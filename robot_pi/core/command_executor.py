"""
Command Executor Module for Robot Pi

Processes and routes control commands from Base Pi.

Commands are authenticated via SecureFramer before reaching this module.

SAFETY-CRITICAL:
- E-STOP commands are processed with strict validation
- Unknown commands are logged and ignored (no actuation)
- All actuation goes through ActuatorController safety checks
"""

import logging
import json
import os
import time
import threading
from typing import Dict, Any, Optional, Tuple

from common.constants import (
    MSG_EMERGENCY_STOP, MSG_PING, ESTOP_REASON_COMMAND,
    ESTOP_CLEAR_CONFIRM
)
from robot_pi import config
from robot_pi.core.autonomous_cutter import AutonomousCutter

logger = logging.getLogger(__name__)

AUTOCUT_STATUS_FILE = '/run/serpent/autocut_status'


class ChainsawRamp:
    """
    Soft start/stop ramp for a chainsaw on/off motor.

    Ramps motor speed linearly when starting or stopping to reduce
    inrush current spikes. Sends keepalive commands at 10 Hz to
    prevent Motoron command-timeout while holding speed.

    E-STOP behaviour: actuator_controller.engage_estop() already stops
    the motor at the hardware level. This class additionally resets its
    internal state to 0 when it detects E-STOP, so the motor does NOT
    restart automatically when E-STOP is cleared.
    """

    RAMP_UP_S   = 1.0   # seconds from 0 → full speed
    RAMP_DOWN_S = 1.5   # seconds from full speed → 0
    LOOP_HZ     = 50    # ramp update rate
    KEEPALIVE_HZ = 10   # keepalive rate when holding target speed

    def __init__(self, motor_id: int, full_speed: int, actuator_controller):
        """
        Args:
            motor_id:             Motor to drive (e.g. 4 or 5)
            full_speed:           Absolute max speed value (e.g. 720)
            actuator_controller:  ActuatorController instance
        """
        self.motor_id            = motor_id
        self.full_speed          = full_speed
        self.actuator_controller = actuator_controller

        self._lock      = threading.Lock()
        self._target    = 0    # desired speed (signed int)
        self._current   = 0    # last speed commanded to hardware (int)
        self._current_f = 0.0  # float accumulator for smooth stepping

        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"cs-ramp-m{motor_id}",
        )
        self._thread.start()

    def set_target(self, speed: int):
        """Set desired speed. Ramp thread transitions smoothly."""
        with self._lock:
            self._target = speed

    def stop_thread(self):
        """Stop the background ramp thread."""
        self._running = False
        self._thread.join(timeout=2.0)

    def _loop(self):
        interval          = 1.0 / self.LOOP_HZ
        keepalive_interval = 1.0 / self.KEEPALIVE_HZ
        up_step   = self.full_speed / (self.RAMP_UP_S   * self.LOOP_HZ)
        down_step = self.full_speed / (self.RAMP_DOWN_S * self.LOOP_HZ)
        last_send = 0.0

        while self._running:
            time.sleep(interval)

            # E-STOP: motor already stopped by actuator. Reset internal
            # state so the motor does not restart when E-STOP is cleared.
            if self.actuator_controller.is_estop_engaged():
                with self._lock:
                    self._current  = 0
                    self._target   = 0
                self._current_f = 0.0
                continue

            with self._lock:
                target  = self._target
                current = self._current

            if current != target:
                # Ramp-up when magnitude is increasing, ramp-down otherwise.
                ramping_up = abs(target) > abs(current)

                if ramping_up:
                    # INSTANT ramp-up: jump directly to target
                    self._current_f = float(target)
                    logger.debug(f"Chainsaw Motor {self.motor_id}: INSTANT start to {target}")
                else:
                    # GRADUAL ramp-down: use slow deceleration step
                    step = down_step
                    if target < current:   # going more negative (spinning up)
                        self._current_f = max(float(target), self._current_f - step)
                    else:                  # going toward 0 (spinning down)
                        self._current_f = min(float(target), self._current_f + step)

                new_speed = int(round(self._current_f))
                with self._lock:
                    self._current = new_speed
                self.actuator_controller.set_motor_speed(self.motor_id, new_speed)
                last_send = time.time()

            elif current != 0:
                # Holding non-zero speed: send keepalive to prevent Motoron timeout.
                now = time.time()
                if now - last_send >= keepalive_interval:
                    self.actuator_controller.set_motor_speed(self.motor_id, current)
                    last_send = now

            else:
                # At 0, keep float accumulator in sync.
                self._current_f = 0.0


class CommandExecutor:
    """
    Command executor for Robot Pi.

    Routes authenticated control commands to appropriate handlers.
    """

    def __init__(
        self,
        actuator_controller,
        framer,
        video_capture=None,
        sensor_reader=None
    ):
        """
        Initialize command executor.

        Args:
            actuator_controller: ActuatorController instance for motor/servo control
            framer: SecureFramer instance for PSK validation
            video_capture: Optional VideoCapture instance for camera switching
            sensor_reader: Optional SensorReader instance for autonomous cutting
        """
        self.actuator_controller = actuator_controller
        self.framer = framer
        self.video_capture = video_capture
        self.sensor_reader = sensor_reader

        # State
        self.height = 0.0
        self.force = 0.0

        # Chainsaw control - 90% power (720/800)
        self._chainsaw_speed_multiplier = 100  # Reduced from 200 to 100 (half speed)
        self._chainsaw_onoff_speed = 780
        self._climb_up_speed = config.CLIMB_UP_SPEED

        # Soft-start/stop ramps for chainsaw on/off motors.
        # CS1 = Motor 5, CS2 = Motor 4. Ramp threads start immediately
        # but stay idle (target=0) until a command arrives.
        self._cs1_ramp = ChainsawRamp(
            motor_id=5,
            full_speed=self._chainsaw_onoff_speed,
            actuator_controller=actuator_controller,
        )
        self._cs2_ramp = ChainsawRamp(
            motor_id=4,
            full_speed=self._chainsaw_onoff_speed,
            actuator_controller=actuator_controller,
        )
        self._chainsaw1_axis_value = 0.0  # Track current axis value
        self._chainsaw2_axis_value = 0.0
        self._chainsaw1_onoff_active = False
        self._chainsaw2_onoff_active = False

        # R1 button state for fast feed travel
        self._r1_pressed = False

        # Chainsaw up/down timeout (background thread monitors this)
        # 0.75 seconds max continuous run time - auto-stops then immediately ready for reuse
        self._chainsaw_timeout_s = 0.75  # Max continuous run time (0.75 seconds, reduced from 1.5s)
        self._chainsaw1_start_time = None  # When motor 2 started (None = not running)
        self._chainsaw2_start_time = None  # When motor 3 started
        self._chainsaw_lock = threading.Lock()
        self._chainsaw_timeout_thread = None
        self._chainsaw_timeout_running = False

        # Double-press detection for L2/R2 autonomous cutting
        self._l2_last_press_time = 0.0
        self._r2_last_press_time = 0.0

        # Autonomous cutter instances (one per chainsaw)
        self._autocut_cs1: Optional[AutonomousCutter] = None
        self._autocut_cs2: Optional[AutonomousCutter] = None
        self._autocut_lock = threading.Lock()

        # Bypass flags: when True, chainsaw timeout loop skips Motor 2/3 respectively
        self._autocut1_active = False
        self._autocut2_active = False

        # Ping/Pong tracking for RTT measurement
        # When we receive a ping, we store it and include pong data in telemetry
        self._last_ping_ts = 0.0      # Timestamp from the ping message
        self._last_ping_seq = 0       # Sequence number from the ping message
        self._last_ping_received = 0.0  # When we received the ping (local time)
        self._ping_lock = threading.Lock()

        # Control tracking (for E-STOP clear validation)
        self.last_control_time = time.time()
        self.control_connected = False

        # E-STOP command deduplication (defense-in-depth)
        self._last_estop_command_time = 0.0
        self._last_estop_command_engage: Optional[bool] = None
        self._estop_dedup_window_s = 0.5  # Ignore duplicate commands within 500ms

        # Motor timeout safety - stop motors if no input received
        self._last_input_time = time.time()
        self._input_timeout_s = 0.5  # Stop motors if no input for 500ms
        self._motor_timeout_thread = None
        self._motor_timeout_running = False
        self._input_lock = threading.Lock()

        logger.info("CommandExecutor initialized")

    def start_motor_timeout_monitor(self):
        """Start the motor timeout monitor thread."""
        if not self._motor_timeout_running:
            self._motor_timeout_running = True
            self._motor_timeout_thread = threading.Thread(
                target=self._motor_timeout_loop,
                daemon=True
            )
            self._motor_timeout_thread.start()
            logger.info(f"Motor timeout monitor started (timeout={self._input_timeout_s}s)")

    def stop_motor_timeout_monitor(self):
        """Stop the motor timeout monitor thread."""
        self._motor_timeout_running = False
        if self._motor_timeout_thread:
            self._motor_timeout_thread.join(timeout=2.0)
        logger.info("Motor timeout monitor stopped")

    def _motor_timeout_loop(self):
        """
        Monitor motor input timeout and stop motors if no input received.

        This prevents motors from continuing to run when the controller
        disconnects or stops sending input.
        """
        logger.info("Motor timeout monitor loop started")
        last_motors_active = False

        while self._motor_timeout_running:
            try:
                time.sleep(0.1)  # Check every 100ms

                with self._input_lock:
                    input_age = time.time() - self._last_input_time

                # If no input for longer than timeout, stop all motors
                if input_age > self._input_timeout_s:
                    # Only log and stop if motors were previously active
                    if last_motors_active:
                        logger.info(f"Motor timeout: no input for {input_age:.2f}s, stopping all motors")
                        self._stop_all_motors()
                        last_motors_active = False
                else:
                    last_motors_active = True

            except Exception as e:
                logger.error(f"Error in motor timeout loop: {e}")
                time.sleep(1.0)

        logger.info("Motor timeout monitor loop stopped")

    def _stop_all_motors(self, force_stop_chainsaws: bool = False):
        """
        Soft-stop motors 0-5 on input timeout.

        Motors 6 (hoist) and 7 (traverse) are intentionally excluded — they
        are "move while pressed" motors that the operator holds for extended
        periods. They should only be zeroed on a genuine connection loss, which
        is handled separately in bridge_coordinator._control_receiver_loop via
        the heartbeat-miss path (see _stop_positional_motors()).

        Autocut: active autonomous cutters are stopped first to prevent
        fighting on motors 2/3.

        Args:
            force_stop_chainsaws: When True, also stop latched chainsaw on/off
                motors 4/5. This should be used for genuine control loss such
                as heartbeat misses or disconnects. The regular idle timeout
                leaves a pressed chainsaw button running until its matching
                release command arrives.
        """
        try:
            # Stop any active autonomous cutters before zeroing their motors.
            if self._autocut1_active:
                self._stop_autocut(1)
            if self._autocut2_active:
                self._stop_autocut(2)

            # Motors 0-3: direct zero
            for motor_id in [0, 1, 2, 3]:
                self.actuator_controller.set_motor_speed(motor_id, 0)

            # Motors 4-5 (chainsaw on/off): preserve explicit press/release
            # semantics during the generic idle timeout, but always stop them
            # on a real control-loss event.
            if force_stop_chainsaws or not self._chainsaw1_onoff_active:
                self._cs1_ramp.set_target(0)
            if force_stop_chainsaws or not self._chainsaw2_onoff_active:
                self._cs2_ramp.set_target(0)

        except Exception as e:
            logger.error(f"Error stopping motors: {e}")

    def _stop_positional_motors(self):
        """
        Zero hoist (motor 6) and traverse (motor 7) on connection loss only.

        Called exclusively by the heartbeat-miss path in bridge_coordinator,
        not by the regular input-timeout loop. Motor 6 (hoist/ascender) has
        its Motoron hardware timeout explicitly disabled, so this is the only
        software safety net for it during a real connection drop.
        """
        try:
            self.actuator_controller.set_motor_speed(6, 0)
            self.actuator_controller.set_motor_speed(7, 0)
        except Exception as e:
            logger.error(f"Error stopping positional motors: {e}")

    def start_chainsaw_timeout_monitor(self):
        """Start the chainsaw timeout monitor thread."""
        if not self._chainsaw_timeout_running:
            self._chainsaw_timeout_running = True
            self._chainsaw_timeout_thread = threading.Thread(
                target=self._chainsaw_timeout_loop,
                daemon=True
            )
            self._chainsaw_timeout_thread.start()
            logger.info(f"Chainsaw timeout monitor started (timeout={self._chainsaw_timeout_s}s)")

    def stop_chainsaw_timeout_monitor(self):
        """Stop the chainsaw timeout monitor thread and ramp threads."""
        self._chainsaw_timeout_running = False
        if self._chainsaw_timeout_thread:
            self._chainsaw_timeout_thread.join(timeout=2.0)
        self._cs1_ramp.stop_thread()
        self._cs2_ramp.stop_thread()
        logger.info("Chainsaw timeout monitor stopped")

    def _chainsaw_timeout_loop(self):
        """
        Background thread that monitors chainsaw up/down motors for timeout.

        Stops motor if it has been running continuously for > 1.5 seconds.
        After timeout, motor stops but is IMMEDIATELY ready for reuse.
        User can keep pressing to run in 1.5s bursts.
        """
        logger.info(f"Chainsaw timeout monitor loop started (timeout={self._chainsaw_timeout_s}s)")
        loop_count = 0

        while self._chainsaw_timeout_running:
            try:
                time.sleep(0.05)  # Check every 50ms for responsive timeout
                now = time.time()
                loop_count += 1

                # Log every 2 seconds (40 loops) to confirm thread is running
                if loop_count % 40 == 0:
                    with self._chainsaw_lock:
                        cs1_status = f"running {now - self._chainsaw1_start_time:.1f}s" if self._chainsaw1_start_time else "idle"
                        cs2_status = f"running {now - self._chainsaw2_start_time:.1f}s" if self._chainsaw2_start_time else "idle"
                        logger.info(f"Chainsaw timeout monitor: CS1={cs1_status}, CS2={cs2_status}")

                with self._chainsaw_lock:
                    # Check chainsaw 1 (Motor 2) — skip if autocut is managing it
                    if self._chainsaw1_start_time is not None and not self._autocut1_active:
                        elapsed = now - self._chainsaw1_start_time
                        if elapsed > self._chainsaw_timeout_s:
                            logger.info(f"CHAINSAW 1 TIMEOUT: {elapsed:.1f}s - stopping Motor 2 (ready for reuse)")
                            self.actuator_controller.set_motor_speed(2, 0)
                            self._chainsaw1_start_time = None  # Reset timer, ready for immediate reuse

                    # Check chainsaw 2 (Motor 3) — skip if autocut is managing it
                    if self._chainsaw2_start_time is not None and not self._autocut2_active:
                        elapsed = now - self._chainsaw2_start_time
                        if elapsed > self._chainsaw_timeout_s:
                            logger.info(f"CHAINSAW 2 TIMEOUT: {elapsed:.1f}s - stopping Motor 3 (ready for reuse)")
                            self.actuator_controller.set_motor_speed(3, 0)
                            self._chainsaw2_start_time = None  # Reset timer, ready for immediate reuse

            except Exception as e:
                logger.error(f"Error in chainsaw timeout loop: {e}")
                time.sleep(0.5)

        logger.info("Chainsaw timeout monitor loop stopped")

    def process_command(self, payload: bytes, seq: int):
        """
        Process a received, authenticated control command.

        SAFETY: Unknown commands are logged and ignored (no actuation).

        Args:
            payload: Command payload (JSON bytes)
            seq: Sequence number from framing protocol
        """
        try:
            message = payload.decode('utf-8')
            command = json.loads(message)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error(f"Failed to decode command payload: {e}")
            # E-STOP on decode error disabled - only operator_command E-STOP enabled
            return

        command_type = command.get('type')
        data = command.get('data', {})

        # Update control timing
        self.last_control_time = time.time()

        logger.debug(f"Command: type={command_type}, seq={seq}")

        # Route command to appropriate handler
        if command_type == MSG_EMERGENCY_STOP:
            self._handle_emergency_stop(data)

        elif command_type == MSG_PING:
            self._handle_ping(data, seq)

        elif command_type == 'clamp_close':
            self.actuator_controller.set_servo_position(0.0)

        elif command_type == 'clamp_open':
            self.actuator_controller.set_servo_position(1.0)

        elif command_type == 'height_update':
            self.height = float(data.get('height', 0.0))

        elif command_type == 'force_update':
            self.force = float(data.get('force', 0.0))

        elif command_type == 'start_camera':
            camera_id = int(data.get('camera_id', 0))
            if self.video_capture:
                self.video_capture.set_active_camera(camera_id)

        elif command_type == 'input_event':
            self._handle_input_event(data)

        elif command_type == 'raw_button_press':
            pass  # Log only, no action

        elif command_type == 'chainsaw_command':
            self._handle_chainsaw_command(data)

        elif command_type == 'chainsaw_move':
            self._handle_chainsaw_move(data)

        elif command_type == 'climb_command':
            self._handle_climb_command(data)

        elif command_type == 'traverse_command':
            self._handle_traverse_command(data)

        elif command_type == 'brake_command':
            self._handle_brake_command(data)

        elif command_type == 'r1_button':
            self._handle_r1_button(data)

        else:
            logger.warning(f"Unknown command type: {command_type} (ignored)")

    def _handle_emergency_stop(self, data: Dict[str, Any]):
        """
        Handle emergency_stop command with SET semantics.

        engage=true (default): Engage E-STOP
        engage=false: Attempt to clear E-STOP (requires validation)

        Includes deduplication to prevent processing duplicate commands
        that may arrive due to network retries or upstream issues.

        Args:
            data: Command data dictionary
        """
        engage = data.get('engage', True)  # Default to ENGAGE for safety
        reason = data.get('reason', 'operator_command')

        # Deduplication: check if this is a duplicate command
        now = time.time()
        time_since_last = now - self._last_estop_command_time

        if time_since_last < self._estop_dedup_window_s:
            if self._last_estop_command_engage == engage:
                logger.debug(f"E-STOP dedup: ignoring duplicate {'ENGAGE' if engage else 'CLEAR'} "
                           f"command (age={time_since_last*1000:.0f}ms)")
                return
            # Different command within window - this is a rapid toggle, log warning but process it
            logger.warning(f"E-STOP rapid toggle detected: was {'ENGAGE' if self._last_estop_command_engage else 'CLEAR'}, "
                         f"now {'ENGAGE' if engage else 'CLEAR'} (age={time_since_last*1000:.0f}ms)")

        # Update deduplication state
        self._last_estop_command_time = now
        self._last_estop_command_engage = engage

        if engage:
            logger.warning(f"E-STOP ENGAGE command received: {reason}")
            self.actuator_controller.engage_estop(ESTOP_REASON_COMMAND, reason)
        else:
            # Attempt to clear - requires strict validation
            confirm = data.get('confirm_clear', '')
            control_age = time.time() - self.last_control_time

            # Additional check: PSK must be valid
            if not self.framer.is_authenticated():
                logger.error("E-STOP clear REJECTED: No valid PSK configured")
                return

            success = self.actuator_controller.clear_estop(
                confirm=confirm,
                control_age_s=control_age,
                control_connected=self.control_connected
            )

            if success:
                logger.info("E-STOP CLEARED by operator command")
            else:
                logger.warning("E-STOP clear REJECTED (see previous log)")

    def _handle_ping(self, data: Dict[str, Any], seq: int):
        """
        Handle ping from Base Pi.

        Store ping data so it can be echoed back in telemetry as pong.
        Base Pi will compute RTT from the pong data.

        Args:
            data: Ping data dictionary
            seq: Sequence number
        """
        ping_ts = data.get('ts', 0)
        ping_seq = data.get('seq', 0)

        with self._ping_lock:
            self._last_ping_ts = ping_ts
            self._last_ping_seq = ping_seq
            self._last_ping_received = time.time()

        logger.debug(f"Received ping: ts={ping_ts}, seq={ping_seq}")

    def _handle_input_event(self, data: Dict[str, Any]):
        """
        Handle gamepad input event.

        Axis Mapping:
        - Axis 1 (Left Stick Y): Motor 3 (Chainsaw 2 up/down)
        - Axis 3 (Right Stick Y): Motor 2 (Chainsaw 1 up/down)

        Button Mapping:
        - Button A (0): Motor 0 UP/FORWARD (claw open)
        - Button B (1): Motor 0 DOWN/BACKWARD (claw close)

        Args:
            data: Input event data dictionary
        """
        # Update last input time to prevent motor timeout
        with self._input_lock:
            self._last_input_time = time.time()

        event_type = data.get('type')
        index = data.get('index', 0)
        value = data.get('value', 0.0)

        try:
            if event_type == 'axis':
                # Deadzone threshold for analog sticks
                DEADZONE = 0.15

                # Left Stick Y-axis (Axis 1): Chainsaw 2 up/down (Motor 3)
                # NOTE: This is LEGACY - Flutter app sends button events (indices 16-17) instead
                # Kept for compatibility with other input sources that may send raw axis values
                if index == 1:
                    self._chainsaw2_axis_value = float(value)

                    # Apply deadzone - treat small values as zero
                    if abs(self._chainsaw2_axis_value) < DEADZONE:
                        logger.debug("Chainsaw 2 STOP: Stick centered")
                        with self._chainsaw_lock:
                            self._chainsaw2_start_time = None  # Clear timer
                        self.actuator_controller.set_motor_speed(3, 0)
                    else:
                        # Select speed based on R1 state
                        speed_multiplier = 600 if self._r1_pressed else self._chainsaw_speed_multiplier  # 100
                        speed = int(self._chainsaw2_axis_value * speed_multiplier)

                        with self._chainsaw_lock:
                            if self._chainsaw2_start_time is None:
                                self._chainsaw2_start_time = time.time()

                        mode = "FAST (600)" if self._r1_pressed else f"NORMAL ({self._chainsaw_speed_multiplier})"
                        logger.info(f"CS2 feed Motor 3: {speed} [{mode}]")
                        self.actuator_controller.set_motor_speed(3, speed)

                # Right Stick Y-axis (Axis 3): Chainsaw 1 up/down (Motor 2)
                # NOTE: This is LEGACY - Flutter app sends button events (indices 20-21) instead
                elif index == 3:
                    self._chainsaw1_axis_value = float(value)

                    # Apply deadzone - treat small values as zero
                    if abs(self._chainsaw1_axis_value) < DEADZONE:
                        logger.debug("Chainsaw 1 STOP: Stick centered")
                        with self._chainsaw_lock:
                            self._chainsaw1_start_time = None  # Clear timer
                        self.actuator_controller.set_motor_speed(2, 0)
                    else:
                        # Select speed based on R1 state
                        speed_multiplier = 600 if self._r1_pressed else self._chainsaw_speed_multiplier  # 100
                        speed = int(self._chainsaw1_axis_value * speed_multiplier)

                        with self._chainsaw_lock:
                            if self._chainsaw1_start_time is None:
                                self._chainsaw1_start_time = time.time()

                        mode = "FAST (600)" if self._r1_pressed else f"NORMAL ({self._chainsaw_speed_multiplier})"
                        logger.info(f"CS1 feed Motor 2: {speed} [{mode}]")
                        self.actuator_controller.set_motor_speed(2, speed)

            elif event_type == 'button':
                # A button (index 0): Motor 0 UP/FORWARD (claw open)
                if index == 0:
                    if value > 0:
                        logger.info("A button: Motor 0 UP (claw open)")
                        self.actuator_controller.set_motor_speed(0, 760)  # 95% forward/up
                    else:
                        self.actuator_controller.set_motor_speed(0, 0)  # Stop

                # B button (index 1): Motor 0 DOWN/BACKWARD (claw close)
                elif index == 1:
                    if value > 0:
                        logger.info("B button: Motor 0 DOWN (claw close)")
                        self.actuator_controller.set_motor_speed(0, -760)  # 95% backward/down
                    else:
                        self.actuator_controller.set_motor_speed(0, 0)  # Stop

                # L2/R2 button (index 6/7): Chainsaw On/Off
                # DISABLED: Now handled via chainsaw_command events from backend
                # This prevents duplicate control where both input_event and chainsaw_command
                # were activating different motors simultaneously
                # elif index == 6:
                #     # Clean up completed autocut if present
                #     with self._autocut_lock:
                #         if self._autocut_cs2 is not None and not self._autocut_cs2.is_running():
                #             self._autocut_cs2 = None
                #             self._autocut2_active = False
                #         autocut_active = self._autocut2_active
                #
                #     if autocut_active:
                #         # Autocut owns Motor 4 — suppress all L2 events
                #         pass
                #     elif value > 0:
                #         now = time.time()
                #         if now - self._l2_last_press_time < config.AUTOCUT_DOUBLE_PRESS_WINDOW_S:
                #             # Double-press detected — start autonomous cutting
                #             logger.info("L2 double-press: starting autonomous cut CS2")
                #             self._start_autocut(2)
                #             self._l2_last_press_time = 0.0  # Reset so next press is fresh
                #         else:
                #             # First (or new) press — soft-start ramp
                #             self._l2_last_press_time = now
                #             logger.info("L2 button: Chainsaw 2 ON (Motor 4, soft-start)")
                #             self._cs2_ramp.set_target(self._chainsaw_onoff_speed)
                #     else:
                #         # Release — soft-stop ramp
                #         logger.info("L2 button: Chainsaw 2 OFF (Motor 4, soft-stop)")
                #         self._cs2_ramp.set_target(0)
                #
                # elif index == 7:
                #     # Clean up completed autocut if present
                #     with self._autocut_lock:
                #         if self._autocut_cs1 is not None and not self._autocut_cs1.is_running():
                #             self._autocut_cs1 = None
                #             self._autocut1_active = False
                #         autocut_active = self._autocut1_active
                #
                #     if autocut_active:
                #         # Autocut owns Motor 5 — suppress all R2 events
                #         pass
                #     elif value > 0:
                #         now = time.time()
                #         if now - self._r2_last_press_time < config.AUTOCUT_DOUBLE_PRESS_WINDOW_S:
                #             # Double-press detected — start autonomous cutting
                #             logger.info("R2 double-press: starting autonomous cut CS1")
                #             self._start_autocut(1)
                #             self._r2_last_press_time = 0.0
                #         else:
                #             # First (or new) press — soft-start ramp
                #             self._r2_last_press_time = now
                #             logger.info("R2 button: Chainsaw 1 ON (Motor 5, soft-start)")
                #             self._cs1_ramp.set_target(-self._chainsaw_onoff_speed)
                #     else:
                #         # Release — soft-stop ramp
                #         logger.info("R2 button: Chainsaw 1 OFF (Motor 5, soft-stop)")
                #         self._cs1_ramp.set_target(0)

                # Dpad Down button (index 11): Brake + Descent (Motor 6 forward - direction swapped)
                elif index == 11:
                    if value > 0:
                        logger.info("Dpad Down: Brake ENGAGE (servo to 1°) + Descent (Motor 6 backward)")
                        self.actuator_controller.set_servo_position(0.0056)  # 1° engage
                        self.actuator_controller.set_motor_speed(6, -720)
                    else:
                        logger.info("Dpad Down: Brake RELEASE (servo to 60°) + Motor 6 STOP")
                        self.actuator_controller.set_motor_speed(6, 0)  # Stop motor first
                        self.actuator_controller.set_servo_position(0.3333)  # 60° release

        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid input_event data: {e}")

    def _handle_r1_button(self, data: Dict[str, Any]):
        """Handle R1 button for fast feed travel mode."""
        action = data.get('action', 'release')

        with self._input_lock:
            self._last_input_time = time.time()

        if action == 'press':
            self._r1_pressed = True
            logger.info("R1 PRESSED: Fast feed travel mode ENABLED (600 speed)")
        else:
            self._r1_pressed = False
            logger.info("R1 RELEASED: Normal feed mode (100 speed)")

    def _handle_chainsaw_command(self, data: Dict[str, Any]):
        """
        Handle chainsaw on/off push-button command.

        Motor mapping:
        - chainsaw_id 1 → Motor 5
        - chainsaw_id 2 → Motor 4

        Args:
            data: Command data with chainsaw_id and action ('on'/'off' or 'press'/'release')
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        chainsaw_id = data.get('chainsaw_id', 1)
        action = data.get('action', 'off')

        # Map chainsaw_id to ramp: 1→CS1 (Motor 5), 2→CS2 (Motor 4)
        ramp = self._cs1_ramp if chainsaw_id == 1 else self._cs2_ramp
        motor_id = 6 - chainsaw_id  # 1→5, 2→4  (for logging only)

        # Support both 'on'/'off' and 'press'/'release' for compatibility
        if action in ('on', 'press'):
            logger.info(f"Chainsaw {chainsaw_id}: Motor {motor_id} ON (soft-start)")
            if chainsaw_id == 1:
                self._chainsaw1_onoff_active = True
            else:
                self._chainsaw2_onoff_active = True
            onoff_sign = 1
            ramp.set_target(onoff_sign * self._chainsaw_onoff_speed)
        else:  # 'off' or 'release'
            logger.info(f"Chainsaw {chainsaw_id}: Motor {motor_id} OFF (soft-stop)")
            if chainsaw_id == 1:
                self._chainsaw1_onoff_active = False
            else:
                self._chainsaw2_onoff_active = False
            ramp.set_target(0)

    def _handle_chainsaw_move(self, data: Dict[str, Any]):
        """
        Handle chainsaw up/down movement command (for button/API control).

        Motor mapping:
        - chainsaw_id 1 → Motor 2
        - chainsaw_id 2 → Motor 3

        Note: Continuous analog stick control is handled in _handle_input_event.
        This method is for discrete button/command-based control.
        Uses same timeout system as axis control (0.75 seconds max).

        Args:
            data: Command data with chainsaw_id and direction (up/down/stop)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        chainsaw_id = data.get('chainsaw_id', 1)
        direction = data.get('direction', 'stop')

        # Map chainsaw_id to motor: 1→Motor 2, 2→Motor 3
        motor_id = 1 + chainsaw_id  # 1→2, 2→3

        # Select speed based on R1 state (normal 100 vs fast travel 600)
        speed = 600 if self._r1_pressed else self._chainsaw_speed_multiplier

        if direction == 'up' or direction == 'down':
            # Use same timeout system as axis control
            with self._chainsaw_lock:
                # Start timer if not already running
                if chainsaw_id == 1:
                    if self._chainsaw1_start_time is None:
                        self._chainsaw1_start_time = time.time()
                        logger.info(f"Chainsaw {chainsaw_id} timer started ({self._chainsaw_timeout_s:.2f}s timeout)")
                else:
                    if self._chainsaw2_start_time is None:
                        self._chainsaw2_start_time = time.time()
                        logger.info(f"Chainsaw {chainsaw_id} timer started ({self._chainsaw_timeout_s:.2f}s timeout)")

                # Set motor speed (inside lock so timeout can't race)
                # CS1 Motor 2: +speed = down, -speed = up
                # CS2 Motor 3: -speed = down, +speed = up (direction swapped)
                mode = "FAST (600)" if self._r1_pressed else f"NORMAL ({self._chainsaw_speed_multiplier})"
                if direction == 'up':
                    logger.info(f"Chainsaw {chainsaw_id} UP: Motor {motor_id} backward [{mode}]")
                    dir_sign = 1 if chainsaw_id == 2 else -1
                    self.actuator_controller.set_motor_speed(motor_id, dir_sign * speed)
                else:  # down
                    logger.info(f"Chainsaw {chainsaw_id} DOWN: Motor {motor_id} forward [{mode}]")
                    dir_sign = -1 if chainsaw_id == 2 else 1
                    self.actuator_controller.set_motor_speed(motor_id, dir_sign * speed)

        else:  # stop
            logger.info(f"Chainsaw {chainsaw_id} STOP: Motor {motor_id}")
            # Clear timer - ready for next use
            with self._chainsaw_lock:
                if chainsaw_id == 1:
                    self._chainsaw1_start_time = None
                else:
                    self._chainsaw2_start_time = None
            self.actuator_controller.set_motor_speed(motor_id, 0)

    def _handle_climb_command(self, data: Dict[str, Any]):
        """
        Handle hoist/climb up command.

        Motor mapping: Motor 6 (up only, down is handled by brake_command)

        Args:
            data: Command data with direction (up/stop)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        direction = data.get('direction', 'stop')

        if direction == 'up':
            logger.info("Hoist UP: Motor 6 forward")
            self.actuator_controller.set_motor_speed(6, self._climb_up_speed)
        else:  # stop
            logger.info("Hoist STOP: Motor 6")
            self.actuator_controller.set_motor_speed(6, 0)

    def _handle_traverse_command(self, data: Dict[str, Any]):
        """
        Handle traverse left/right command.

        Motor mapping: Motor 7

        Args:
            data: Command data with direction (left/right/stop)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        direction = data.get('direction', 'stop')

        if direction == 'left':
            logger.info("Traverse LEFT: Motor 7 forward")
            self.actuator_controller.set_motor_speed(7, 400)  # 50% forward
        elif direction == 'right':
            logger.info("Traverse RIGHT: Motor 7 backward")
            self.actuator_controller.set_motor_speed(7, -400)  # 50% backward
        else:  # stop
            logger.info("Traverse STOP: Motor 7")
            self.actuator_controller.set_motor_speed(7, 0)

    def _handle_brake_command(self, data: Dict[str, Any]):
        """
        Handle brake engage/release command (servo + descent motor control).

        Servo position:
        - engage: 1 degree (position 0.0056) + Motor 6 backwards (descend)
        - release: 60 degrees (position 0.3333) + Motor 6 stop

        Args:
            data: Command data with action (engage/release)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        action = data.get('action', 'release')

        if action == 'engage':
            # 1 degree = 1/180 = 0.0056 position
            logger.info("Brake ENGAGE: Servo to 1° + Descent (Motor 6 backward)")
            success = self.actuator_controller.set_servo_position(0.0056)
            if not success:
                logger.warning("Brake ENGAGE failed - servo command returned False")
            self.actuator_controller.set_motor_speed(6, -720)
        else:  # release
            # 60 degrees = 60/180 = 0.3333 position
            logger.info("Brake RELEASE: Motor 6 STOP + Servo to 60°")
            self.actuator_controller.set_motor_speed(6, 0)  # Stop motor first
            success = self.actuator_controller.set_servo_position(0.3333)
            if not success:
                logger.warning("Brake RELEASE failed - servo command returned False")

    # ------------------------------------------------------------------
    # Autonomous cutting management
    # ------------------------------------------------------------------

    def _write_autocut_status(self):
        """Write current autocut running state to status file for dashboard."""
        try:
            status = {
                'cs1': self._autocut1_active,
                'cs2': self._autocut2_active,
            }
            os.makedirs(os.path.dirname(AUTOCUT_STATUS_FILE), exist_ok=True)
            tmp = AUTOCUT_STATUS_FILE + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(status, f)
            os.replace(tmp, AUTOCUT_STATUS_FILE)
        except Exception as e:
            logger.debug(f"Could not write autocut status: {e}")

    def _start_autocut(self, chainsaw_id: int):
        """
        Create and start an AutonomousCutter for the given chainsaw.

        Stops any existing autocut for that chainsaw first.
        Sets the bypass flag so the chainsaw timeout loop does not
        interfere with Motor 2/3 while autocut is running.

        Args:
            chainsaw_id: 1 or 2
        """
        if self.sensor_reader is None:
            logger.warning(
                f"Cannot start autocut CS{chainsaw_id}: no sensor_reader available"
            )
            return

        with self._autocut_lock:
            # Stop any existing autocut for this chainsaw
            if chainsaw_id == 1 and self._autocut_cs1 is not None:
                self._autocut_cs1.stop()
                self._autocut_cs1 = None
            elif chainsaw_id == 2 and self._autocut_cs2 is not None:
                self._autocut_cs2.stop()
                self._autocut_cs2 = None

            ramp = self._cs1_ramp if chainsaw_id == 1 else self._cs2_ramp

            cutter = AutonomousCutter(
                chainsaw_id=chainsaw_id,
                actuator_controller=self.actuator_controller,
                sensor_reader=self.sensor_reader,
                target_current=config.AUTOCUT_TARGET_CURRENT_A,
                pid_kp=config.AUTOCUT_PID_KP,
                pid_ki=config.AUTOCUT_PID_KI,
                pid_kd=config.AUTOCUT_PID_KD,
                max_speed=config.AUTOCUT_MAX_SPEED,
                idle_current=config.AUTOCUT_IDLE_CURRENT_A,
                breakthrough_confirm_s=config.AUTOCUT_BREAKTHROUGH_CONFIRM_S,
                loop_interval_s=config.AUTOCUT_LOOP_INTERVAL_S,
                onoff_speed=config.AUTOCUT_BLADE_SPEED,
                set_blade_speed=ramp.set_target,
                on_complete=self._on_autocut_complete,
                approach_speed=config.AUTOCUT_CS1_APPROACH_SPEED if chainsaw_id == 1 else config.AUTOCUT_APPROACH_SPEED,
                contact_confirm_reads=config.AUTOCUT_CONTACT_CONFIRM_READS,
                max_cut_duration_s=config.AUTOCUT_MAX_CUT_DURATION_S,
            )

            if chainsaw_id == 1:
                self._autocut_cs1 = cutter
                self._autocut1_active = True
                # Clear feed-motor start time so timeout loop ignores Motor 2
                with self._chainsaw_lock:
                    self._chainsaw1_start_time = None
            else:
                self._autocut_cs2 = cutter
                self._autocut2_active = True
                with self._chainsaw_lock:
                    self._chainsaw2_start_time = None

            cutter.start()
            logger.info(f"Autocut CS{chainsaw_id} started (autonomous mode)")

        self._write_autocut_status()

    def _stop_autocut(self, chainsaw_id: int):
        """
        Stop the autonomous cutter for the given chainsaw and clear state.

        Args:
            chainsaw_id: 1 or 2
        """
        with self._autocut_lock:
            if chainsaw_id == 1:
                if self._autocut_cs1 is not None:
                    self._autocut_cs1.stop()
                    self._autocut_cs1 = None
                self._autocut1_active = False
                self._chainsaw1_onoff_active = False
                with self._chainsaw_lock:
                    self._chainsaw1_start_time = None
            else:
                if self._autocut_cs2 is not None:
                    self._autocut_cs2.stop()
                    self._autocut_cs2 = None
                self._autocut2_active = False
                self._chainsaw2_onoff_active = False
                with self._chainsaw_lock:
                    self._chainsaw2_start_time = None

        # Always stop blade and feed — covers the case where autocut completed
        # naturally (instance already cleared) but blade is still spinning.
        ramp = self._cs1_ramp if chainsaw_id == 1 else self._cs2_ramp
        ramp.set_target(0)
        feed_motor = 2 if chainsaw_id == 1 else 3
        self.actuator_controller.set_motor_speed(feed_motor, 0)

        logger.info(f"Autocut CS{chainsaw_id} stopped")
        self._write_autocut_status()

    def _on_autocut_complete(self, chainsaw_id: int):
        """
        Callback fired by AutonomousCutter when breakthrough is confirmed.

        Clears autocut state so normal L2/R2 operation resumes.

        Args:
            chainsaw_id: 1 or 2
        """
        with self._autocut_lock:
            if chainsaw_id == 1:
                self._autocut_cs1 = None
                self._autocut1_active = False
            else:
                self._autocut_cs2 = None
                self._autocut2_active = False
        logger.info(
            f"Autocut CS{chainsaw_id} complete — branch cut, returning to manual mode"
        )
        self._write_autocut_status()

    def get_pong_data(self) -> Optional[Dict[str, Any]]:
        """
        Get pong data for RTT measurement.

        Returns pong data if a recent ping was received (within last 5 seconds).

        Returns:
            Pong data dictionary or None if no recent ping
        """
        with self._ping_lock:
            ping_age = time.time() - self._last_ping_received
            if self._last_ping_ts > 0 and ping_age < 5.0:
                return {
                    'ping_ts': self._last_ping_ts,
                    'ping_seq': self._last_ping_seq,
                    'robot_ts': time.time()  # When robot is sending pong
                }
            return None

    def get_height(self) -> float:
        """Get current height value."""
        return self.height

    def get_force(self) -> float:
        """Get current force value."""
        return self.force

    def set_control_connected(self, connected: bool):
        """
        Update control connection status.

        Args:
            connected: True if control is connected
        """
        self.control_connected = connected

    def update_control_time(self):
        """Update last control time (for E-STOP clear validation)."""
        self.last_control_time = time.time()

    def get_last_control_time(self) -> float:
        """Get timestamp of last control command."""
        return self.last_control_time

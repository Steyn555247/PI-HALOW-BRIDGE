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
import time
import threading
from typing import Dict, Any, Optional, Tuple

from common.constants import (
    MSG_EMERGENCY_STOP, MSG_PING, ESTOP_REASON_COMMAND,
    ESTOP_CLEAR_CONFIRM
)

logger = logging.getLogger(__name__)


class CommandExecutor:
    """
    Command executor for Robot Pi.

    Routes authenticated control commands to appropriate handlers.
    """

    def __init__(
        self,
        actuator_controller,
        framer,
        video_capture=None
    ):
        """
        Initialize command executor.

        Args:
            actuator_controller: ActuatorController instance for motor/servo control
            framer: SecureFramer instance for PSK validation
            video_capture: Optional VideoCapture instance for camera switching
        """
        self.actuator_controller = actuator_controller
        self.framer = framer
        self.video_capture = video_capture

        # State
        self.height = 0.0
        self.force = 0.0

        # Chainsaw control - 90% power (720/800)
        self._chainsaw_speed_multiplier = 720
        self._chainsaw_onoff_speed = 720
        self._chainsaw1_axis_value = 0.0  # Track current axis value
        self._chainsaw2_axis_value = 0.0

        # Chainsaw up/down timeout (background thread monitors this)
        # 1.5 seconds max continuous run time - auto-stops then immediately ready for reuse
        self._chainsaw_timeout_s = 1.5  # Max continuous run time (1.5 seconds)
        self._chainsaw1_start_time = None  # When motor 2 started (None = not running)
        self._chainsaw2_start_time = None  # When motor 3 started
        self._chainsaw_lock = threading.Lock()
        self._chainsaw_timeout_thread = None
        self._chainsaw_timeout_running = False

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

    def _stop_all_motors(self):
        """Stop claw motors only (0-1). Chainsaw, traverse, hoist excluded from timeout."""
        try:
            # Only stop claw motors (0-1)
            # Excluded from timeout:
            #   - Motor 2, 3: Chainsaw up/down (have explicit stop on release)
            #   - Motor 4, 5: Chainsaw on/off (toggle, user controls)
            #   - Motor 6: Traverse (has explicit stop on release)
            #   - Motor 7: Hoist (has explicit stop on release)
            for motor_id in range(2):  # Only motors 0 and 1
                self.actuator_controller.set_motor_speed(motor_id, 0)
        except Exception as e:
            logger.error(f"Error stopping motors: {e}")

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
        """Stop the chainsaw timeout monitor thread."""
        self._chainsaw_timeout_running = False
        if self._chainsaw_timeout_thread:
            self._chainsaw_timeout_thread.join(timeout=2.0)
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
                    # Check chainsaw 1 (Motor 2)
                    if self._chainsaw1_start_time is not None:
                        elapsed = now - self._chainsaw1_start_time
                        if elapsed > self._chainsaw_timeout_s:
                            logger.info(f"CHAINSAW 1 TIMEOUT: {elapsed:.1f}s - stopping Motor 2 (ready for reuse)")
                            self.actuator_controller.set_motor_speed(2, 0)
                            self._chainsaw1_start_time = None  # Reset timer, ready for immediate reuse

                    # Check chainsaw 2 (Motor 3)
                    if self._chainsaw2_start_time is not None:
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
        - Axis 1 (Left Stick Y): Motor 2 (Chainsaw 1 up/down)
        - Axis 3 (Right Stick Y): Motor 3 (Chainsaw 2 up/down)

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

                # Left Stick Y-axis (Axis 1): Chainsaw 1 up/down
                # NOTE: This is LEGACY - Flutter app sends button events (indices 16-17) instead
                # Kept for compatibility with other input sources that may send raw axis values
                if index == 1:
                    self._chainsaw1_axis_value = float(value)

                    # Apply deadzone - treat small values as zero
                    if abs(self._chainsaw1_axis_value) < DEADZONE:
                        logger.debug("Chainsaw 1 STOP: Stick released via axis (Motor 2)")
                        with self._chainsaw_lock:
                            self._chainsaw1_start_time = None  # Clear timer
                        self.actuator_controller.set_motor_speed(2, 0)
                    else:
                        # All motor control inside lock to prevent race with timeout thread
                        with self._chainsaw_lock:
                            # Start timer if not already running
                            if self._chainsaw1_start_time is None:
                                self._chainsaw1_start_time = time.time()
                                logger.debug("Chainsaw 1: Timer started via axis")
                            # Set motor speed (inside lock so timeout can't race)
                            speed = int(self._chainsaw1_axis_value * self._chainsaw_speed_multiplier)
                            logger.debug(f"Chainsaw 1: Motor 2 speed={speed}")
                            self.actuator_controller.set_motor_speed(2, speed)

                # Right Stick Y-axis (Axis 3): Chainsaw 2 up/down
                # NOTE: This is LEGACY - Flutter app sends button events (indices 20-21) instead
                elif index == 3:
                    self._chainsaw2_axis_value = float(value)

                    # Apply deadzone - treat small values as zero
                    if abs(self._chainsaw2_axis_value) < DEADZONE:
                        logger.debug("Chainsaw 2 STOP: Stick released via axis (Motor 3)")
                        with self._chainsaw_lock:
                            self._chainsaw2_start_time = None  # Clear timer
                        self.actuator_controller.set_motor_speed(3, 0)
                    else:
                        # All motor control inside lock to prevent race with timeout thread
                        with self._chainsaw_lock:
                            # Start timer if not already running
                            if self._chainsaw2_start_time is None:
                                self._chainsaw2_start_time = time.time()
                                logger.debug("Chainsaw 2: Timer started via axis")
                            # Set motor speed (inside lock so timeout can't race)
                            speed = int(self._chainsaw2_axis_value * self._chainsaw_speed_multiplier)
                            logger.debug(f"Chainsaw 2: Motor 3 speed={speed}")
                            self.actuator_controller.set_motor_speed(3, speed)

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

                # L2 button (index 6): Chainsaw 1 On/Off (Motor 4) - Push-button
                elif index == 6:
                    if value > 0:
                        logger.info("L2 button: Chainsaw 1 ON (Motor 4)")
                        self.actuator_controller.set_motor_speed(4, self._chainsaw_onoff_speed)  # 90% forward
                    else:
                        logger.info("L2 button: Chainsaw 1 OFF (Motor 4)")
                        self.actuator_controller.set_motor_speed(4, 0)  # Stop

                # R2 button (index 7): Chainsaw 2 On/Off (Motor 5) - Push-button
                elif index == 7:
                    if value > 0:
                        logger.info("R2 button: Chainsaw 2 ON (Motor 5)")
                        self.actuator_controller.set_motor_speed(5, self._chainsaw_onoff_speed)  # 90% forward
                    else:
                        logger.info("R2 button: Chainsaw 2 OFF (Motor 5)")
                        self.actuator_controller.set_motor_speed(5, 0)  # Stop

                # Dpad Down button (index 11): Brake + Descent (Motor 7 backwards)
                elif index == 11:
                    if value > 0:
                        logger.info("Dpad Down: Brake ENGAGE (servo to 1°) + Descent (Motor 7 backwards)")
                        self.actuator_controller.set_servo_position(0.0056)  # 1° engage
                        self.actuator_controller.set_motor_speed(7, -400)  # 50% backwards (descend)
                    else:
                        logger.info("Dpad Down: Brake RELEASE (servo to 60°) + Motor 7 STOP")
                        self.actuator_controller.set_motor_speed(7, 0)  # Stop motor first
                        self.actuator_controller.set_servo_position(0.3333)  # 60° release

        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid input_event data: {e}")

    def _handle_chainsaw_command(self, data: Dict[str, Any]):
        """
        Handle chainsaw on/off push-button command.

        Motor mapping:
        - chainsaw_id 1 → Motor 4
        - chainsaw_id 2 → Motor 5

        Args:
            data: Command data with chainsaw_id and action ('on'/'off' or 'press'/'release')
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        chainsaw_id = data.get('chainsaw_id', 1)
        action = data.get('action', 'off')

        # Map chainsaw_id to motor: 1→Motor 4, 2→Motor 5
        motor_id = 3 + chainsaw_id  # 1→4, 2→5

        # Support both 'on'/'off' and 'press'/'release' for compatibility
        if action in ('on', 'press'):
            logger.info(f"Chainsaw {chainsaw_id}: Motor {motor_id} ON (forward)")
            self.actuator_controller.set_motor_speed(motor_id, self._chainsaw_onoff_speed)  # 90% forward
        else:  # 'off' or 'release'
            logger.info(f"Chainsaw {chainsaw_id}: Motor {motor_id} OFF")
            self.actuator_controller.set_motor_speed(motor_id, 0)

    def _handle_chainsaw_move(self, data: Dict[str, Any]):
        """
        Handle chainsaw up/down movement command (for button/API control).

        Motor mapping:
        - chainsaw_id 1 → Motor 2
        - chainsaw_id 2 → Motor 3

        Note: Continuous analog stick control is handled in _handle_input_event.
        This method is for discrete button/command-based control.
        Uses same timeout system as axis control (1.5 seconds max).

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

        # 90% power = 720
        speed = self._chainsaw_speed_multiplier

        if direction == 'up' or direction == 'down':
            # Use same timeout system as axis control
            with self._chainsaw_lock:
                # Start timer if not already running
                if chainsaw_id == 1:
                    if self._chainsaw1_start_time is None:
                        self._chainsaw1_start_time = time.time()
                        logger.info(f"Chainsaw {chainsaw_id} timer started (1.5s timeout)")
                else:
                    if self._chainsaw2_start_time is None:
                        self._chainsaw2_start_time = time.time()
                        logger.info(f"Chainsaw {chainsaw_id} timer started (1.5s timeout)")

                # Set motor speed (inside lock so timeout can't race)
                if direction == 'up':
                    logger.info(f"Chainsaw {chainsaw_id} UP: Motor {motor_id} forward (90% power)")
                    self.actuator_controller.set_motor_speed(motor_id, speed)
                else:  # down
                    logger.info(f"Chainsaw {chainsaw_id} DOWN: Motor {motor_id} backward (90% power)")
                    self.actuator_controller.set_motor_speed(motor_id, -speed)

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

        Motor mapping: Motor 7 (up only, down is handled by brake_command)

        Args:
            data: Command data with direction (up/stop)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        direction = data.get('direction', 'stop')

        if direction == 'up':
            logger.info("Hoist UP: Motor 7 forward")
            self.actuator_controller.set_motor_speed(7, 400)  # 50% forward
        else:  # stop
            logger.info("Hoist STOP: Motor 7")
            self.actuator_controller.set_motor_speed(7, 0)

    def _handle_traverse_command(self, data: Dict[str, Any]):
        """
        Handle traverse left/right command.

        Motor mapping: Motor 6

        Args:
            data: Command data with direction (left/right/stop)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        direction = data.get('direction', 'stop')

        if direction == 'left':
            logger.info("Traverse LEFT: Motor 6 forward")
            self.actuator_controller.set_motor_speed(6, 400)  # 50% forward
        elif direction == 'right':
            logger.info("Traverse RIGHT: Motor 6 backward")
            self.actuator_controller.set_motor_speed(6, -400)  # 50% backward
        else:  # stop
            logger.info("Traverse STOP: Motor 6")
            self.actuator_controller.set_motor_speed(6, 0)

    def _handle_brake_command(self, data: Dict[str, Any]):
        """
        Handle brake engage/release command (servo + descent motor control).

        Servo position:
        - engage: 1 degree (position 0.0056) + Motor 7 backwards (descend)
        - release: 60 degrees (position 0.3333) + Motor 7 stop

        Args:
            data: Command data with action (engage/release)
        """
        # Update input time to prevent timeout
        with self._input_lock:
            self._last_input_time = time.time()

        action = data.get('action', 'release')

        if action == 'engage':
            # 1 degree = 1/180 = 0.0056 position
            logger.info("Brake ENGAGE: Servo to 1° + Descent (Motor 7 backwards)")
            success = self.actuator_controller.set_servo_position(0.0056)
            if not success:
                logger.warning("Brake ENGAGE failed - servo command returned False")
            self.actuator_controller.set_motor_speed(7, -400)  # 50% backwards (descend)
        else:  # release
            # 60 degrees = 60/180 = 0.3333 position
            logger.info("Brake RELEASE: Motor 7 STOP + Servo to 60°")
            self.actuator_controller.set_motor_speed(7, 0)  # Stop motor first
            success = self.actuator_controller.set_servo_position(0.3333)
            if not success:
                logger.warning("Brake RELEASE failed - servo command returned False")

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

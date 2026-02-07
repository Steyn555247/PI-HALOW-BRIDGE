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
from typing import Dict, Any, Optional

from common.constants import (
    MSG_EMERGENCY_STOP, MSG_PING, ESTOP_REASON_COMMAND,
    ESTOP_REASON_DECODE_ERROR, ESTOP_CLEAR_CONFIRM
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

        # Ping/Pong tracking for RTT measurement
        # When we receive a ping, we store it and include pong data in telemetry
        self._last_ping_ts = 0.0      # Timestamp from the ping message
        self._last_ping_seq = 0       # Sequence number from the ping message
        self._last_ping_received = 0.0  # When we received the ping (local time)
        self._ping_lock = threading.Lock()

        # Control tracking (for E-STOP clear validation)
        self.last_control_time = time.time()
        self.control_connected = False

        logger.info("CommandExecutor initialized")

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
            self.actuator_controller.engage_estop(
                ESTOP_REASON_DECODE_ERROR, f"JSON decode: {e}"
            )
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

        else:
            logger.warning(f"Unknown command type: {command_type} (ignored)")

    def _handle_emergency_stop(self, data: Dict[str, Any]):
        """
        Handle emergency_stop command with SET semantics.

        engage=true (default): Engage E-STOP
        engage=false: Attempt to clear E-STOP (requires validation)

        Args:
            data: Command data dictionary
        """
        engage = data.get('engage', True)  # Default to ENGAGE for safety
        reason = data.get('reason', 'operator_command')

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

        Args:
            data: Input event data dictionary
        """
        event_type = data.get('type')
        index = data.get('index', 0)
        value = data.get('value', 0.0)

        try:
            if event_type == 'axis':
                if index == 0:
                    speed = int(float(value) * 800)
                    self.actuator_controller.set_motor_speed(0, speed)
                elif index == 1:
                    speed = int(float(value) * 800)
                    self.actuator_controller.set_motor_speed(1, speed)

            elif event_type == 'button':
                # A button (index 0): Motor 0 forward
                if index == 0:
                    if value > 0:
                        self.actuator_controller.set_motor_speed(0, 760)  # 95% forward
                    else:
                        self.actuator_controller.set_motor_speed(0, 0)  # Stop
                # Y button (index 3): Motor 0 backward
                elif index == 3:
                    if value > 0:
                        self.actuator_controller.set_motor_speed(0, -760)  # 95% backward
                    else:
                        self.actuator_controller.set_motor_speed(0, 0)  # Stop
                # B button (index 1): Servo position 0 (legacy)
                elif index == 1 and value > 0:
                    self.actuator_controller.set_servo_position(0.0)
                # X button (index 2): Servo position 1 (legacy)
                elif index == 2 and value > 0:
                    self.actuator_controller.set_servo_position(1.0)

        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid input_event data: {e}")

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

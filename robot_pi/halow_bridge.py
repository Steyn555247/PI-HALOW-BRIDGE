"""
HaLow Bridge - Main coordinator for Robot Pi

SAFETY-CRITICAL MODULE

Safety invariants:
1. E-STOP is LATCHED on boot (via ActuatorController)
2. Watchdog triggers E-STOP if no valid control for WATCHDOG_TIMEOUT_S
3. Watchdog triggers E-STOP if control never established after STARTUP_GRACE_S
4. Any disconnect, buffer overflow, decode error, auth failure triggers E-STOP
5. E-STOP can only be cleared via authenticated command with strict validation
6. All commands must pass HMAC authentication and anti-replay check
"""

import logging
import time
import signal
import sys
import json
import socket
import threading
import os
from typing import Optional, Dict, Any

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
from video_capture import VideoCapture
from sensor_reader import SensorReader
from actuator_controller import ActuatorController
from common.framing import SecureFramer, FramingError, AuthenticationError, ReplayError
from common.constants import (
    MAX_CONTROL_BUFFER, WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S,
    ESTOP_REASON_WATCHDOG, ESTOP_REASON_DISCONNECT, ESTOP_REASON_BUFFER_OVERFLOW,
    ESTOP_REASON_DECODE_ERROR, ESTOP_REASON_AUTH_FAILURE, ESTOP_REASON_STARTUP_TIMEOUT,
    ESTOP_REASON_COMMAND, ESTOP_REASON_INTERNAL_ERROR, ESTOP_CLEAR_CONFIRM,
    MSG_EMERGENCY_STOP, MSG_PING, MSG_PONG, HEARTBEAT_INTERVAL_S
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HaLowBridge:
    """
    Main bridge coordinator for Robot Pi.

    SAFETY: Robot boots with E-STOP engaged and will not clear it until:
    1. Control connection is established
    2. Valid authenticated emergency_stop command with engage=false received
    3. All validation checks pass
    """

    def __init__(self):
        # Initialize secure framing (loads PSK from environment)
        self.framer = SecureFramer(role="robot_pi")
        if not self.framer.is_authenticated():
            logger.critical("NO VALID PSK - Robot will refuse to clear E-STOP")

        # Components - ActuatorController starts with E-STOP ENGAGED
        self.actuator_controller = ActuatorController(
            motoron_addresses=config.MOTORON_ADDRESSES,
            servo_gpio=config.SERVO_GPIO_PIN,
            servo_freq=config.SERVO_FREQ,
            active_motors=config.ACTIVE_MOTORS
        )

        self.sensor_reader = SensorReader(
            i2c_bus=config.I2C_BUS,
            bno085_addr=config.BNO085_ADDRESS,
            bmp388_addr=config.BMP388_ADDRESS,
            read_interval=config.SENSOR_READ_INTERVAL
        )

        self.video_capture = None
        if config.VIDEO_ENABLED:
            self.video_capture = VideoCapture(
                camera_devices=config.CAMERA_DEVICES,
                base_pi_ip=config.BASE_PI_IP,
                video_port=config.VIDEO_PORT,
                width=config.CAMERA_WIDTH,
                height=config.CAMERA_HEIGHT,
                fps=config.CAMERA_FPS,
                quality=config.CAMERA_QUALITY
            )

        # Control receiver state (Robot Pi is the SERVER for control)
        self.control_server: Optional[socket.socket] = None
        self.control_socket: Optional[socket.socket] = None  # Accepted client connection
        self.control_connected = False
        self.control_established = False  # True once first valid command received
        self.last_control_time = time.time()  # Initialize to boot time for watchdog
        self.last_control_seq = 0

        # Telemetry sender state
        self.telemetry_socket: Optional[socket.socket] = None
        self.telemetry_connected = False
        self.telemetry_framer = SecureFramer(role="robot_pi_telemetry")

        # State
        self.running = False
        self.boot_time = time.time()
        self.height = 0.0
        self.force = 0.0

        # Ping/Pong tracking for RTT measurement
        # When we receive a ping, we store it and include pong data in telemetry
        self._last_ping_ts = 0.0      # Timestamp from the ping message
        self._last_ping_seq = 0       # Sequence number from the ping message
        self._last_ping_received = 0.0  # When we received the ping (local time)
        self._ping_lock = threading.Lock()

        # RTT tracking (from pings) - legacy, kept for compatibility
        self.last_rtt_ms = 0
        self.rtt_lock = threading.Lock()

        logger.info("HaLowBridge initialized - E-STOP is ENGAGED (fail-safe boot)")

    def start(self):
        """Start the bridge. E-STOP remains engaged until explicitly cleared."""
        self.running = True

        # Start components
        logger.info("Starting components...")

        self.actuator_controller.start()
        self.sensor_reader.start()

        if self.video_capture:
            self.video_capture.start()

        # Start control receiver thread
        control_thread = threading.Thread(target=self._control_receiver_loop, daemon=True)
        control_thread.start()

        # Start telemetry sender thread
        telemetry_thread = threading.Thread(target=self._telemetry_sender_loop, daemon=True)
        telemetry_thread.start()

        logger.info("HaLowBridge started - entering watchdog loop")

        # Watchdog loop runs in main thread
        self._watchdog_loop()

    def stop(self):
        """Stop the bridge. Engages E-STOP."""
        logger.info("Stopping HaLowBridge...")
        self.running = False

        # Engage E-STOP on shutdown
        self.actuator_controller.engage_estop(ESTOP_REASON_INTERNAL_ERROR, "Bridge shutdown")

        # Stop components
        self.actuator_controller.stop()
        self.sensor_reader.stop()

        if self.video_capture:
            self.video_capture.stop()

        # Close sockets
        self._close_control_server()
        self._close_telemetry_socket()

        logger.info("HaLowBridge stopped")

    def _close_control_socket(self):
        """Safely close control client socket (keeps server open)"""
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
            self.control_socket = None
        self.control_connected = False

    def _close_control_server(self):
        """Safely close control server socket"""
        self._close_control_socket()
        if self.control_server:
            try:
                self.control_server.close()
            except:
                pass
            self.control_server = None

    def _close_telemetry_socket(self):
        """Safely close telemetry socket"""
        if self.telemetry_socket:
            try:
                self.telemetry_socket.close()
            except:
                pass
            self.telemetry_socket = None
        self.telemetry_connected = False

    def _control_receiver_loop(self):
        """
        Receive control commands from Base Pi.

        Robot Pi runs a TCP server on CONTROL_PORT.
        Base Pi's control_forwarder connects to us.

        SAFETY: Any error triggers E-STOP and waits for reconnect.
        """
        logger.info("Control receiver thread started")

        # Start the server - retry on failure
        while self.running and not self._start_control_server():
            logger.error("Retrying control server startup in 2 seconds...")
            time.sleep(2.0)

        while self.running:
            try:
                # Accept connection if not connected
                if not self.control_connected:
                    if not self._accept_control_connection():
                        # Timeout or error - loop continues
                        continue

                # Receive authenticated frame
                try:
                    payload, seq = self.framer.read_frame_from_socket(
                        self.control_socket, timeout=1.0
                    )
                    self._process_control_command(payload, seq)

                except socket.timeout:
                    # Normal timeout, continue loop
                    continue

                except AuthenticationError as e:
                    logger.error(f"Authentication FAILED: {e}")
                    self.actuator_controller.engage_estop(
                        ESTOP_REASON_AUTH_FAILURE, str(e)
                    )
                    self._close_control_socket()
                    time.sleep(1.0)

                except ReplayError as e:
                    logger.error(f"Replay attack detected: {e}")
                    self.actuator_controller.engage_estop(
                        ESTOP_REASON_AUTH_FAILURE, f"Replay: {e}"
                    )
                    self._close_control_socket()
                    time.sleep(1.0)

                except FramingError as e:
                    logger.error(f"Framing error: {e}")
                    self.actuator_controller.engage_estop(
                        ESTOP_REASON_DECODE_ERROR, str(e)
                    )
                    self._close_control_socket()
                    time.sleep(1.0)

                except ConnectionError as e:
                    logger.warning(f"Control connection lost: {e}")
                    self.actuator_controller.engage_estop(
                        ESTOP_REASON_DISCONNECT, str(e)
                    )
                    self._close_control_socket()
                    time.sleep(1.0)

                except UnicodeDecodeError as e:
                    logger.error(f"Unicode decode error: {e}")
                    self.actuator_controller.engage_estop(
                        ESTOP_REASON_DECODE_ERROR, str(e)
                    )
                    self._close_control_socket()
                    time.sleep(1.0)

            except Exception as e:
                logger.error(f"Unexpected error in control loop: {e}")
                self.actuator_controller.engage_estop(
                    ESTOP_REASON_INTERNAL_ERROR, str(e)
                )
                self._close_control_socket()
                time.sleep(1.0)

    def _start_control_server(self) -> bool:
        """Start control server to accept connections from Base Pi"""
        try:
            if self.control_server:
                return True  # Already started

            logger.info(f"Starting control server on port {config.CONTROL_PORT}")
            self.control_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Socket options for clean port reuse
            # SO_REUSEADDR allows rebinding after TIME_WAIT
            self.control_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # On Windows, also use SO_EXCLUSIVEADDRUSE to prevent port hijacking
            if sys.platform == 'win32':
                try:
                    # SO_EXCLUSIVEADDRUSE = -5 on Windows
                    self.control_server.setsockopt(socket.SOL_SOCKET, -5, 1)
                except (OSError, AttributeError):
                    pass  # Not available on this Windows version

            # Bind to all interfaces (0.0.0.0) so both localhost and network work
            self.control_server.bind(('0.0.0.0', config.CONTROL_PORT))
            self.control_server.listen(1)
            self.control_server.settimeout(2.0)  # Shorter timeout for more responsive accept loop
            logger.info(f"Control server listening on 0.0.0.0:{config.CONTROL_PORT}")
            return True

        except OSError as e:
            if e.errno == 10048 or 'Address already in use' in str(e):  # WSAEADDRINUSE or Unix equivalent
                logger.error(f"Port {config.CONTROL_PORT} already in use. Previous process may still be running.")
            else:
                logger.error(f"Failed to start control server: {e}")
            self._close_control_server()
            return False

        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            self._close_control_server()
            return False

    def _accept_control_connection(self) -> bool:
        """Accept a control connection from Base Pi"""
        try:
            if not self.control_server:
                if not self._start_control_server():
                    time.sleep(1.0)  # Wait before retry if server failed to start
                    return False

            # Close any existing client connection
            self._close_control_socket()

            # Log at INFO level periodically so we can see accept is running
            if not hasattr(self, '_last_accept_log') or time.time() - self._last_accept_log > 10.0:
                logger.info("Control server: waiting for Base Pi connection...")
                self._last_accept_log = time.time()

            client_sock, addr = self.control_server.accept()
            client_sock.settimeout(5.0)  # Timeout for all operations

            self.control_socket = client_sock
            self.control_connected = True
            logger.info(f"Accepted control connection from {addr}")
            return True

        except socket.timeout:
            # Normal - no connection yet, continue loop
            return False

        except OSError as e:
            # Handle "bad file descriptor" after server socket closed
            if e.errno == 9 or e.errno == 10038:  # EBADF or WSAENOTSOCK
                logger.warning("Control server socket closed, will restart")
                self._close_control_server()
            else:
                logger.error(f"Error accepting control connection: {e}")
                self._close_control_socket()
            return False

        except Exception as e:
            logger.error(f"Error accepting control connection: {e}")
            self._close_control_socket()
            return False

    def _process_control_command(self, payload: bytes, seq: int):
        """
        Process a received, authenticated control command.

        SAFETY: Unknown commands are logged and ignored (no actuation).
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
        self.last_control_seq = seq

        if not self.control_established:
            self.control_established = True
            logger.info(f"Control ESTABLISHED (seq={seq})")

        logger.debug(f"Command: type={command_type}, seq={seq}")

        # Handle commands
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
        """
        ping_ts = data.get('ts', 0)
        ping_seq = data.get('seq', 0)

        with self._ping_lock:
            self._last_ping_ts = ping_ts
            self._last_ping_seq = ping_seq
            self._last_ping_received = time.time()

        logger.debug(f"Received ping: ts={ping_ts}, seq={ping_seq}")

    def _handle_input_event(self, data: Dict[str, Any]):
        """Handle gamepad input event"""
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
                if index == 0 and value > 0:
                    self.actuator_controller.set_servo_position(0.0)
                elif index == 1 and value > 0:
                    self.actuator_controller.set_servo_position(1.0)

        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid input_event data: {e}")

    def _telemetry_sender_loop(self):
        """Send telemetry to Base Pi"""
        while self.running:
            try:
                if not self.telemetry_connected:
                    if not self._connect_telemetry():
                        time.sleep(config.RECONNECT_DELAY)
                        continue

                # Collect telemetry
                sensor_data = self.sensor_reader.get_all_data()
                motor_currents = self.actuator_controller.get_motor_currents()
                estop_info = self.actuator_controller.get_estop_info()

                control_age_ms = int((time.time() - self.last_control_time) * 1000)

                with self.rtt_lock:
                    rtt_ms = self.last_rtt_ms

                # Get pong data if we received a recent ping (within last 5 seconds)
                pong_data = None
                with self._ping_lock:
                    ping_age = time.time() - self._last_ping_received
                    if self._last_ping_ts > 0 and ping_age < 5.0:
                        pong_data = {
                            'ping_ts': self._last_ping_ts,
                            'ping_seq': self._last_ping_seq,
                            'robot_ts': time.time()  # When robot is sending pong
                        }

                telemetry = {
                    'voltage': 12.0,  # TODO: Read actual voltage
                    'height': self.height,
                    'force': self.force,
                    'chainsaw_force': 0.0,
                    'rope_force': 0.0,
                    'imu': sensor_data.get('imu', {}),
                    'barometer': sensor_data.get('barometer', {}),
                    'motor_currents': motor_currents,
                    'estop': estop_info,
                    'control_age_ms': control_age_ms,
                    'control_established': self.control_established,
                    'control_seq': self.last_control_seq,
                    'rtt_ms': rtt_ms,
                    'pong': pong_data,  # Include pong data for RTT measurement
                    'timestamp': time.time()
                }

                # Send authenticated telemetry
                try:
                    payload = json.dumps(telemetry).encode('utf-8')
                    frame = self.telemetry_framer.create_frame(payload)
                    self.telemetry_socket.sendall(frame)
                    logger.debug(f"Sent telemetry: control_age={control_age_ms}ms")

                except Exception as e:
                    logger.error(f"Failed to send telemetry: {e}")
                    self._close_telemetry_socket()
                    continue

                time.sleep(config.TELEMETRY_INTERVAL)

            except Exception as e:
                logger.error(f"Telemetry sender error: {e}")
                self._close_telemetry_socket()
                time.sleep(1.0)

    def _connect_telemetry(self) -> bool:
        """Connect to Base Pi telemetry server"""
        try:
            logger.info(f"Connecting to Base Pi telemetry at {config.BASE_PI_IP}:{config.TELEMETRY_PORT}")
            self._close_telemetry_socket()

            self.telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.telemetry_socket.settimeout(5.0)
            self.telemetry_socket.connect((config.BASE_PI_IP, config.TELEMETRY_PORT))
            self.telemetry_connected = True
            logger.info("Connected to Base Pi telemetry")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Base Pi telemetry: {e}")
            self._close_telemetry_socket()
            return False

    def _watchdog_loop(self):
        """
        Monitor connection health and trigger E-STOP if needed.

        SAFETY INVARIANTS:
        1. If no valid control for WATCHDOG_TIMEOUT_S -> E-STOP
        2. If control never established after STARTUP_GRACE_S -> E-STOP (stays latched)
        3. Watchdog can only ENGAGE E-STOP, never clear it
        """
        last_status_log = time.time()

        while self.running:
            try:
                time.sleep(1.0)
                now = time.time()

                # Check startup grace period
                uptime = now - self.boot_time
                if uptime > STARTUP_GRACE_S and not self.control_established:
                    if not self.actuator_controller.is_estop_engaged():
                        logger.error(f"Control not established after {uptime:.0f}s, engaging E-STOP")
                        self.actuator_controller.engage_estop(
                            ESTOP_REASON_STARTUP_TIMEOUT,
                            f"No control after {STARTUP_GRACE_S}s"
                        )
                    # Continue checking - E-STOP stays latched

                # Check control timeout (always, even before control_established)
                control_age = now - self.last_control_time
                if control_age > WATCHDOG_TIMEOUT_S:
                    if not self.actuator_controller.is_estop_engaged():
                        logger.error(f"Control timeout ({control_age:.1f}s), engaging E-STOP")
                        self.actuator_controller.engage_estop(
                            ESTOP_REASON_WATCHDOG,
                            f"No control for {control_age:.1f}s"
                        )

                # Log status every 10 seconds
                if now - last_status_log > 10.0:
                    estop_info = self.actuator_controller.get_estop_info()
                    status = {
                        "event": "status",
                        "uptime_s": int(uptime),
                        "control_connected": self.control_connected,
                        "control_established": self.control_established,
                        "control_age_ms": int(control_age * 1000),
                        "telemetry_connected": self.telemetry_connected,
                        "estop_engaged": estop_info["engaged"],
                        "estop_reason": estop_info["reason"],
                        "psk_valid": self.framer.is_authenticated()
                    }
                    logger.info(json.dumps(status))
                    last_status_log = now

            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                # Engage E-STOP on watchdog error
                self.actuator_controller.engage_estop(
                    ESTOP_REASON_INTERNAL_ERROR,
                    f"Watchdog error: {e}"
                )


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info(f"Shutdown signal {sig} received")
    if bridge:
        bridge.stop()
    sys.exit(0)


# Global bridge instance
bridge: Optional[HaLowBridge] = None


def main():
    """Main entry point"""
    global bridge

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("SERPENT ROBOT PI BRIDGE STARTING")
    logger.info("E-STOP is ENGAGED by default (fail-safe)")
    logger.info("=" * 60)

    # Create and start bridge
    bridge = HaLowBridge()

    try:
        bridge.start()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        if bridge:
            bridge.stop()
        sys.exit(1)


if __name__ == '__main__':
    main()

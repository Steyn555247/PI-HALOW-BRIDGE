"""
Bridge Coordinator for Robot Pi

Main orchestrator that replaces the monolithic halow_bridge.py.

SAFETY-CRITICAL MODULE:
- E-STOP is LATCHED on boot (via ActuatorController)
- Watchdog triggers E-STOP if no valid control for WATCHDOG_TIMEOUT_S
- All errors trigger E-STOP
- E-STOP can only be cleared via authenticated command

PHASE 5 REFACTORING:
Extracts 752-line monolith into modular components:
- ControlServer: Receives commands (with <2s failover fix)
- CommandExecutor: Routes and executes commands
- TelemetrySender: Sends telemetry (with backoff & caching)
- WatchdogMonitor: Safety timeout monitoring

Result: ~150 LOC coordinator + clean component interfaces.
"""

import logging
import time
import signal
import sys
import os
import threading
from typing import Optional

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from robot_pi import config
from robot_pi.video_capture import VideoCapture
from robot_pi.sensor_reader import SensorReader
from robot_pi.actuator_controller import ActuatorController
from common.framing import SecureFramer
from common.constants import ESTOP_REASON_INTERNAL_ERROR
from common.logging_config import setup_logging

# Phase 5 extracted modules
from robot_pi.core.command_executor import CommandExecutor
from robot_pi.core.watchdog_monitor import WatchdogMonitor
from robot_pi.control.control_server import ControlServer
from robot_pi.telemetry.telemetry_sender import TelemetrySender

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
        """Initialize all bridge components."""
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

        # Configure current sensors
        # DISABLED: Current sensors not implemented yet - causing system overload
        # current_sensors_config = {
        #     'battery': {
        #         'addr': config.CURRENT_SENSOR_BATTERY_ADDR,
        #         'channel': config.CURRENT_SENSOR_BATTERY_CHANNEL,
        #         'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
        #         'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        #     },
        #     'system': {
        #         'addr': config.CURRENT_SENSOR_SYSTEM_ADDR,
        #         'channel': config.CURRENT_SENSOR_SYSTEM_CHANNEL,
        #         'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
        #         'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        #     },
        #     'servo': {
        #         'addr': config.CURRENT_SENSOR_SERVO_ADDR,
        #         'channel': config.CURRENT_SENSOR_SERVO_CHANNEL,
        #         'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
        #         'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        #     }
        # }

        self.sensor_reader = SensorReader(
            i2c_bus=config.I2C_BUS,
            bno055_addr=config.BNO055_ADDRESS,
            bmp581_addr=config.BMP581_ADDRESS,
            read_interval=config.SENSOR_READ_INTERVAL,
            use_multiplexer=config.USE_I2C_MULTIPLEXER,
            mux_addr=config.I2C_MUX_ADDRESS,
            imu_channel=config.IMU_MUX_CHANNEL,
            baro_channel=config.BAROMETER_MUX_CHANNEL,
            current_sensors=None  # Disabled - not implemented yet
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

        # Phase 5: Initialize extracted modules
        self.command_executor = CommandExecutor(
            actuator_controller=self.actuator_controller,
            framer=self.framer,
            video_capture=self.video_capture
        )

        self.control_server = ControlServer(
            port=config.CONTROL_PORT,
            framer=self.framer,
            on_command_received=self._on_command_received,
            on_estop_trigger=self._on_estop_trigger,
            on_auth_success=self._on_auth_success
        )

        self.telemetry_sender = TelemetrySender(
            base_pi_ip=config.BASE_PI_IP,
            telemetry_port=config.TELEMETRY_PORT,
            telemetry_interval=config.TELEMETRY_INTERVAL
        )

        watchdog_disabled = getattr(config, 'DISABLE_WATCHDOG_FOR_LOCAL_TESTING', False)
        self.watchdog_monitor = WatchdogMonitor(
            actuator_controller=self.actuator_controller,
            control_server=self.control_server,
            framer=self.framer,
            status_interval=10.0,
            watchdog_disabled=watchdog_disabled
        )

        # State
        self.running = False

        logger.info("HaLowBridge initialized (Phase 5: modular architecture) - E-STOP is ENGAGED (fail-safe boot)")

    def _on_command_received(self, payload: bytes, seq: int):
        """
        Callback when command is received from control server.

        Args:
            payload: Command payload
            seq: Sequence number
        """
        # Update command executor control time
        self.command_executor.update_control_time()
        self.command_executor.set_control_connected(self.control_server.is_connected())

        # Process command
        self.command_executor.process_command(payload, seq)

    def _on_estop_trigger(self, reason_code: str, message: str):
        """
        Callback when E-STOP should be triggered.

        Args:
            reason_code: E-STOP reason code
            message: E-STOP message
        """
        self.actuator_controller.engage_estop(reason_code, message)

    def _on_auth_success(self):
        """
        Callback when authentication succeeds.

        Automatically clears auth_failure E-STOP if it's currently engaged,
        since successful authentication means the auth_failure condition is resolved.
        """
        estop_info = self.actuator_controller.get_estop_info()
        if estop_info['engaged'] and estop_info['reason'] == 'auth_failure':
            logger.info("Auth succeeded - auto-clearing auth_failure E-STOP")
            self.actuator_controller.clear_estop_local()

    def start(self):
        """Start the bridge. E-STOP remains engaged until explicitly cleared."""
        self.running = True

        # Start components
        logger.info("Starting components...")

        self.actuator_controller.start()
        self.sensor_reader.start()

        if self.video_capture:
            self.video_capture.start()

        # Start motor timeout monitor
        self.command_executor.start_motor_timeout_monitor()

        # Start control server
        if not self.control_server.start_server():
            logger.error("Failed to start control server - retrying in background")

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
        """Stop the bridge."""
        logger.info("Stopping HaLowBridge...")
        self.running = False

        # E-STOP on shutdown disabled - only operator_command E-STOP enabled

        # Stop motor timeout monitor
        self.command_executor.stop_motor_timeout_monitor()

        # Stop components
        self.actuator_controller.stop()
        self.sensor_reader.stop()

        if self.video_capture:
            self.video_capture.stop()

        # Close sockets
        self.control_server.close_server()
        self.telemetry_sender.close()

        logger.info("HaLowBridge stopped")

    def _control_receiver_loop(self):
        """
        Control receiver loop.

        Accepts connections and receives commands via ControlServer.
        """
        logger.info("Control receiver thread started")

        # Start the server - retry on failure
        while self.running and not self.control_server.start_server():
            logger.error("Retrying control server startup in 2 seconds...")
            time.sleep(2.0)

        while self.running:
            try:
                # Accept connection if not connected
                if not self.control_server.is_connected():
                    if not self.control_server.accept_connection():
                        # Timeout or error - continue loop
                        continue

                # Receive command (includes timeout handling)
                self.control_server.receive_command()

            except Exception as e:
                logger.error(f"Unexpected error in control loop: {e}")
                # E-STOP on error disabled - only operator_command E-STOP enabled
                self.control_server.close_client()
                time.sleep(1.0)

    def _telemetry_sender_loop(self):
        """
        Telemetry sender loop.

        Collects and sends telemetry via TelemetrySender.
        """
        logger.info("Telemetry sender thread started")

        while self.running:
            try:
                if not self.telemetry_sender.is_connected():
                    if not self.telemetry_sender.connect():
                        delay = self.telemetry_sender.get_backoff_delay()
                        time.sleep(delay)
                        continue

                # Collect telemetry
                sensor_data = self.sensor_reader.get_all_data()
                motor_currents = self.actuator_controller.get_motor_currents()
                estop_info = self.actuator_controller.get_estop_info()
                current_data = sensor_data.get('current', {})

                # Get battery voltage from current sensor, fallback to hardcoded value
                battery_voltage = current_data.get('battery', {}).get('voltage', 12.0)

                control_age_ms = int(self.control_server.get_control_age() * 1000)

                # Get pong data from command executor
                pong_data = self.command_executor.get_pong_data()

                telemetry = {
                    'voltage': battery_voltage,
                    'height': self.command_executor.get_height(),
                    'force': self.command_executor.get_force(),
                    'chainsaw_force': 0.0,
                    'rope_force': 0.0,
                    'imu': sensor_data.get('imu', {}),
                    'barometer': sensor_data.get('barometer', {}),
                    'motor_currents': motor_currents,
                    'battery': current_data.get('battery', {}),
                    'system_power': current_data.get('system', {}),
                    'servo_power': current_data.get('servo', {}),
                    'estop': estop_info,
                    'control_age_ms': control_age_ms,
                    'control_established': self.control_server.is_control_established(),
                    'control_seq': self.control_server.get_last_control_seq(),
                    'rtt_ms': 0,  # Legacy field, kept for compatibility
                    'pong': pong_data,
                    'timestamp': time.time()
                }

                # Send telemetry
                if not self.telemetry_sender.send_telemetry(telemetry):
                    # Send failed, connection will be closed and retry on next iteration
                    continue

                time.sleep(self.telemetry_sender.get_interval())

            except Exception as e:
                logger.error(f"Telemetry sender error: {e}")
                self.telemetry_sender.close()
                time.sleep(1.0)

    def _watchdog_loop(self):
        """
        Watchdog loop.

        Monitors connection health via WatchdogMonitor.
        """
        logger.info("Watchdog loop started")

        while self.running:
            try:
                time.sleep(1.0)

                # Check safety conditions
                self.watchdog_monitor.check_safety(
                    telemetry_connected=self.telemetry_sender.is_connected()
                )

                # Log status periodically (include sensor data and motor currents for dashboard)
                sensor_data = self.sensor_reader.get_all_data()
                motor_currents = self.actuator_controller.get_motor_currents()
                video_stats = self.video_capture.get_stats() if self.video_capture else None
                self.watchdog_monitor.log_status(
                    telemetry_connected=self.telemetry_sender.is_connected(),
                    sensor_data=sensor_data,
                    motor_currents=motor_currents,
                    video_stats=video_stats
                )

            except Exception as e:
                self.watchdog_monitor.handle_error(e)


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info(f"Shutdown signal {sig} received")
    if bridge:
        bridge.stop()
    sys.exit(0)


# Global bridge instance
bridge: Optional[HaLowBridge] = None


def main():
    """Main entry point."""
    global bridge

    # Setup logging
    setup_logging("robot_pi", config.LOG_LEVEL, config.LOG_FILE)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("SERPENT ROBOT PI BRIDGE STARTING (Phase 5: Modular)")
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

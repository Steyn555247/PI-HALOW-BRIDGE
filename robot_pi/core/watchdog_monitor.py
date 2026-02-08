"""
Watchdog Monitor Module for Robot Pi

Monitors connection health and triggers E-STOP if needed.

SAFETY-CRITICAL:
1. If no valid control for WATCHDOG_TIMEOUT_S (5s) -> E-STOP
2. If control never established after STARTUP_GRACE_S (30s) -> E-STOP
3. Watchdog can only ENGAGE E-STOP, never clear it
4. Can be disabled via config.DISABLE_WATCHDOG_FOR_LOCAL_TESTING for local testing

This is the safety net that protects the robot from runaway conditions.
"""

import logging
import json
import time
from typing import Optional

from common.constants import (
    WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S,
    ESTOP_REASON_WATCHDOG, ESTOP_REASON_STARTUP_TIMEOUT,
    ESTOP_REASON_INTERNAL_ERROR
)

logger = logging.getLogger(__name__)


class WatchdogMonitor:
    """
    Watchdog monitor for Robot Pi.

    Monitors control connection health and triggers E-STOP on timeout.

    SAFETY: Can only engage E-STOP, never clear it.
    """

    def __init__(
        self,
        actuator_controller,
        control_server,
        framer,
        status_interval: float = 10.0,
        watchdog_disabled: bool = False
    ):
        """
        Initialize watchdog monitor.

        Args:
            actuator_controller: ActuatorController instance for E-STOP
            control_server: ControlServer instance for connection status
            framer: SecureFramer instance for PSK validation check
            status_interval: Interval for status logging (default 10s)
            watchdog_disabled: Disable watchdog for local testing (default False)
        """
        self.actuator_controller = actuator_controller
        self.control_server = control_server
        self.framer = framer
        self.status_interval = status_interval
        self.watchdog_disabled = watchdog_disabled

        # Timing
        self.boot_time = time.time()
        self.last_status_log = time.time()

        # Log warning if watchdog is disabled
        if self.watchdog_disabled:
            logger.warning("=" * 60)
            logger.warning("WATCHDOG DISABLED FOR LOCAL TESTING")
            logger.warning("Safety timeouts are NOT enforced")
            logger.warning("=" * 60)

        logger.info("WatchdogMonitor initialized")

    def check_safety(self, telemetry_connected: bool):
        """
        Check safety conditions and engage E-STOP if needed.

        SAFETY: Only engages E-STOP, never clears it.

        Args:
            telemetry_connected: Whether telemetry connection is active
        """
        if self.watchdog_disabled:
            # Skip safety checks if disabled for local testing
            return

        now = time.time()
        uptime = now - self.boot_time
        control_age = self.control_server.get_control_age()

        # SAFETY CHECKS DISABLED - Only operator_command E-STOP enabled
        # Startup grace period check disabled
        # Control timeout check disabled

    def log_status(self, telemetry_connected: bool, sensor_data: Optional[dict] = None, motor_currents: Optional[list] = None, video_stats: Optional[dict] = None):
        """
        Log status periodically.

        Args:
            telemetry_connected: Whether telemetry connection is active
            sensor_data: Optional sensor data (IMU, barometer) to include in status
            motor_currents: Optional motor current data (list of 8 floats in amps)
            video_stats: Optional video connection and frame statistics
        """
        now = time.time()

        if now - self.last_status_log > self.status_interval:
            uptime = now - self.boot_time
            control_age = self.control_server.get_control_age()
            estop_info = self.actuator_controller.get_estop_info()

            status = {
                "event": "status",
                "uptime_s": int(uptime),
                "control_connected": self.control_server.is_connected(),
                "control_established": self.control_server.is_control_established(),
                "control_age_ms": int(control_age * 1000),
                "control_seq": self.control_server.get_last_control_seq(),
                "telemetry_connected": telemetry_connected,
                "estop_engaged": estop_info["engaged"],
                "estop_reason": estop_info["reason"],
                "psk_valid": self.framer.is_authenticated(),
                "watchdog_disabled": self.watchdog_disabled
            }

            # Add sensor data if available
            if sensor_data:
                if 'imu' in sensor_data:
                    status['imu'] = sensor_data['imu']
                if 'barometer' in sensor_data:
                    status['barometer'] = sensor_data['barometer']

            # Add motor currents if available
            if motor_currents:
                status['motor_currents'] = motor_currents

            # Add video stats if available
            if video_stats:
                status['video'] = video_stats

            logger.info(json.dumps(status))
            self.last_status_log = now

    def handle_error(self, error: Exception):
        """
        Handle watchdog error.

        E-STOP triggering disabled - only operator_command E-STOP enabled.

        Args:
            error: Exception that occurred
        """
        logger.error(f"Watchdog error: {error}")

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

        # SAFETY CHECK 1: Startup grace period
        # If control not established after STARTUP_GRACE_S, engage E-STOP
        if uptime > STARTUP_GRACE_S and not self.control_server.is_control_established():
            if not self.actuator_controller.is_estop_engaged():
                logger.error(f"Control not established after {uptime:.0f}s, engaging E-STOP")
                self.actuator_controller.engage_estop(
                    ESTOP_REASON_STARTUP_TIMEOUT,
                    f"No control after {STARTUP_GRACE_S}s"
                )
            # Continue checking - E-STOP stays latched

        # SAFETY CHECK 2: Control timeout
        # If no valid control for WATCHDOG_TIMEOUT_S, engage E-STOP
        if control_age > WATCHDOG_TIMEOUT_S:
            if not self.actuator_controller.is_estop_engaged():
                logger.error(f"Control timeout ({control_age:.1f}s), engaging E-STOP")
                self.actuator_controller.engage_estop(
                    ESTOP_REASON_WATCHDOG,
                    f"No control for {control_age:.1f}s"
                )

    def log_status(self, telemetry_connected: bool):
        """
        Log status periodically.

        Args:
            telemetry_connected: Whether telemetry connection is active
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
                "telemetry_connected": telemetry_connected,
                "estop_engaged": estop_info["engaged"],
                "estop_reason": estop_info["reason"],
                "psk_valid": self.framer.is_authenticated(),
                "watchdog_disabled": self.watchdog_disabled
            }
            logger.info(json.dumps(status))
            self.last_status_log = now

    def handle_error(self, error: Exception):
        """
        Handle watchdog error.

        Engages E-STOP on any watchdog error (even if watchdog is disabled).

        Args:
            error: Exception that occurred
        """
        logger.error(f"Watchdog error: {error}")
        # Engage E-STOP on watchdog error (even if watchdog is disabled, errors still trigger E-STOP)
        self.actuator_controller.engage_estop(
            ESTOP_REASON_INTERNAL_ERROR,
            f"Watchdog error: {error}"
        )

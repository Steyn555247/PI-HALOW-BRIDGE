"""
Watchdog Monitor for Base Pi

Monitors connection health and triggers E-STOP if needed.

SAFETY:
- Watchdog can only ENGAGE E-STOP, never clear it
- Triggers E-STOP if telemetry timeout exceeds threshold
- Logs periodic status for monitoring
"""

import logging
import time
import json
from typing import Callable, Optional

from common.constants import MSG_EMERGENCY_STOP, WATCHDOG_TIMEOUT_S

logger = logging.getLogger(__name__)


class WatchdogMonitor:
    """
    Monitors connection health and safety conditions.

    SAFETY: Can only ENGAGE E-STOP, never clear it.
    """

    def __init__(
        self,
        on_estop_engage: Callable[[str, str], None],
        get_last_telemetry_time: Callable[[], float],
        status_interval: float = 10.0
    ):
        """
        Initialize watchdog monitor.

        Args:
            on_estop_engage: Callback to engage E-STOP (cmd_type, data)
            get_last_telemetry_time: Callback to get last telemetry timestamp
            status_interval: Status logging interval in seconds
        """
        self.on_estop_engage = on_estop_engage
        self.get_last_telemetry_time = get_last_telemetry_time
        self.status_interval = status_interval

        # State
        self.last_status_log = time.time()
        self.estop_sent_for_timeout = False

        logger.info(f"WatchdogMonitor initialized (timeout={WATCHDOG_TIMEOUT_S}s, "
                   f"status_interval={status_interval}s)")

    def check_safety(self):
        """
        Check safety conditions and trigger E-STOP if needed.

        SAFETY: Only ENGAGES E-STOP, never clears it.
        """
        now = time.time()

        # Check telemetry timeout - indicates Robot Pi may be unreachable
        last_telemetry = self.get_last_telemetry_time()
        if last_telemetry > 0:
            telemetry_age = now - last_telemetry

            if telemetry_age > WATCHDOG_TIMEOUT_S:
                if not self.estop_sent_for_timeout:
                    logger.error(f"Telemetry timeout ({telemetry_age:.1f}s), sending E-STOP ENGAGE")
                    self.on_estop_engage(MSG_EMERGENCY_STOP, {
                        'engage': True,
                        'reason': f'base_watchdog_telemetry_timeout_{telemetry_age:.0f}s'
                    })
                    self.estop_sent_for_timeout = True
            else:
                # Telemetry is fresh, reset timeout flag
                self.estop_sent_for_timeout = False

    def log_status(
        self,
        backend_connected: bool,
        control_connected: bool,
        telemetry_connected: bool,
        video_connected: bool,
        robot_estop_state: Optional[bool],
        psk_valid: bool,
        robot_estop_reason: Optional[str] = None
    ):
        """
        Log periodic status for monitoring.

        Args:
            backend_connected: Backend connection state
            control_connected: Control connection state
            telemetry_connected: Telemetry connection state
            video_connected: Video connection state
            robot_estop_state: Robot E-STOP state
            psk_valid: PSK validation state
            robot_estop_reason: Robot E-STOP reason string (from telemetry)
        """
        now = time.time()

        # Log status at configured interval
        if now - self.last_status_log > self.status_interval:
            status = {
                "event": "status",
                "backend": "connected" if backend_connected else "disconnected",
                "control": "connected" if control_connected else "disconnected",
                "telemetry": "connected" if telemetry_connected else "disconnected",
                "video": "connected" if video_connected else "N/A",
                "robot_estop": robot_estop_state,
                "robot_estop_reason": robot_estop_reason,
                "psk_valid": psk_valid
            }
            logger.info(json.dumps(status))
            self.last_status_log = now

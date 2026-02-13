"""
State Manager for Base Pi

Manages bridge state including:
- Camera ID tracking
- E-STOP state from Robot Pi
- RTT measurements
- Health scoring
- Controller telemetry rate limiting
"""

import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages bridge state and health tracking.

    Tracks connection states, E-STOP status, RTT, and provides
    health scoring for monitoring.
    """

    def __init__(self, default_camera_id: int = 0):
        """
        Initialize state manager.

        Args:
            default_camera_id: Default camera ID
        """
        # State tracking
        self.active_camera_id = default_camera_id
        self.backend_connected = False
        self.last_robot_estop_state: Optional[bool] = None
        self.last_robot_estop_reason: Optional[str] = None
        self.last_rtt_ms = 0
        self.last_controller_update = 0.0

        # Heartbeat state for RTT measurement
        self.last_ping_time = 0
        self.last_ping_seq = 0

        # E-STOP deduplication state (prevent multiple commands for same logical event)
        self._last_emergency_status_time = 0.0
        self._last_emergency_command_sent: Optional[bool] = None  # Last command we SENT to robot
        self._emergency_debounce_s = 1.0  # Ignore events within 1 second
        self._emergency_event_id: int = 0  # Increments on each unique event

        logger.info(f"StateManager initialized (camera_id={default_camera_id})")

    def set_backend_connected(self, connected: bool):
        """Set backend connection state."""
        if connected != self.backend_connected:
            logger.info(f"Backend connection state changed: {connected}")
        self.backend_connected = connected

    def is_backend_connected(self) -> bool:
        """Check if backend is connected."""
        return self.backend_connected

    def set_camera_id(self, camera_id: int):
        """Set active camera ID."""
        logger.info(f"Active camera changed: {self.active_camera_id} -> {camera_id}")
        self.active_camera_id = camera_id

    def get_camera_id(self) -> int:
        """Get active camera ID."""
        return self.active_camera_id

    def update_estop_state(self, engaged: Optional[bool], reason: Optional[str] = None):
        """
        Update E-STOP state from Robot Pi telemetry.

        Args:
            engaged: E-STOP engaged state (True/False/None)
            reason: E-STOP reason string from Robot Pi (e.g. 'boot_default', 'watchdog')
        """
        if engaged != self.last_robot_estop_state:
            logger.info(f"Robot E-STOP state changed: {self.last_robot_estop_state} -> {engaged} (reason: {reason})")
        self.last_robot_estop_state = engaged
        if reason is not None:
            self.last_robot_estop_reason = reason

    def get_estop_state(self) -> Optional[bool]:
        """Get last known E-STOP state from Robot Pi."""
        return self.last_robot_estop_state

    def get_estop_reason(self) -> Optional[str]:
        """Get last known E-STOP reason from Robot Pi."""
        return self.last_robot_estop_reason

    def update_rtt(self, ping_seq: int, ping_ts: float) -> Optional[int]:
        """
        Update RTT measurement from pong data.

        Args:
            ping_seq: Ping sequence number from pong
            ping_ts: Original ping timestamp from pong

        Returns:
            RTT in milliseconds if valid, None otherwise
        """
        if ping_seq == self.last_ping_seq and self.last_ping_time > 0:
            now = time.time()
            rtt_ms = int((now - ping_ts) * 1000)

            # Sanity check: 0-10 second range
            if 0 <= rtt_ms < 10000:
                self.last_rtt_ms = rtt_ms
                logger.debug(f"RTT measured: {rtt_ms}ms (ping_seq={ping_seq})")
                return rtt_ms
            else:
                logger.warning(f"RTT out of range: {rtt_ms}ms, ignoring")
        return None

    def get_rtt(self) -> int:
        """Get last measured RTT in milliseconds."""
        return self.last_rtt_ms

    def update_ping_sent(self, seq: int, timestamp: float):
        """
        Record that a ping was sent.

        Args:
            seq: Ping sequence number
            timestamp: Ping send timestamp
        """
        self.last_ping_seq = seq
        self.last_ping_time = timestamp

    def get_next_ping_seq(self) -> int:
        """Get next ping sequence number."""
        self.last_ping_seq += 1
        return self.last_ping_seq

    def should_send_controller_update(self, rate_hz: float) -> bool:
        """
        Check if controller telemetry update should be sent.

        Args:
            rate_hz: Target update rate in Hz

        Returns:
            True if update should be sent
        """
        now = time.time()
        interval = 1.0 / rate_hz if rate_hz > 0 else 1.0

        if now - self.last_controller_update >= interval:
            self.last_controller_update = now
            return True
        return False

    def should_send_emergency_command(self, active: bool, source: str) -> bool:
        """
        Check if emergency command should be sent to robot.

        SIMPLIFIED: Only block exact duplicates, never auto-re-engage.
        E-STOP logic is handled by backend and controller only.

        Args:
            active: E-STOP active state (True=engage, False=clear)
            source: Source of the event for logging

        Returns:
            True if command should be sent to robot
        """
        # Simple state-based dedup: don't send if we already sent the same command
        if self._last_emergency_command_sent == active:
            logger.debug(f"E-STOP: ignoring duplicate {'ENGAGE' if active else 'CLEAR'} from {source}")
            return False

        # New command - allow it
        self._last_emergency_command_sent = active
        self._emergency_event_id += 1

        logger.info(f"E-STOP: forwarding {'ENGAGE' if active else 'CLEAR'} from {source}")
        return True

    def get_last_emergency_command(self) -> Optional[bool]:
        """Get the last emergency command that was sent to robot."""
        return self._last_emergency_command_sent

    def reset_emergency_state(self):
        """Reset emergency state tracking (e.g. on reconnect)."""
        self._last_emergency_command_sent = None
        self._last_emergency_status_time = 0.0
        logger.info("E-STOP state tracking reset")

    def compute_health_score(
        self,
        control_connected: bool,
        telemetry_connected: bool,
        video_connected: bool,
        last_telemetry_age: float,
        watchdog_timeout: float,
        psk_valid: bool
    ) -> int:
        """
        Compute overall health score (0-100).

        Args:
            control_connected: Control connection state
            telemetry_connected: Telemetry connection state
            video_connected: Video connection state
            last_telemetry_age: Age of last telemetry in seconds
            watchdog_timeout: Watchdog timeout threshold
            psk_valid: PSK validation state

        Returns:
            Health score (0-100)
        """
        score = 100

        # Critical: PSK validation
        if not psk_valid:
            score -= 50

        # Connection states
        if not control_connected:
            score -= 20
        if not telemetry_connected:
            score -= 20
        if not video_connected:
            score -= 10

        # Telemetry freshness
        if last_telemetry_age > 0:
            if last_telemetry_age > watchdog_timeout:
                score -= 30
            elif last_telemetry_age > watchdog_timeout / 2:
                score -= 10

        return max(0, score)

    def get_health_status(
        self,
        control_connected: bool,
        telemetry_connected: bool,
        video_connected: bool,
        last_telemetry_age: Optional[float],
        watchdog_timeout: float,
        psk_valid: bool
    ) -> Dict[str, Any]:
        """
        Get comprehensive health status.

        Args:
            control_connected: Control connection state
            telemetry_connected: Telemetry connection state
            video_connected: Video connection state
            last_telemetry_age: Age of last telemetry in seconds (None if no telemetry)
            watchdog_timeout: Watchdog timeout threshold
            psk_valid: PSK validation state

        Returns:
            Health status dictionary
        """
        # Determine if system is healthy
        healthy = (
            control_connected and
            telemetry_connected and
            psk_valid and
            (last_telemetry_age is None or last_telemetry_age <= watchdog_timeout)
        )

        # Compute health score
        telem_age = last_telemetry_age if last_telemetry_age is not None else 0
        score = self.compute_health_score(
            control_connected,
            telemetry_connected,
            video_connected,
            telem_age,
            watchdog_timeout,
            psk_valid
        )

        return {
            'status': 'ok' if healthy else 'degraded',
            'health_score': score,
            'backend_connected': self.backend_connected,
            'control_connected': control_connected,
            'telemetry_connected': telemetry_connected,
            'video_connected': video_connected,
            'robot_estop_engaged': self.last_robot_estop_state,
            'last_telemetry_age_s': last_telemetry_age,
            'psk_valid': psk_valid,
            'last_rtt_ms': self.last_rtt_ms,
            'active_camera_id': self.active_camera_id
        }

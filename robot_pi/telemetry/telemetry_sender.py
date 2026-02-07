"""
Telemetry Sender Module for Robot Pi

Sends telemetry data to Base Pi over TCP.
Robot Pi connects as CLIENT to Base Pi's telemetry receiver.

PHASE 5 OPTIMIZATION:
- Exponential backoff for reconnection (1s → 32s)
- JSON serialization caching (serialize once, reuse for same data)
- Circuit breaker pattern
- TCP keepalive for zombie detection

Telemetry is sent at 10 Hz (100ms interval) with authenticated framing.
"""

import logging
import json
import socket
import time
import sys
import os
from typing import Optional, Dict, Any

# Add project root to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from common.connection_manager import (
    ExponentialBackoff, CircuitBreaker, configure_tcp_keepalive
)
from common.framing import SecureFramer

logger = logging.getLogger(__name__)


class TelemetrySender:
    """
    Telemetry sender for Robot Pi.

    Connects to Base Pi and sends authenticated telemetry at 10 Hz.
    """

    def __init__(
        self,
        base_pi_ip: str,
        telemetry_port: int,
        telemetry_interval: float = 0.1  # 10 Hz
    ):
        """
        Initialize telemetry sender.

        Args:
            base_pi_ip: Base Pi IP address
            telemetry_port: Telemetry port on Base Pi
            telemetry_interval: Time between telemetry sends (default 0.1s = 10 Hz)
        """
        self.base_pi_ip = base_pi_ip
        self.telemetry_port = telemetry_port
        self.telemetry_interval = telemetry_interval

        # Socket
        self.socket: Optional[socket.socket] = None
        self.connected = False

        # Framer for authenticated telemetry
        self.framer = SecureFramer(role="robot_pi_telemetry")

        # Connection health
        self.backoff = ExponentialBackoff(initial=1.0, multiplier=2.0, max_delay=32.0)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=30.0)

        # JSON caching (PHASE 5 optimization)
        self._cached_json: Optional[str] = None
        self._cached_telemetry_id: Optional[int] = None

        # Statistics
        self.sends_total = 0
        self.cache_hits = 0

        logger.info(f"TelemetrySender initialized (target: {base_pi_ip}:{telemetry_port} @ {1.0/telemetry_interval} Hz)")

    def connect(self) -> bool:
        """
        Connect to Base Pi telemetry server.

        Returns:
            True if connected successfully
        """
        try:
            # Check circuit breaker
            if not self.circuit_breaker.allow_request():
                logger.warning("Circuit breaker OPEN - waiting for cooldown")
                return False

            logger.info(f"Connecting to Base Pi telemetry at {self.base_pi_ip}:{self.telemetry_port}")
            self.close()

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.base_pi_ip, self.telemetry_port))

            # Configure TCP keepalive
            configure_tcp_keepalive(self.socket, idle=60, interval=10, count=3)

            self.connected = True

            # Reset backoff on successful connection
            self.backoff.reset()
            self.circuit_breaker.record_success()

            logger.info("Connected to Base Pi telemetry")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Base Pi telemetry: {e}")
            self.close()
            self.circuit_breaker.record_failure()
            return False

    def send_telemetry(self, telemetry: Dict[str, Any]) -> bool:
        """
        Send telemetry to Base Pi.

        PHASE 5: Uses cached JSON serialization for efficiency.

        Args:
            telemetry: Telemetry dictionary to send

        Returns:
            True if sent successfully
        """
        if not self.connected or not self.socket:
            return False

        try:
            # Phase 5: Check JSON cache using object identity
            telemetry_id = id(telemetry)
            if self._cached_telemetry_id == telemetry_id and self._cached_json:
                # Cache hit - reuse serialized JSON
                payload = self._cached_json.encode('utf-8')
                self.cache_hits += 1
            else:
                # Cache miss - serialize and cache
                json_str = json.dumps(telemetry)
                payload = json_str.encode('utf-8')
                self._cached_json = json_str
                self._cached_telemetry_id = telemetry_id

            # Create authenticated frame
            frame = self.framer.create_frame(payload)

            # Send frame
            self.socket.sendall(frame)
            self.sends_total += 1

            logger.debug(f"Sent telemetry (cache hit: {self._cached_telemetry_id == telemetry_id})")

            # Record success for circuit breaker
            self.circuit_breaker.record_success()

            return True

        except Exception as e:
            logger.error(f"Failed to send telemetry: {e}")
            self.close()
            self.circuit_breaker.record_failure()
            return False

    def close(self):
        """Close telemetry socket."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.connected = False

    def is_connected(self) -> bool:
        """Check if connected to Base Pi."""
        return self.connected

    def get_backoff_delay(self) -> float:
        """
        Get next backoff delay for reconnection.

        Returns:
            Delay in seconds before next reconnect attempt
        """
        return self.backoff.next_delay()

    def get_health(self) -> dict:
        """
        Get telemetry sender health metrics.

        Returns:
            Dictionary with health metrics
        """
        return {
            'connected': self.connected,
            'sends_total': self.sends_total,
            'cache_hits': self.cache_hits,
            'cache_hit_ratio': self.cache_hits / max(1, self.sends_total) if self.sends_total > 0 else 0.0,
            'circuit_breaker_state': self.circuit_breaker.state.value,
            'circuit_breaker_failures': self.circuit_breaker.failure_count
        }

    def get_interval(self) -> float:
        """Get telemetry send interval."""
        return self.telemetry_interval

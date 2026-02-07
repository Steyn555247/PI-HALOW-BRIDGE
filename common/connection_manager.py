"""
Connection Management Utilities

Provides robust connection management patterns:
- Exponential backoff for reconnection attempts
- Circuit breaker pattern to prevent hammering failed services
- Server socket creation with SO_REUSEADDR
- TCP keepalive configuration for zombie connection detection

Created for Phase 1 foundation utilities.
"""

import socket
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    """
    Exponential backoff delay calculator.

    Implements exponential backoff with configurable parameters:
    - initial: Starting delay (default 1.0s)
    - multiplier: Delay multiplier on each failure (default 2.0)
    - max_delay: Maximum delay cap (default 32.0s)

    Example delays: 1s, 2s, 4s, 8s, 16s, 32s (capped)
    """

    def __init__(self, initial: float = 1.0, multiplier: float = 2.0, max_delay: float = 32.0):
        """
        Initialize exponential backoff.

        Args:
            initial: Initial delay in seconds
            multiplier: Delay multiplier on each failure
            max_delay: Maximum delay cap in seconds
        """
        self.initial = initial
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.current_delay = initial

    def next_delay(self) -> float:
        """
        Get next backoff delay and advance state.

        Returns:
            Delay in seconds to wait before next attempt
        """
        delay = self.current_delay
        self.current_delay = min(self.current_delay * self.multiplier, self.max_delay)
        return delay

    def reset(self):
        """Reset backoff to initial delay (call on successful connection)."""
        self.current_delay = self.initial


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents hammering a failing service by:
    - Tracking consecutive failures
    - Opening circuit after failure_threshold failures
    - Blocking requests while circuit is OPEN (for timeout seconds)
    - Allowing test request in HALF_OPEN state
    - Closing circuit on successful request

    States:
    - CLOSED: Normal operation (requests allowed)
    - OPEN: Too many failures (requests blocked)
    - HALF_OPEN: Testing recovery (one request allowed)
    """

    def __init__(self, failure_threshold: int = 5, timeout: float = 30.0):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery (OPEN -> HALF_OPEN)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def allow_request(self) -> bool:
        """
        Check if request should be allowed.

        Returns:
            True if request should proceed, False if blocked by circuit breaker
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout expired -> transition to HALF_OPEN
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info("Circuit breaker transitioning to HALF_OPEN (testing recovery)")
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow one test request
            return True

        return False

    def record_success(self):
        """Record successful request (resets failure count, closes circuit)."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker transitioning to CLOSED (recovery successful)")

        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        """Record failed request (increments failure count, may open circuit)."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Test failed, reopen circuit
            logger.warning("Circuit breaker reopening (recovery test failed)")
            self.state = CircuitState.OPEN
            return

        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(f"Circuit breaker OPEN ({self.failure_count} failures, will retry after {self.timeout}s)")
            self.state = CircuitState.OPEN


def create_server_socket(host: str, port: int, backlog: int = 5, timeout: Optional[float] = None) -> socket.socket:
    """
    Create TCP server socket with SO_REUSEADDR enabled.

    This prevents "Address already in use" errors when restarting services quickly.
    The SO_REUSEADDR option allows rebinding to a port in TIME_WAIT state.

    Args:
        host: Host address to bind (e.g., '0.0.0.0' for all interfaces)
        port: Port number to bind
        backlog: Maximum queued connections (default 5)
        timeout: Optional accept timeout in seconds (default None = blocking)

    Returns:
        Configured server socket ready to accept connections

    Raises:
        OSError: If socket creation or binding fails
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Enable SO_REUSEADDR to prevent "Address already in use" errors
    # This allows rebinding to a port in TIME_WAIT state after a restart
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind and listen
    sock.bind((host, port))
    sock.listen(backlog)

    if timeout is not None:
        sock.settimeout(timeout)

    logger.debug(f"Server socket created: {host}:{port} (SO_REUSEADDR enabled)")
    return sock


def configure_tcp_keepalive(sock: socket.socket, idle: int = 60, interval: int = 10, count: int = 3):
    """
    Configure TCP keepalive for zombie connection detection.

    TCP keepalive sends periodic probes to detect dead connections:
    - idle: Seconds of idle time before first probe
    - interval: Seconds between probes
    - count: Number of probes before declaring connection dead

    Total detection time: idle + (interval * count)
    Example: 60 + (10 * 3) = 90 seconds to detect zombie connection

    Args:
        sock: Socket to configure
        idle: Idle time in seconds before first keepalive probe (default 60)
        interval: Interval in seconds between keepalive probes (default 10)
        count: Number of failed probes before declaring connection dead (default 3)
    """
    # Enable TCP keepalive
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    # Configure keepalive parameters (Linux-specific)
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, count)
        logger.debug(f"TCP keepalive configured: idle={idle}s, interval={interval}s, count={count} (detection={idle + interval * count}s)")
    except (OSError, AttributeError):
        # Platform doesn't support these options (e.g., Windows)
        logger.warning("TCP keepalive detailed configuration not supported on this platform")

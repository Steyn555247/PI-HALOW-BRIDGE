"""
Control Server Module for Robot Pi

Receives control commands from Base Pi over TCP.
Robot Pi runs as the SERVER, Base Pi's control_forwarder connects as the CLIENT.

PHASE 5 OPTIMIZATION:
- Reduced timeouts for <2s failover (0.5s accept, 1.0s read, down from 2.0s + 5.0s)
- Exponential backoff (1s → 32s)
- Circuit breaker pattern
- TCP keepalive for zombie detection

SAFETY-CRITICAL:
- Any error triggers E-STOP via callback
- Authentication required for all commands (via SecureFramer)
- Replay protection via sequence numbers
- Control timeout monitored by watchdog
"""

import logging
import socket
import time
import sys
import os
from typing import Optional, Callable

# Add project root to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from common.connection_manager import (
    create_server_socket, ExponentialBackoff, CircuitBreaker,
    configure_tcp_keepalive
)
from common.framing import SecureFramer, FramingError, AuthenticationError, ReplayError
from common.constants import (
    ESTOP_REASON_AUTH_FAILURE, ESTOP_REASON_DISCONNECT,
    ESTOP_REASON_DECODE_ERROR, ESTOP_REASON_INTERNAL_ERROR
)

logger = logging.getLogger(__name__)


class ControlServer:
    """
    Control server for Robot Pi - receives commands from Base Pi.

    Robot Pi acts as TCP server, Base Pi connects as client.
    """

    def __init__(
        self,
        port: int,
        framer: SecureFramer,
        on_command_received: Callable[[bytes, int], None],
        on_estop_trigger: Callable[[str, str], None],
        on_auth_success: Optional[Callable[[], None]] = None
    ):
        """
        Initialize control server.

        Args:
            port: Port to listen on
            framer: SecureFramer instance for authenticated framing
            on_command_received: Callback(payload, seq) when command received
            on_estop_trigger: Callback(reason_code, message) to trigger E-STOP
            on_auth_success: Optional callback when authentication succeeds (for clearing auth_failure E-STOP)
        """
        self.port = port
        self.framer = framer
        self.on_command_received = on_command_received
        self.on_estop_trigger = on_estop_trigger
        self.on_auth_success = on_auth_success

        # Server socket
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None

        # Connection state
        self.connected = False
        self.control_established = False  # True once first valid command received
        self.last_control_time = time.time()
        self.last_control_seq = 0

        # Connection health
        self.backoff = ExponentialBackoff(initial=1.0, multiplier=2.0, max_delay=32.0)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=30.0)

        # Logging throttle
        self._last_accept_log = 0.0

        logger.info("ControlServer initialized (Phase 5: <2s failover)")

    def start_server(self) -> bool:
        """
        Start control server to accept connections from Base Pi.

        PHASE 5 FIX: Uses create_server_socket() with SO_REUSEADDR.

        Returns:
            True if server started successfully
        """
        try:
            if self.server_socket:
                return True  # Already started

            logger.info(f"Starting control server on port {self.port}")

            # Use connection_manager helper (includes SO_REUSEADDR)
            self.server_socket = create_server_socket(
                host='0.0.0.0',
                port=self.port,
                backlog=1,
                timeout=0.5  # PHASE 5 FIX: 2.0s → 0.5s for faster failover
            )

            logger.info(f"Control server listening on 0.0.0.0:{self.port} (accept timeout: 0.5s)")
            return True

        except OSError as e:
            if e.errno == 10048 or 'Address already in use' in str(e):
                logger.error(f"Port {self.port} already in use. Previous process may still be running.")
            else:
                logger.error(f"Failed to start control server: {e}")
            self.close_server()
            return False

        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            self.close_server()
            return False

    def accept_connection(self) -> bool:
        """
        Accept a control connection from Base Pi.

        PHASE 5 FIX: Uses 0.5s accept timeout (down from 2.0s).

        Returns:
            True if connection accepted successfully
        """
        try:
            if not self.server_socket:
                if not self.start_server():
                    time.sleep(1.0)
                    return False

            # Close any existing client connection
            self.close_client()

            # Log periodically so we can see accept is running
            if time.time() - self._last_accept_log > 10.0:
                logger.info("Control server: waiting for Base Pi connection...")
                self._last_accept_log = time.time()

            client_sock, addr = self.server_socket.accept()

            # PHASE 5 FIX: 5.0s → 1.0s for faster failover
            client_sock.settimeout(1.0)

            # Configure TCP keepalive
            configure_tcp_keepalive(client_sock, idle=60, interval=10, count=3)

            self.client_socket = client_sock
            self.connected = True

            # Reset backoff on successful connection
            self.backoff.reset()
            self.circuit_breaker.record_success()

            logger.info(f"Accepted control connection from {addr} (read timeout: 1.0s)")
            return True

        except socket.timeout:
            # Normal - no connection yet, continue loop
            return False

        except OSError as e:
            # Handle "bad file descriptor" after server socket closed
            if e.errno == 9 or e.errno == 10038:  # EBADF or WSAENOTSOCK
                logger.warning("Control server socket closed, will restart")
                self.close_server()
            else:
                logger.error(f"Error accepting control connection: {e}")
                self.close_client()
            return False

        except Exception as e:
            logger.error(f"Error accepting control connection: {e}")
            self.close_client()
            return False

    def receive_command(self) -> bool:
        """
        Receive and process one control command.

        Returns:
            True if command received and processed successfully
        """
        if not self.connected or not self.client_socket:
            return False

        try:
            # Check circuit breaker
            if not self.circuit_breaker.allow_request():
                logger.warning("Circuit breaker OPEN - waiting for cooldown")
                self.close_client()
                return False

            # Receive authenticated frame
            try:
                payload, seq = self.framer.read_frame_from_socket(
                    self.client_socket,
                    timeout=1.0
                )

                # Update control timing
                self.last_control_time = time.time()
                self.last_control_seq = seq

                if not self.control_established:
                    self.control_established = True
                    logger.info(f"Control ESTABLISHED (seq={seq})")

                # Call command callback
                self.on_command_received(payload, seq)

                # Record success for circuit breaker
                self.circuit_breaker.record_success()

                # Notify auth success (for clearing auth_failure E-STOP)
                if self.on_auth_success:
                    self.on_auth_success()

                return True

            except socket.timeout:
                # Normal timeout, no command received
                return False

            except AuthenticationError as e:
                logger.error(f"Authentication FAILED: {e}")
                self.on_estop_trigger(ESTOP_REASON_AUTH_FAILURE, str(e))
                self.circuit_breaker.record_failure()
                self.close_client()
                return False

            except ReplayError as e:
                logger.error(f"Replay attack detected: {e}")
                self.on_estop_trigger(ESTOP_REASON_AUTH_FAILURE, f"Replay: {e}")
                self.circuit_breaker.record_failure()
                self.close_client()
                return False

            except FramingError as e:
                logger.error(f"Framing error: {e}")
                self.on_estop_trigger(ESTOP_REASON_DECODE_ERROR, str(e))
                self.circuit_breaker.record_failure()
                self.close_client()
                return False

            except ConnectionError as e:
                logger.warning(f"Control connection lost: {e}")
                self.on_estop_trigger(ESTOP_REASON_DISCONNECT, str(e))
                self.circuit_breaker.record_failure()
                self.close_client()
                return False

            except UnicodeDecodeError as e:
                logger.error(f"Unicode decode error: {e}")
                self.on_estop_trigger(ESTOP_REASON_DECODE_ERROR, str(e))
                self.circuit_breaker.record_failure()
                self.close_client()
                return False

        except Exception as e:
            logger.error(f"Unexpected error receiving command: {e}")
            self.on_estop_trigger(ESTOP_REASON_INTERNAL_ERROR, str(e))
            self.circuit_breaker.record_failure()
            self.close_client()
            return False

    def close_client(self):
        """Close client connection (keeps server open)."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        self.connected = False

    def close_server(self):
        """Close server and client sockets."""
        self.close_client()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.connected

    def is_control_established(self) -> bool:
        """Check if control has been established (first command received)."""
        return self.control_established

    def get_last_control_time(self) -> float:
        """Get timestamp of last control command."""
        return self.last_control_time

    def get_last_control_seq(self) -> int:
        """Get sequence number of last control command."""
        return self.last_control_seq

    def get_control_age(self) -> float:
        """Get age of last control command in seconds."""
        return time.time() - self.last_control_time

    def get_health(self) -> dict:
        """
        Get control server health metrics.

        Returns:
            Dictionary with health metrics
        """
        return {
            'connected': self.connected,
            'control_established': self.control_established,
            'control_age_s': self.get_control_age(),
            'last_control_seq': self.last_control_seq,
            'circuit_breaker_state': self.circuit_breaker.state.value,
            'circuit_breaker_failures': self.circuit_breaker.failure_count
        }

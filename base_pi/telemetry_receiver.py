"""
Telemetry Receiver - Receives authenticated sensor data from Robot Pi

SAFETY:
- Bounded receive buffer to prevent OOM
- HMAC authentication on all telemetry
- Decode errors are logged and cause reconnect
"""

import socket
import json
import time
import logging
import threading
import os
import sys
from typing import Optional, Dict, Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.framing import SecureFramer, FramingError, AuthenticationError, ReplayError
from common.constants import MAX_CONTROL_BUFFER

logger = logging.getLogger(__name__)


class TelemetryReceiver:
    """Receives authenticated telemetry data from Robot Pi over TCP"""

    def __init__(self, telemetry_port: int,
                 on_telemetry: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.telemetry_port = telemetry_port
        self.on_telemetry = on_telemetry

        self.framer = SecureFramer(role="base_pi_telemetry_rx")

        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.running = False
        self.connected = False
        self.last_telemetry_time = 0

        self.receive_thread: Optional[threading.Thread] = None

        # Statistics
        self.messages_received = 0
        self.auth_failures = 0
        self.decode_errors = 0

        logger.info(f"TelemetryReceiver initialized on port {telemetry_port}")

    def start(self):
        """Start listening for telemetry"""
        self.running = True

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.telemetry_port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            logger.info(f"Listening for telemetry on port {self.telemetry_port}")
        except Exception as e:
            logger.error(f"Failed to start telemetry server: {e}")
            return

        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

        logger.info("TelemetryReceiver started")

    def stop(self):
        """Stop receiving telemetry"""
        self.running = False

        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None

        if self.receive_thread:
            self.receive_thread.join(timeout=2.0)

        logger.info(f"TelemetryReceiver stopped (received={self.messages_received}, "
                   f"auth_fail={self.auth_failures}, decode_err={self.decode_errors})")

    def _receive_loop(self):
        """Main receive loop with authenticated framing"""
        while self.running:
            try:
                # Accept connection if not connected
                if not self.connected:
                    try:
                        logger.info("Waiting for Robot Pi telemetry connection...")
                        self.client_socket, addr = self.server_socket.accept()

                        # PRIORITY: Low-latency and fast dead connection detection
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)

                        self.client_socket.settimeout(3.0)  # Reduced for faster failure detection
                        self.connected = True
                        # Reset framer sequence for new connection
                        self.framer = SecureFramer(role="base_pi_telemetry_rx")
                        logger.info(f"Robot Pi telemetry connected from {addr}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Error accepting telemetry connection: {e}")
                        time.sleep(1.0)
                        continue

                # Receive authenticated frame
                try:
                    payload, seq = self.framer.read_frame_from_socket(
                        self.client_socket, timeout=5.0
                    )
                    self._process_telemetry(payload, seq)

                except socket.timeout:
                    continue

                except AuthenticationError as e:
                    logger.error(f"Telemetry auth FAILED: {e}")
                    self.auth_failures += 1
                    self._disconnect_client()

                except ReplayError as e:
                    logger.error(f"Telemetry replay detected: {e}")
                    self.auth_failures += 1
                    self._disconnect_client()

                except FramingError as e:
                    logger.error(f"Telemetry framing error: {e}")
                    self.decode_errors += 1
                    self._disconnect_client()

                except ConnectionError as e:
                    logger.warning(f"Telemetry connection lost: {e}")
                    self._disconnect_client()

            except Exception as e:
                logger.error(f"Unexpected error in telemetry receive loop: {e}")
                self._disconnect_client()
                time.sleep(1.0)

    def _disconnect_client(self):
        """Disconnect current client"""
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

    def _process_telemetry(self, payload: bytes, seq: int):
        """Process received telemetry frame"""
        try:
            message = payload.decode('utf-8')
            telemetry = json.loads(message)
        except UnicodeDecodeError as e:
            logger.error(f"Telemetry decode error: {e}")
            self.decode_errors += 1
            return
        except json.JSONDecodeError as e:
            logger.error(f"Telemetry JSON error: {e}")
            self.decode_errors += 1
            return

        self.last_telemetry_time = time.time()
        self.messages_received += 1

        # Call callback if provided
        if self.on_telemetry:
            try:
                self.on_telemetry(telemetry)
            except Exception as e:
                logger.error(f"Telemetry callback error: {e}")

        logger.debug(f"Telemetry received: seq={seq}, estop={telemetry.get('estop', {}).get('engaged')}")

    def is_connected(self) -> bool:
        """Check if Robot Pi telemetry is connected"""
        return self.connected

    def get_last_telemetry_time(self) -> float:
        """Get timestamp of last received telemetry"""
        return self.last_telemetry_time

    def get_stats(self) -> dict:
        """Get receiver statistics"""
        return {
            'messages_received': self.messages_received,
            'auth_failures': self.auth_failures,
            'decode_errors': self.decode_errors,
            'recv_seq': self.framer.get_recv_seq()
        }

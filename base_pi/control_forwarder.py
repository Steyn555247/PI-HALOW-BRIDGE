"""
Control Forwarder - Forwards authenticated control commands to Robot Pi

SAFETY:
- All commands are authenticated with HMAC-SHA256
- Sequence numbers prevent replay attacks
- Socket timeouts prevent indefinite blocking
"""

import socket
import json
import time
import logging
import threading
import os
import sys
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.framing import SecureFramer, FramingError

logger = logging.getLogger(__name__)


class ControlForwarder:
    """Forwards authenticated control commands to Robot Pi over TCP"""

    def __init__(self, robot_ip: str, control_port: int, reconnect_delay: float = 0.5,
                 framer: Optional[SecureFramer] = None):
        self.robot_ip = robot_ip
        self.control_port = control_port
        self.reconnect_delay = reconnect_delay  # Reduced for faster recovery

        # Use provided framer or create new one
        self.framer = framer or SecureFramer(role="base_pi_control")

        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.lock = threading.Lock()

        # Track send statistics
        self.commands_sent = 0
        self.commands_failed = 0

        logger.info(f"ControlForwarder initialized for {robot_ip}:{control_port}")

    def connect(self) -> bool:
        """Establish connection to Robot Pi"""
        try:
            with self.lock:
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass

                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # PRIORITY: Disable Nagle's algorithm for low-latency control
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                # Enable TCP keepalive for faster dead connection detection
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                # Linux-specific keepalive settings (in seconds)
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)   # Start after 5s idle
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)  # Probe every 2s
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)    # 3 probes before dead

                self.socket.settimeout(5.0)
                self.socket.connect((self.robot_ip, self.control_port))
                # Keep timeout for all operations - prevent indefinite blocking
                self.socket.settimeout(3.0)  # Reduced from 5s for faster failure detection

                self.connected = True
                logger.info(f"Connected to Robot Pi at {self.robot_ip}:{self.control_port}")
                return True

        except Exception as e:
            logger.error(f"Failed to connect to Robot Pi: {e}")
            self.connected = False
            with self.lock:
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
            return False

    def disconnect(self):
        """Disconnect from Robot Pi"""
        with self.lock:
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
        logger.info("Disconnected from Robot Pi")

    def send_command(self, command_type: str, data: Dict[str, Any] = None) -> bool:
        """
        Send an authenticated control command to Robot Pi.

        Args:
            command_type: Command type (e.g., 'emergency_stop', 'clamp_close')
            data: Command data dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.connected:
            logger.warning(f"Not connected, cannot send command: {command_type}")
            self.commands_failed += 1
            return False

        if not self.framer.is_authenticated():
            logger.error(f"Cannot send command {command_type}: No PSK configured")
            self.commands_failed += 1
            return False

        message = {
            "type": command_type,
            "data": data or {},
            "timestamp": time.time()
        }

        try:
            with self.lock:
                if self.socket:
                    # Create authenticated frame
                    payload = json.dumps(message).encode('utf-8')
                    frame = self.framer.create_frame(payload)

                    self.socket.sendall(frame)
                    self.commands_sent += 1
                    logger.debug(f"Sent command: {command_type} (seq={self.framer.get_send_seq()})")
                    return True
                else:
                    logger.warning("Socket is None, cannot send command")
                    self.commands_failed += 1
                    return False

        except FramingError as e:
            logger.error(f"Framing error for {command_type}: {e}")
            self.commands_failed += 1
            return False

        except Exception as e:
            logger.error(f"Failed to send command {command_type}: {e}")
            self.connected = False
            self.commands_failed += 1
            return False

    def start(self):
        """Start the control forwarder with auto-reconnect"""
        self.running = True

        def reconnect_thread():
            while self.running:
                if not self.connected:
                    logger.info("Attempting to connect to Robot Pi...")
                    if self.connect():
                        logger.info("Connection established")
                    else:
                        logger.warning(f"Connection failed, retrying in {self.reconnect_delay}s")
                        time.sleep(self.reconnect_delay)
                else:
                    time.sleep(1.0)

        self.reconnect_thread = threading.Thread(target=reconnect_thread, daemon=True)
        self.reconnect_thread.start()

        logger.info("ControlForwarder started")

    def stop(self):
        """Stop the control forwarder"""
        self.running = False
        self.disconnect()
        logger.info(f"ControlForwarder stopped (sent={self.commands_sent}, failed={self.commands_failed})")

    def is_connected(self) -> bool:
        """Check if connected to Robot Pi"""
        return self.connected

    def get_stats(self) -> dict:
        """Get command statistics"""
        return {
            'commands_sent': self.commands_sent,
            'commands_failed': self.commands_failed,
            'send_seq': self.framer.get_send_seq()
        }

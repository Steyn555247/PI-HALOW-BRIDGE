"""
Secure framing with HMAC-SHA256 authentication and anti-replay.

Frame format:
  +------------------+------------------+------------------+------------------+
  | Length (2B BE)   | Sequence (8B BE) | HMAC-SHA256 (32B)| Payload (N bytes)|
  +------------------+------------------+------------------+------------------+

HMAC covers: length(2) + seq(8) + payload(N)

Security properties:
- Authentication: HMAC-SHA256 with pre-shared key
- Anti-replay: Strictly monotonic sequence numbers
- Integrity: HMAC covers entire frame content
"""

import hmac
import hashlib
import struct
import os
import logging
import threading
from typing import Optional, Tuple

from .constants import MAX_FRAME_SIZE

logger = logging.getLogger(__name__)

HEADER_SIZE = 2 + 8 + 32  # length + seq + hmac = 42 bytes


class FramingError(Exception):
    """Base exception for framing errors"""
    pass


class AuthenticationError(FramingError):
    """HMAC verification failed"""
    pass


class ReplayError(FramingError):
    """Sequence number replay detected"""
    pass


class FrameSizeError(FramingError):
    """Frame exceeds maximum size"""
    pass


class SecureFramer:
    """
    Handles secure framing with HMAC authentication and anti-replay.

    Thread-safety: All sequence number operations are protected by locks.
    Safe to use from multiple threads.
    """

    def __init__(self, psk_hex: Optional[str] = None, role: str = "unknown"):
        """
        Initialize framer with pre-shared key.

        Args:
            psk_hex: 64 hex characters (32 bytes). If None, reads from SERPENT_PSK_HEX env.
            role: Identifier for logging ("base_pi" or "robot_pi")
        """
        self.role = role
        self.psk: Optional[bytes] = None
        self.psk_valid = False

        # Sequence tracking with thread safety
        self._send_seq = 0
        self._recv_seq = 0  # Last accepted sequence
        self._send_lock = threading.Lock()
        self._recv_lock = threading.Lock()

        # Load PSK
        psk_source = psk_hex or os.getenv('SERPENT_PSK_HEX')
        if psk_source:
            try:
                self.psk = bytes.fromhex(psk_source)
                if len(self.psk) != 32:
                    logger.critical(f"[{role}] PSK must be 32 bytes (64 hex chars), got {len(self.psk)}")
                    self.psk = None
                else:
                    self.psk_valid = True
                    logger.info(f"[{role}] PSK loaded successfully")
            except ValueError as e:
                logger.critical(f"[{role}] Invalid PSK hex: {e}")
                self.psk = None
        else:
            logger.critical(f"[{role}] NO PSK CONFIGURED - SERPENT_PSK_HEX not set")
            logger.critical(f"[{role}] Robot will refuse to clear E-STOP without valid PSK")

    def is_authenticated(self) -> bool:
        """Check if PSK is configured and valid"""
        return self.psk_valid and self.psk is not None

    def create_frame(self, payload: bytes) -> bytes:
        """
        Create an authenticated frame.

        Args:
            payload: Raw payload bytes (typically JSON)

        Returns:
            Complete frame ready to send

        Raises:
            FrameSizeError: If payload exceeds MAX_FRAME_SIZE
            AuthenticationError: If PSK not configured
        """
        if not self.is_authenticated():
            raise AuthenticationError("Cannot create frame: PSK not configured")

        if len(payload) > MAX_FRAME_SIZE:
            raise FrameSizeError(f"Payload {len(payload)} exceeds max {MAX_FRAME_SIZE}")

        # Thread-safe sequence increment
        with self._send_lock:
            self._send_seq += 1
            seq = self._send_seq

        # Pack header (length + seq)
        length = len(payload)
        header = struct.pack('>HQ', length, seq)

        # Compute HMAC over header + payload
        mac = hmac.new(self.psk, header + payload, hashlib.sha256).digest()

        return header + mac + payload

    def parse_frame(self, data: bytes) -> Tuple[bytes, int]:
        """
        Parse and verify an authenticated frame.

        Args:
            data: Raw frame data (must be complete frame)

        Returns:
            Tuple of (payload, sequence_number)

        Raises:
            FramingError: If frame is malformed
            AuthenticationError: If HMAC verification fails
            ReplayError: If sequence number is not strictly increasing
            FrameSizeError: If frame exceeds limits
        """
        if not self.is_authenticated():
            raise AuthenticationError("Cannot parse frame: PSK not configured")

        if len(data) < HEADER_SIZE:
            raise FramingError(f"Frame too short: {len(data)} < {HEADER_SIZE}")

        # Unpack header
        length, seq = struct.unpack('>HQ', data[:10])
        received_mac = data[10:42]

        # Validate length
        if length > MAX_FRAME_SIZE:
            raise FrameSizeError(f"Frame length {length} exceeds max {MAX_FRAME_SIZE}")

        expected_total = HEADER_SIZE + length
        if len(data) < expected_total:
            raise FramingError(f"Incomplete frame: got {len(data)}, need {expected_total}")

        payload = data[42:42 + length]

        # Verify HMAC
        header = data[:10]
        expected_mac = hmac.new(self.psk, header + payload, hashlib.sha256).digest()

        if not hmac.compare_digest(received_mac, expected_mac):
            logger.warning(f"[{self.role}] HMAC verification FAILED for seq={seq}")
            raise AuthenticationError("HMAC verification failed")

        # Anti-replay: strictly monotonic (thread-safe)
        with self._recv_lock:
            if seq <= self._recv_seq:
                logger.warning(f"[{self.role}] Replay detected: seq={seq} <= last={self._recv_seq}")
                raise ReplayError(f"Sequence {seq} not greater than {self._recv_seq}")
            self._recv_seq = seq

        return payload, seq

    def read_frame_from_socket(self, sock, timeout: float = 5.0) -> Tuple[bytes, int]:
        """
        Read a complete frame from a socket.

        Args:
            sock: Socket to read from
            timeout: Read timeout in seconds

        Returns:
            Tuple of (payload, sequence_number)

        Raises:
            Various FramingError subclasses on failure
            ConnectionError on socket issues
        """
        sock.settimeout(timeout)

        # Read header
        header_data = self._recv_exact(sock, HEADER_SIZE)
        length, seq = struct.unpack('>HQ', header_data[:10])

        if length > MAX_FRAME_SIZE:
            raise FrameSizeError(f"Frame length {length} exceeds max {MAX_FRAME_SIZE}")

        # Read payload
        payload = self._recv_exact(sock, length) if length > 0 else b''

        # Verify HMAC
        if not self.is_authenticated():
            raise AuthenticationError("PSK not configured")

        received_mac = header_data[10:42]
        expected_mac = hmac.new(self.psk, header_data[:10] + payload, hashlib.sha256).digest()

        if not hmac.compare_digest(received_mac, expected_mac):
            logger.warning(f"[{self.role}] HMAC verification FAILED for seq={seq}")
            raise AuthenticationError("HMAC verification failed")

        # Anti-replay (thread-safe)
        with self._recv_lock:
            if seq <= self._recv_seq:
                logger.warning(f"[{self.role}] Replay: seq={seq} <= last={self._recv_seq}")
                raise ReplayError(f"Sequence {seq} not greater than {self._recv_seq}")
            self._recv_seq = seq

        return payload, seq

    def _recv_exact(self, sock, n: int) -> bytes:
        """Receive exactly n bytes from socket"""
        data = b''
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Socket closed while reading frame")
            data += chunk
        return data

    def get_send_seq(self) -> int:
        """Get current send sequence number (thread-safe)"""
        with self._send_lock:
            return self._send_seq

    def get_recv_seq(self) -> int:
        """Get last received sequence number (thread-safe)"""
        with self._recv_lock:
            return self._recv_seq


def create_unauthenticated_frame(payload: bytes) -> bytes:
    """
    Create a frame without authentication (for video only).
    Uses zero HMAC to indicate unauthenticated.

    WARNING: Do not use for control messages.
    """
    if len(payload) > MAX_FRAME_SIZE * 4:  # Allow larger for video
        raise FrameSizeError(f"Payload too large: {len(payload)}")

    length = len(payload)
    header = struct.pack('>HQ', length, 0)  # seq=0 for unauthenticated
    mac = b'\x00' * 32  # Zero MAC indicates unauthenticated
    return header + mac + payload

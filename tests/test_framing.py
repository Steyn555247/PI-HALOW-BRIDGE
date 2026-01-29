"""
Tests for secure framing module.

Tests HMAC authentication, anti-replay protection, and frame parsing.
"""

import unittest
import os
import sys
import struct

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.framing import (
    SecureFramer, FramingError, AuthenticationError, ReplayError, FrameSizeError,
    HEADER_SIZE
)
from common.constants import MAX_FRAME_SIZE


# Test PSK (32 bytes = 64 hex chars)
TEST_PSK = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


class TestSecureFramer(unittest.TestCase):
    """Test SecureFramer HMAC and framing"""

    def setUp(self):
        """Create framers for testing"""
        self.sender = SecureFramer(psk_hex=TEST_PSK, role="sender")
        self.receiver = SecureFramer(psk_hex=TEST_PSK, role="receiver")

    def test_psk_loaded(self):
        """Test PSK loads correctly"""
        self.assertTrue(self.sender.is_authenticated())
        self.assertTrue(self.receiver.is_authenticated())

    def test_invalid_psk_length(self):
        """Test invalid PSK length is rejected"""
        framer = SecureFramer(psk_hex="0123456789", role="test")  # Too short
        self.assertFalse(framer.is_authenticated())

    def test_invalid_psk_hex(self):
        """Test invalid hex is rejected"""
        framer = SecureFramer(psk_hex="ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ", role="test")
        self.assertFalse(framer.is_authenticated())

    def test_no_psk_configured(self):
        """Test framer without PSK cannot create frames"""
        # Temporarily unset env var if it exists
        old_psk = os.environ.get('SERPENT_PSK_HEX')
        if old_psk:
            del os.environ['SERPENT_PSK_HEX']

        try:
            framer = SecureFramer(psk_hex=None, role="test")
            self.assertFalse(framer.is_authenticated())

            with self.assertRaises(AuthenticationError):
                framer.create_frame(b"test")
        finally:
            if old_psk:
                os.environ['SERPENT_PSK_HEX'] = old_psk

    def test_roundtrip(self):
        """Test frame creation and parsing roundtrip"""
        payload = b'{"type": "test", "data": 123}'
        frame = self.sender.create_frame(payload)

        parsed_payload, seq = self.receiver.parse_frame(frame)
        self.assertEqual(parsed_payload, payload)
        self.assertEqual(seq, 1)

    def test_multiple_frames_monotonic(self):
        """Test sequence numbers are strictly monotonic"""
        for i in range(1, 10):
            frame = self.sender.create_frame(f"message {i}".encode())
            payload, seq = self.receiver.parse_frame(frame)
            self.assertEqual(seq, i)

    def test_replay_attack_rejected(self):
        """Test replay of old frame is rejected"""
        frame1 = self.sender.create_frame(b"first")
        frame2 = self.sender.create_frame(b"second")

        # Parse frame2 first (seq=2)
        self.receiver.parse_frame(frame2)

        # Now try to parse frame1 (seq=1) - should be rejected
        with self.assertRaises(ReplayError):
            self.receiver.parse_frame(frame1)

    def test_replay_same_seq_rejected(self):
        """Test replaying the same frame is rejected"""
        frame = self.sender.create_frame(b"test")

        # First parse succeeds
        self.receiver.parse_frame(frame)

        # Second parse fails (same seq)
        with self.assertRaises(ReplayError):
            self.receiver.parse_frame(frame)

    def test_hmac_tampering_rejected(self):
        """Test tampered frame is rejected"""
        frame = self.sender.create_frame(b"test payload")

        # Tamper with payload (last byte)
        tampered = frame[:-1] + bytes([frame[-1] ^ 0xFF])

        with self.assertRaises(AuthenticationError):
            self.receiver.parse_frame(tampered)

    def test_hmac_tampering_header_rejected(self):
        """Test tampered header is rejected"""
        frame = self.sender.create_frame(b"test payload")

        # Tamper with length field
        tampered = bytes([0xFF, 0xFF]) + frame[2:]

        with self.assertRaises((AuthenticationError, FrameSizeError)):
            self.receiver.parse_frame(tampered)

    def test_wrong_psk_rejected(self):
        """Test frame with wrong PSK is rejected"""
        wrong_psk = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        wrong_sender = SecureFramer(psk_hex=wrong_psk, role="wrong")

        frame = wrong_sender.create_frame(b"test")

        with self.assertRaises(AuthenticationError):
            self.receiver.parse_frame(frame)

    def test_truncated_frame_rejected(self):
        """Test truncated frame is rejected"""
        frame = self.sender.create_frame(b"test payload")

        # Truncate to just header
        with self.assertRaises(FramingError):
            self.receiver.parse_frame(frame[:HEADER_SIZE])

        # Truncate mid-payload
        with self.assertRaises(FramingError):
            self.receiver.parse_frame(frame[:HEADER_SIZE + 5])

    def test_too_short_frame_rejected(self):
        """Test frame shorter than header is rejected"""
        with self.assertRaises(FramingError):
            self.receiver.parse_frame(b"short")

    def test_oversize_payload_rejected(self):
        """Test oversized payload is rejected"""
        oversized = b"x" * (MAX_FRAME_SIZE + 1)

        with self.assertRaises(FrameSizeError):
            self.sender.create_frame(oversized)

    def test_max_size_payload_accepted(self):
        """Test max-size payload is accepted"""
        maxsize = b"x" * MAX_FRAME_SIZE
        frame = self.sender.create_frame(maxsize)
        payload, seq = self.receiver.parse_frame(frame)
        self.assertEqual(payload, maxsize)

    def test_empty_payload(self):
        """Test empty payload is valid"""
        frame = self.sender.create_frame(b"")
        payload, seq = self.receiver.parse_frame(frame)
        self.assertEqual(payload, b"")

    def test_binary_payload(self):
        """Test binary (non-UTF8) payload works"""
        binary_data = bytes(range(256))
        frame = self.sender.create_frame(binary_data)
        payload, seq = self.receiver.parse_frame(frame)
        self.assertEqual(payload, binary_data)

    def test_frame_structure(self):
        """Test frame has correct structure"""
        payload = b"test"
        frame = self.sender.create_frame(payload)

        # Header: 2B length + 8B seq + 32B hmac = 42 bytes
        self.assertEqual(len(frame), HEADER_SIZE + len(payload))

        # Parse length field
        length = struct.unpack('>H', frame[:2])[0]
        self.assertEqual(length, len(payload))

        # Parse sequence field
        seq = struct.unpack('>Q', frame[2:10])[0]
        self.assertEqual(seq, 1)

    def test_thread_safety_sequence(self):
        """Test sequence numbers are thread-safe"""
        import threading
        import time

        frames = []
        errors = []

        def send_frames():
            try:
                for _ in range(100):
                    frame = self.sender.create_frame(b"test")
                    frames.append(frame)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_frames) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        # All frames should have unique sequence numbers
        seqs = set()
        for frame in frames:
            seq = struct.unpack('>Q', frame[2:10])[0]
            self.assertNotIn(seq, seqs)
            seqs.add(seq)


class TestFramerEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def test_receiver_starts_at_zero(self):
        """Test receiver expects seq > 0"""
        receiver = SecureFramer(psk_hex=TEST_PSK, role="receiver")
        self.assertEqual(receiver.get_recv_seq(), 0)

    def test_sender_starts_at_zero(self):
        """Test sender starts at seq 0, first frame is 1"""
        sender = SecureFramer(psk_hex=TEST_PSK, role="sender")
        self.assertEqual(sender.get_send_seq(), 0)

        sender.create_frame(b"test")
        self.assertEqual(sender.get_send_seq(), 1)


if __name__ == '__main__':
    unittest.main()

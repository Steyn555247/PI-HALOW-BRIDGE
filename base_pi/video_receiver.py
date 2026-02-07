"""
Video Receiver - Receives video stream from Robot Pi

NOTE: Video is NOT authenticated (for performance).
Video data cannot cause actuation, so this is acceptable.

SAFETY:
- Bounded receive buffer to prevent OOM
- Buffer overflow triggers reconnect (not E-STOP, video is low priority)
"""

import socket
import logging
import threading
import time
from typing import Optional
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.constants import MAX_VIDEO_BUFFER

logger = logging.getLogger(__name__)


class VideoReceiver:
    """Receives MJPEG video stream from Robot Pi over TCP"""

    def __init__(self, video_port: int, buffer_size: int = 65536):
        self.video_port = video_port
        self.buffer_size = buffer_size

        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.running = False
        self.connected = False

        self.current_frame: Optional[bytes] = None
        self.frame_lock = threading.Lock()
        self.last_frame_time = 0

        self.receive_thread: Optional[threading.Thread] = None

        # Statistics
        self.frames_received = 0
        self.buffer_overflows = 0

        logger.info(f"VideoReceiver initialized on port {video_port}")

    def start(self):
        """Start listening for video stream"""
        self.running = True

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.video_port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            logger.info(f"Listening for video on port {self.video_port}")
        except Exception as e:
            logger.error(f"Failed to start video server: {e}")
            return

        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

        logger.info("VideoReceiver started")

    def stop(self):
        """Stop receiving video"""
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

        logger.info(f"VideoReceiver stopped (frames={self.frames_received}, overflows={self.buffer_overflows})")

    def _receive_loop(self):
        """Main receive loop for MJPEG stream"""
        while self.running:
            try:
                if not self.connected:
                    try:
                        logger.info("Waiting for Robot Pi video connection...")
                        self.client_socket, addr = self.server_socket.accept()

                        # TCP optimizations for video streaming
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
                        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)

                        self.client_socket.settimeout(3.0)
                        self.connected = True
                        logger.info(f"Robot Pi video connected from {addr}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Error accepting video connection: {e}")
                        time.sleep(1.0)
                        continue

                try:
                    self._receive_mjpeg_stream()
                except Exception as e:
                    logger.error(f"Error receiving video stream: {e}")
                    self._disconnect_client()
                    time.sleep(1.0)

            except Exception as e:
                logger.error(f"Unexpected error in video receive loop: {e}")
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

    def _receive_mjpeg_stream(self):
        """Receive and parse MJPEG stream with bounded buffer"""
        buffer = b""

        while self.running and self.connected:
            # Read data
            try:
                data = self.client_socket.recv(self.buffer_size)
            except socket.timeout:
                continue

            if not data:
                logger.warning("Robot Pi video disconnected")
                self.connected = False
                return

            buffer += data

            # SAFETY: Bounded buffer check
            if len(buffer) > MAX_VIDEO_BUFFER:
                logger.warning(f"Video buffer overflow ({len(buffer)} > {MAX_VIDEO_BUFFER}), resetting")
                self.buffer_overflows += 1
                # Find next SOI marker to resync
                soi = buffer.find(b'\xff\xd8', MAX_VIDEO_BUFFER // 2)
                if soi != -1:
                    buffer = buffer[soi:]
                else:
                    buffer = b""
                continue

            # Look for JPEG frames (SOI: 0xFFD8, EOI: 0xFFD9)
            while True:
                soi = buffer.find(b'\xff\xd8')
                if soi == -1:
                    # No SOI, clear buffer up to last few bytes
                    if len(buffer) > 2:
                        buffer = buffer[-2:]
                    break

                eoi = buffer.find(b'\xff\xd9', soi + 2)
                if eoi == -1:
                    # Incomplete frame, keep waiting
                    break

                # Extract frame
                frame = buffer[soi:eoi + 2]
                buffer = buffer[eoi + 2:]

                # Store frame (only keep latest)
                with self.frame_lock:
                    self.current_frame = frame
                    self.last_frame_time = time.time()
                    self.frames_received += 1

                logger.debug(f"Video frame: {len(frame)} bytes")

    def get_frame(self) -> Optional[bytes]:
        """Get the latest video frame"""
        with self.frame_lock:
            return self.current_frame

    def get_frame_generator(self):
        """Generator for streaming frames (for Flask MJPEG endpoint)"""
        while True:
            frame = self.get_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame)).encode() + b'\r\n'
                       b'\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.1)

    def is_connected(self) -> bool:
        """Check if Robot Pi video is connected"""
        return self.connected

    def get_last_frame_time(self) -> float:
        """Get timestamp of last received frame"""
        return self.last_frame_time

    def get_stats(self) -> dict:
        """Get receiver statistics"""
        return {
            'frames_received': self.frames_received,
            'buffer_overflows': self.buffer_overflows
        }

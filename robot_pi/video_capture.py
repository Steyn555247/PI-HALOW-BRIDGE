"""
Video Capture - Captures from USB cameras and streams to Base Pi

PRIORITY: Video is LOWEST priority. Control must not be delayed by video.

BACKPRESSURE STRATEGY:
- Only keep latest frame (drop older frames)
- Use non-blocking send with timeout
- Drop frames if send buffer is full
- This ensures video cannot block control channel

SIM_MODE: When enabled, generates synthetic test frames instead of using cameras.
"""

import cv2
import logging
import threading
import time
import socket
import platform
import numpy as np
from typing import Optional, Dict
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config

logger = logging.getLogger(__name__)

# Maximum time to wait for socket send
SEND_TIMEOUT_S = 0.5

# Platform detection
IS_LINUX = platform.system() == 'Linux'


class VideoCapture:
    """
    Captures video from ELP USB cameras and streams to Base Pi.

    Frame dropping policy: Always send latest frame, drop if socket blocked.
    """

    def __init__(self, camera_devices: list, base_pi_ip: str, video_port: int,
                 width: int = 640, height: int = 480, fps: int = 10, quality: int = 60):
        self.camera_devices = camera_devices
        self.base_pi_ip = base_pi_ip
        self.video_port = video_port
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality

        self.active_camera_id = 0
        self.active_camera_lock = threading.Lock()
        self.cameras: Dict[int, cv2.VideoCapture] = {}
        self.running = False
        self.connected = False

        self.socket: Optional[socket.socket] = None
        self.capture_thread: Optional[threading.Thread] = None

        # Statistics
        self.frames_sent = 0
        self.frames_dropped = 0
        self.camera_errors = 0

        # Camera health tracking per camera
        self._camera_consecutive_failures: Dict[int, int] = {}
        self._camera_recovery_attempts: Dict[int, int] = {}
        self._camera_last_recovery: Dict[int, float] = {}
        self._max_consecutive_failures = 5  # Trigger recovery after N failures
        self._recovery_backoff_base = 2.0   # Exponential backoff base (seconds)
        self._max_recovery_backoff = 30.0   # Max backoff (seconds)

        # Simulation mode
        self.sim_mode = getattr(config, 'SIM_MODE', False)
        self._sim_frame_count = 0

        logger.info(f"VideoCapture initialized: {len(camera_devices)} cameras, {width}x{height}@{fps}fps, sim_mode={self.sim_mode}")

    def _init_camera(self, camera_id: int) -> Optional[cv2.VideoCapture]:
        """Initialize a camera with platform-appropriate backend"""
        if self.sim_mode:
            logger.info(f"SIM_MODE: Skipping real camera {camera_id} initialization")
            return None

        try:
            device = self.camera_devices[camera_id]

            # Extract device index from path (e.g., '/dev/video0' -> 0, '/dev/video2' -> 2)
            # V4L2 backend requires integer indices, not device path strings
            if '/dev/video' in str(device):
                try:
                    device_idx = int(str(device).replace('/dev/video', ''))
                except ValueError:
                    device_idx = camera_id
                    logger.warning(f"Could not parse device index from {device}, using camera_id={camera_id}")
            else:
                device_idx = int(device) if str(device).isdigit() else camera_id

            # Use V4L2 on Linux with integer index, default backend on Windows/Mac
            if IS_LINUX:
                logger.debug(f"Opening camera {camera_id} as V4L2 device index {device_idx}")
                cap = cv2.VideoCapture(device_idx, cv2.CAP_V4L2)
            else:
                cap = cv2.VideoCapture(device_idx)

            if not cap.isOpened():
                logger.error(f"Failed to open camera {camera_id} (config: {device}, index: {device_idx})")
                return None

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)

            # MJPG fourcc only supported on some platforms
            if IS_LINUX:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            logger.info(f"Camera {camera_id} initialized (config: {device}, index: {device_idx})")
            return cap

        except Exception as e:
            logger.error(f"Error initializing camera {camera_id}: {e}")
            return None

    def _generate_sim_frame(self) -> np.ndarray:
        """Generate a synthetic test frame for SIM_MODE"""
        self._sim_frame_count += 1

        # Create a frame with test pattern
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Gradient background
        for y in range(self.height):
            frame[y, :, 0] = int(255 * y / self.height)  # Blue gradient
            frame[y, :, 1] = int(128 * (1 + np.sin(self._sim_frame_count / 10)))  # Pulsing green
            frame[y, :, 2] = 64  # Fixed red

        # Add frame counter text
        cv2.putText(frame, f"SIM FRAME {self._sim_frame_count}", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Add timestamp
        ts = time.strftime("%H:%M:%S")
        cv2.putText(frame, ts, (50, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Add camera ID
        with self.active_camera_lock:
            cam_id = self.active_camera_id
        cv2.putText(frame, f"CAM {cam_id}", (50, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return frame

    def _should_attempt_recovery(self, camera_id: int) -> bool:
        """Check if enough time has passed for recovery attempt (exponential backoff)"""
        last_recovery = self._camera_last_recovery.get(camera_id, 0)
        attempts = self._camera_recovery_attempts.get(camera_id, 0)

        # Calculate backoff time
        backoff = min(
            self._recovery_backoff_base * (2 ** attempts),
            self._max_recovery_backoff
        )

        return (time.time() - last_recovery) >= backoff

    def _attempt_camera_recovery(self, camera_id: int):
        """Attempt to recover a failed camera with exponential backoff"""
        if not self._should_attempt_recovery(camera_id):
            return

        attempts = self._camera_recovery_attempts.get(camera_id, 0) + 1
        self._camera_recovery_attempts[camera_id] = attempts
        self._camera_last_recovery[camera_id] = time.time()

        logger.info(f"Attempting camera {camera_id} recovery (attempt {attempts})")

        # Release existing camera if present
        if camera_id in self.cameras:
            try:
                self.cameras[camera_id].release()
            except:
                pass
            del self.cameras[camera_id]

        # Try to reinitialize
        new_cam = self._init_camera(camera_id)
        if new_cam:
            self.cameras[camera_id] = new_cam
            self._camera_consecutive_failures[camera_id] = 0
            self._camera_recovery_attempts[camera_id] = 0  # Reset on success
            logger.info(f"Camera {camera_id} recovered successfully")
        else:
            logger.warning(f"Camera {camera_id} recovery failed (attempt {attempts})")

    def _connect_to_base_pi(self) -> bool:
        """Connect to Base Pi for video streaming"""
        try:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.base_pi_ip, self.video_port))
            # Set send timeout for backpressure
            self.socket.settimeout(SEND_TIMEOUT_S)
            self.connected = True
            logger.info(f"Connected to Base Pi video at {self.base_pi_ip}:{self.video_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Base Pi video: {e}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False

    def start(self):
        """Start video capture and streaming"""
        self.running = True

        if self.sim_mode:
            logger.info("SIM_MODE: Using synthetic video frames")
        else:
            # Initialize cameras
            for i in range(len(self.camera_devices)):
                camera = self._init_camera(i)
                if camera:
                    self.cameras[i] = camera

            if not self.cameras:
                logger.warning("No cameras initialized - video capture will use sim frames")

        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

        logger.info("VideoCapture started")

    def stop(self):
        """Stop video capture"""
        self.running = False
        self.connected = False

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)

        for cap in self.cameras.values():
            try:
                cap.release()
            except:
                pass

        self.cameras.clear()

        logger.info(f"VideoCapture stopped (sent={self.frames_sent}, dropped={self.frames_dropped}, errors={self.camera_errors})")

    def _capture_loop(self):
        """Main capture and streaming loop with backpressure handling"""
        frame_interval = 1.0 / self.fps
        last_frame_time = 0

        while self.running:
            try:
                # Connect if not connected
                if not self.connected:
                    if self._connect_to_base_pi():
                        logger.info("Video connection established")
                    else:
                        time.sleep(2.0)
                        continue

                # Get active camera (thread-safe)
                with self.active_camera_lock:
                    active_id = self.active_camera_id

                # Rate limiting - sleep if needed, then proceed to capture
                now = time.time()
                elapsed = now - last_frame_time
                if elapsed < frame_interval:
                    sleep_time = max(0, frame_interval - elapsed)
                    time.sleep(sleep_time)
                    # Don't continue - proceed to capture after sleeping

                # Capture frame (from camera or generate synthetic)
                frame = None
                if self.sim_mode or not self.cameras:
                    frame = self._generate_sim_frame()
                else:
                    camera = self.cameras.get(active_id)
                    if camera:
                        ret, frame = camera.read()
                        if not ret:
                            self.camera_errors += 1
                            self._camera_consecutive_failures[active_id] = \
                                self._camera_consecutive_failures.get(active_id, 0) + 1
                            failures = self._camera_consecutive_failures[active_id]

                            logger.warning(f"Failed to read from camera {active_id} "
                                         f"(consecutive={failures}, total={self.camera_errors})")

                            # Attempt recovery after threshold failures
                            if failures >= self._max_consecutive_failures:
                                self._attempt_camera_recovery(active_id)

                            time.sleep(0.1)
                            continue
                        else:
                            # Reset consecutive failures on success
                            self._camera_consecutive_failures[active_id] = 0
                    else:
                        # Camera not available, try recovery or use synthetic
                        if self._should_attempt_recovery(active_id):
                            self._attempt_camera_recovery(active_id)
                        frame = self._generate_sim_frame()

                if frame is None:
                    time.sleep(0.1)
                    continue

                last_frame_time = time.time()

                # Encode as JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                result, encoded_frame = cv2.imencode('.jpg', frame, encode_param)

                if not result:
                    logger.warning("Failed to encode frame")
                    continue

                # Send frame with timeout (backpressure)
                try:
                    frame_data = encoded_frame.tobytes()
                    self.socket.sendall(frame_data)
                    self.frames_sent += 1
                    logger.debug(f"Sent video frame: {len(frame_data)} bytes")

                except socket.timeout:
                    # Socket blocked - drop this frame
                    self.frames_dropped += 1
                    logger.debug("Video frame dropped (socket blocked)")
                    continue

                except Exception as e:
                    logger.error(f"Failed to send video frame: {e}")
                    self.connected = False
                    if self.socket:
                        try:
                            self.socket.close()
                        except:
                            pass
                        self.socket = None

            except Exception as e:
                logger.error(f"Error in video capture loop: {e}")
                time.sleep(1.0)

    def set_active_camera(self, camera_id: int):
        """Set the active camera (thread-safe)"""
        with self.active_camera_lock:
            if self.sim_mode or camera_id in self.cameras or camera_id < len(self.camera_devices):
                self.active_camera_id = camera_id
                logger.info(f"Active camera set to {camera_id}")
            else:
                logger.warning(f"Camera {camera_id} not available")

    def get_active_camera(self) -> int:
        """Get the active camera ID (thread-safe)"""
        with self.active_camera_lock:
            return self.active_camera_id

    def get_stats(self) -> dict:
        """Get capture statistics"""
        total = self.frames_sent + self.frames_dropped
        return {
            'frames_sent': self.frames_sent,
            'frames_dropped': self.frames_dropped,
            'camera_errors': self.camera_errors,
            'drop_rate': self.frames_dropped / max(1, total),
            'sim_mode': self.sim_mode
        }

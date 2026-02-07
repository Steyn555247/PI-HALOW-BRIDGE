"""
Video Recorder Module

Record video stream to files on SSD with automatic rotation and cleanup.
"""

import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional


logger = logging.getLogger(__name__)


class VideoRecorder:
    """
    Records MJPEG video stream to files with automatic rotation.
    """

    def __init__(self, base_path: str, retention_days: int = 7, rotation_minutes: int = 10):
        """
        Initialize video recorder.

        Args:
            base_path: Base directory for video files
            retention_days: Number of days to retain videos
            rotation_minutes: Minutes between file rotations
        """
        self.base_path = base_path
        self.retention_days = retention_days
        self.rotation_minutes = rotation_minutes
        self.running = False

        # Current file
        self.current_file: Optional[object] = None
        self.current_file_path: Optional[str] = None
        self.current_file_start_time: float = 0

        # Video receiver reference
        self.video_receiver = None
        self.recorder_thread: Optional[threading.Thread] = None

        # Create base directory
        os.makedirs(base_path, exist_ok=True)

    def start_recording(self, video_receiver):
        """
        Start recording video from receiver.

        Args:
            video_receiver: VideoReceiver instance
        """
        self.video_receiver = video_receiver
        self.running = True

        self.recorder_thread = threading.Thread(target=self._recorder_loop, daemon=True)
        self.recorder_thread.start()

        logger.info(f"Video recorder started (path: {self.base_path}, retention: {self.retention_days} days)")

    def stop_recording(self):
        """Stop recording."""
        self.running = False

        if self.recorder_thread:
            self.recorder_thread.join(timeout=5.0)

        # Close current file
        if self.current_file:
            self.current_file.close()
            self.current_file = None

        logger.info("Video recorder stopped")

    def _recorder_loop(self):
        """Background recording loop."""
        last_frame_time = 0
        last_cleanup_time = time.time()

        while self.running:
            try:
                # Check if video receiver is available
                if not self.video_receiver:
                    time.sleep(1.0)
                    continue

                # Rotate file if needed
                self._rotate_file_if_needed()

                # Get latest frame
                current_frame_time = self.video_receiver.last_frame_time
                if current_frame_time > last_frame_time:
                    frame = self.video_receiver.get_frame()
                    if frame and self.current_file:
                        # Write MJPEG frame with boundary
                        self.current_file.write(b'--frame\r\n')
                        self.current_file.write(b'Content-Type: image/jpeg\r\n')
                        self.current_file.write(f'Content-Length: {len(frame)}\r\n'.encode())
                        self.current_file.write(b'\r\n')
                        self.current_file.write(frame)
                        self.current_file.write(b'\r\n')
                        self.current_file.flush()

                    last_frame_time = current_frame_time
                else:
                    # Wait briefly for new frame
                    time.sleep(0.1)

                # Periodic cleanup (every 10 minutes)
                now = time.time()
                if now - last_cleanup_time > 600:
                    self._cleanup_old_files()
                    last_cleanup_time = now

            except Exception as e:
                logger.error(f"Error in video recorder loop: {e}")
                time.sleep(1.0)

    def _rotate_file_if_needed(self):
        """Check if we need to rotate to a new video file."""
        now = time.time()

        # Check if rotation is needed
        should_rotate = False
        if not self.current_file:
            should_rotate = True
        elif now - self.current_file_start_time >= self.rotation_minutes * 60:
            should_rotate = True

        if should_rotate:
            # Close current file
            if self.current_file:
                self.current_file.close()
                logger.info(f"Closed video file: {self.current_file_path}")

            # Create new file
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"video_{timestamp_str}.mjpeg"
            self.current_file_path = os.path.join(self.base_path, filename)

            self.current_file = open(self.current_file_path, 'wb')
            self.current_file_start_time = now

            logger.info(f"Started new video file: {self.current_file_path}")

    def _cleanup_old_files(self):
        """Delete video files older than retention period."""
        try:
            cutoff_time = time.time() - (self.retention_days * 86400)

            for filename in os.listdir(self.base_path):
                if not filename.startswith('video_') or not filename.endswith('.mjpeg'):
                    continue

                file_path = os.path.join(self.base_path, filename)

                # Check file modification time
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        # Don't delete current file
                        if file_path != self.current_file_path:
                            os.remove(file_path)
                            logger.info(f"Deleted old video: {filename}")
                except Exception as e:
                    logger.error(f"Error checking file {filename}: {e}")

        except Exception as e:
            logger.error(f"Error cleaning up old videos: {e}")

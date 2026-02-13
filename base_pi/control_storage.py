"""
Control Storage Module

Record control commands to JSONL files on SSD with daily rotation.
Thread-safe async write queue for non-blocking operation.
"""

import json
import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from queue import Queue, Empty


logger = logging.getLogger(__name__)


class ControlStorage:
    """
    Records control commands to JSONL files with daily rotation.

    Format: One JSON object per line with timestamp and command data.
    Files: commands_YYYYMMDD.jsonl
    """

    def __init__(self, base_path: str, retention_days: int = 3650):
        """
        Initialize control storage.

        Args:
            base_path: Base directory for command log files
            retention_days: Number of days to retain logs (default ~10 years)
        """
        self.base_path = base_path
        self.retention_days = retention_days
        self.running = False
        self.write_queue: Queue = Queue(maxsize=10000)
        self.writer_thread: Optional[threading.Thread] = None

        # Current file
        self.current_file: Optional[object] = None
        self.current_file_date: Optional[str] = None

        # Statistics
        self.commands_written = 0
        self.commands_dropped = 0

        # Create base directory
        os.makedirs(base_path, exist_ok=True)

    def start(self):
        """Start the storage writer thread."""
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        logger.info(f"Control storage started (path: {self.base_path}, retention: {self.retention_days} days)")

    def stop(self):
        """Stop the storage writer thread."""
        self.running = False
        if self.writer_thread:
            self.writer_thread.join(timeout=5.0)

        # Close current file
        if self.current_file:
            self.current_file.close()
            self.current_file = None

        logger.info(f"Control storage stopped (written: {self.commands_written}, dropped: {self.commands_dropped})")

    def write_command(self, command_type: str, data: Dict[str, Any], success: bool = True):
        """
        Queue a control command for async write to file.

        Args:
            command_type: Type of command (e.g., 'emergency_stop', 'clamp_close')
            data: Command data dictionary
            success: Whether the command was sent successfully
        """
        record = {
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat(),
            'type': command_type,
            'data': data,
            'success': success
        }

        try:
            self.write_queue.put_nowait(record)
        except:
            # Queue full, drop record (prefer real-time over storage)
            self.commands_dropped += 1

    def _writer_loop(self):
        """Background writer loop (processes write queue)."""
        last_cleanup_time = time.time()

        while self.running:
            try:
                # Get command from queue (with timeout)
                try:
                    record = self.write_queue.get(timeout=1.0)
                except Empty:
                    continue

                # Rotate file if needed (new day)
                self._rotate_file_if_needed()

                # Write to file
                self._write_to_file(record)

                # Periodic cleanup (every 10 minutes)
                now = time.time()
                if now - last_cleanup_time > 600:
                    self._cleanup_old_files()
                    last_cleanup_time = now

            except Exception as e:
                logger.error(f"Error in control storage writer loop: {e}")
                time.sleep(1.0)

    def _rotate_file_if_needed(self):
        """Check if we need to rotate to a new file (new day)."""
        today = datetime.now().strftime("%Y%m%d")

        if self.current_file_date != today:
            # Close current file
            if self.current_file:
                self.current_file.close()
                logger.info(f"Closed command log: commands_{self.current_file_date}.jsonl")

            # Open new file for today
            filename = f"commands_{today}.jsonl"
            file_path = os.path.join(self.base_path, filename)
            self.current_file = open(file_path, 'a', encoding='utf-8')
            self.current_file_date = today

            logger.info(f"Opened command log: {file_path}")

    def _write_to_file(self, record: Dict[str, Any]):
        """
        Write a command record to the current file.

        Args:
            record: Command record dictionary
        """
        if not self.current_file:
            return

        try:
            # Write as single JSON line
            line = json.dumps(record, separators=(',', ':')) + '\n'
            self.current_file.write(line)
            self.current_file.flush()
            self.commands_written += 1

        except Exception as e:
            logger.error(f"Error writing command to file: {e}")

    def _cleanup_old_files(self):
        """Delete command log files older than retention period."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)

            for filename in os.listdir(self.base_path):
                if not filename.startswith('commands_') or not filename.endswith('.jsonl'):
                    continue

                # Extract date from filename
                try:
                    date_str = filename[9:17]  # commands_YYYYMMDD.jsonl
                    file_date = datetime.strptime(date_str, "%Y%m%d")

                    if file_date < cutoff_date:
                        file_path = os.path.join(self.base_path, filename)
                        # Don't delete current file
                        if date_str != self.current_file_date:
                            os.remove(file_path)
                            logger.info(f"Deleted old command log: {filename}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error cleaning up old command logs: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        return {
            'commands_written': self.commands_written,
            'commands_dropped': self.commands_dropped,
            'queue_size': self.write_queue.qsize(),
            'current_file_date': self.current_file_date
        }

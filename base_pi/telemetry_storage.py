"""
Telemetry Storage Module

Store telemetry data to SQLite database on attached SSD.
Automatic rotation and cleanup.
"""

import sqlite3
import logging
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from queue import Queue, Empty


logger = logging.getLogger(__name__)


class TelemetryStorage:
    """
    SQLite storage for telemetry data with automatic rotation and cleanup.
    """

    def __init__(self, base_path: str, retention_days: int = 30):
        """
        Initialize telemetry storage.

        Args:
            base_path: Base directory for database files
            retention_days: Number of days to retain data
        """
        self.base_path = base_path
        self.retention_days = retention_days
        self.running = False
        self.write_queue: Queue = Queue(maxsize=1000)
        self.writer_thread: Optional[threading.Thread] = None

        # Current database connection
        self.db_conn: Optional[sqlite3.Connection] = None
        self.current_db_date: Optional[str] = None

        # Create base directory
        os.makedirs(base_path, exist_ok=True)

    def start(self):
        """Start the storage writer thread."""
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        logger.info(f"Telemetry storage started (path: {self.base_path}, retention: {self.retention_days} days)")

    def stop(self):
        """Stop the storage writer thread."""
        self.running = False
        if self.writer_thread:
            self.writer_thread.join(timeout=5.0)

        # Close database
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None

        logger.info("Telemetry storage stopped")

    def write_telemetry(self, telemetry: Dict[str, Any]):
        """
        Queue telemetry for async write to database.

        Args:
            telemetry: Telemetry dictionary
        """
        try:
            self.write_queue.put_nowait(telemetry)
        except:
            # Queue full, drop sample (prefer real-time over storage)
            pass

    def _writer_loop(self):
        """Background writer loop (processes write queue)."""
        while self.running:
            try:
                # Get telemetry from queue (with timeout)
                try:
                    telemetry = self.write_queue.get(timeout=1.0)
                except Empty:
                    continue

                # Rotate database if needed (new day)
                self._rotate_database_if_needed()

                # Write to database
                self._write_to_db(telemetry)

                # Periodic cleanup (every 100 writes)
                if self.write_queue.qsize() == 0:
                    self._cleanup_old_files()

            except Exception as e:
                logger.error(f"Error in storage writer loop: {e}")
                time.sleep(1.0)

    def _rotate_database_if_needed(self):
        """Check if we need to rotate to a new database file (new day)."""
        today = datetime.now().strftime("%Y%m%d")

        if self.current_db_date != today:
            # Close current database
            if self.db_conn:
                self.db_conn.close()

            # Open new database for today
            db_path = self._get_db_path(today)
            self.db_conn = sqlite3.connect(db_path)
            self.current_db_date = today

            # Create tables if needed
            self._create_tables()

            logger.info(f"Rotated to new database: {db_path}")

    def _get_db_path(self, date_str: str) -> str:
        """Get database file path for a given date."""
        return os.path.join(self.base_path, f"telemetry_{date_str}.db")

    def _create_tables(self):
        """Create database tables if they don't exist."""
        if not self.db_conn:
            return

        cursor = self.db_conn.cursor()

        # Main telemetry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                voltage REAL,
                height REAL,
                force REAL,

                -- IMU (10 columns)
                imu_quat_w REAL,
                imu_quat_x REAL,
                imu_quat_y REAL,
                imu_quat_z REAL,
                imu_accel_x REAL,
                imu_accel_y REAL,
                imu_accel_z REAL,
                imu_gyro_x REAL,
                imu_gyro_y REAL,
                imu_gyro_z REAL,

                -- Barometer (3 columns)
                baro_pressure REAL,
                baro_temperature REAL,
                baro_altitude REAL,

                -- Motors (8 columns)
                motor_0_current REAL,
                motor_1_current REAL,
                motor_2_current REAL,
                motor_3_current REAL,
                motor_4_current REAL,
                motor_5_current REAL,
                motor_6_current REAL,
                motor_7_current REAL,

                -- Status (4 columns)
                estop_engaged INTEGER,
                control_age_ms INTEGER,
                rtt_ms INTEGER,
                control_seq INTEGER
            )
        """)

        # Create index on timestamp for fast queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry(timestamp)
        """)

        self.db_conn.commit()

    def _write_to_db(self, telemetry: Dict[str, Any]):
        """
        Write telemetry sample to database.

        Args:
            telemetry: Telemetry dictionary
        """
        if not self.db_conn:
            return

        try:
            cursor = self.db_conn.cursor()

            # Extract values
            timestamp = telemetry.get('timestamp', time.time())
            voltage = telemetry.get('voltage')
            height = telemetry.get('height')
            force = telemetry.get('force')

            # IMU data
            imu = telemetry.get('imu', {})
            imu_quat_w = imu.get('quat_w')
            imu_quat_x = imu.get('quat_x')
            imu_quat_y = imu.get('quat_y')
            imu_quat_z = imu.get('quat_z')
            imu_accel_x = imu.get('accel_x')
            imu_accel_y = imu.get('accel_y')
            imu_accel_z = imu.get('accel_z')
            imu_gyro_x = imu.get('gyro_x')
            imu_gyro_y = imu.get('gyro_y')
            imu_gyro_z = imu.get('gyro_z')

            # Barometer data
            baro = telemetry.get('barometer', {})
            baro_pressure = baro.get('pressure')
            baro_temperature = baro.get('temperature')
            baro_altitude = baro.get('altitude')

            # Motor currents (8 motors)
            motor_currents = telemetry.get('motor_currents', [0] * 8)
            motor_currents = (motor_currents + [0] * 8)[:8]  # Ensure 8 values

            # Status
            estop = telemetry.get('estop', {})
            estop_engaged = 1 if estop.get('engaged', False) else 0
            control_age_ms = telemetry.get('control_age_ms')
            rtt_ms = telemetry.get('rtt_ms')
            control_seq = telemetry.get('control_seq')

            # Insert into database
            cursor.execute("""
                INSERT INTO telemetry (
                    timestamp, voltage, height, force,
                    imu_quat_w, imu_quat_x, imu_quat_y, imu_quat_z,
                    imu_accel_x, imu_accel_y, imu_accel_z,
                    imu_gyro_x, imu_gyro_y, imu_gyro_z,
                    baro_pressure, baro_temperature, baro_altitude,
                    motor_0_current, motor_1_current, motor_2_current, motor_3_current,
                    motor_4_current, motor_5_current, motor_6_current, motor_7_current,
                    estop_engaged, control_age_ms, rtt_ms, control_seq
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
            """, (
                timestamp, voltage, height, force,
                imu_quat_w, imu_quat_x, imu_quat_y, imu_quat_z,
                imu_accel_x, imu_accel_y, imu_accel_z,
                imu_gyro_x, imu_gyro_y, imu_gyro_z,
                baro_pressure, baro_temperature, baro_altitude,
                motor_currents[0], motor_currents[1], motor_currents[2], motor_currents[3],
                motor_currents[4], motor_currents[5], motor_currents[6], motor_currents[7],
                estop_engaged, control_age_ms, rtt_ms, control_seq
            ))

            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error writing to database: {e}")

    def _cleanup_old_files(self):
        """Delete database files older than retention period."""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)

            for filename in os.listdir(self.base_path):
                if not filename.startswith('telemetry_') or not filename.endswith('.db'):
                    continue

                # Extract date from filename
                try:
                    date_str = filename[10:18]  # telemetry_YYYYMMDD.db
                    file_date = datetime.strptime(date_str, "%Y%m%d")

                    if file_date < cutoff_date:
                        file_path = os.path.join(self.base_path, filename)
                        os.remove(file_path)
                        logger.info(f"Deleted old database: {filename}")
                except:
                    pass

        except Exception as e:
            logger.error(f"Error cleaning up old files: {e}")

    def query_range(self, start_ts: float, end_ts: float) -> List[Dict[str, Any]]:
        """
        Query telemetry data for a time range.

        Args:
            start_ts: Start timestamp (Unix time)
            end_ts: End timestamp (Unix time)

        Returns:
            List of telemetry dictionaries
        """
        # TODO: Implement if needed for analysis/export
        pass

"""
Sensor Reader - Reads IMU and barometer via I2C

SIM_MODE: When enabled or when hardware is unavailable, generates deterministic
mock sensor data for testing without I2C hardware.
"""
import logging
import math
import time
import threading
import os
import sys
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Check SIM_MODE first
SIM_MODE = os.getenv('SIM_MODE', 'false').lower() == 'true'

BNO08X_AVAILABLE = False
if not SIM_MODE:
    try:
        import board
        import busio
        from adafruit_bno08x import BNO08X_I2C
        from adafruit_bno08x.i2c import BNO08X_I2C
        import adafruit_bmp3xx
        BNO08X_AVAILABLE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)
if not BNO08X_AVAILABLE and not SIM_MODE:
    logger.warning("BNO08X/BMP3XX libraries not available, using mock sensors")


class SensorReader:
    """Reads BNO085 IMU and BMP388 barometer"""

    def __init__(self, i2c_bus: int = 1, bno085_addr: int = 0x4A, bmp388_addr: int = 0x77,
                 read_interval: float = 0.1):
        self.i2c_bus = i2c_bus
        self.bno085_addr = bno085_addr
        self.bmp388_addr = bmp388_addr
        self.read_interval = read_interval

        self.bno085 = None
        self.bmp388 = None
        self.i2c = None

        self.running = False
        self.read_thread: Optional[threading.Thread] = None

        self.latest_imu_data: Dict[str, float] = {}
        self.latest_baro_data: Dict[str, float] = {}
        self.data_lock = threading.Lock()

        logger.info(f"SensorReader initialized: I2C bus {i2c_bus}")

    def start(self):
        """Initialize sensors and start reading"""
        try:
            if BNO08X_AVAILABLE:
                # Initialize I2C
                self.i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

                # Initialize BNO085
                try:
                    self.bno085 = BNO08X_I2C(self.i2c, address=self.bno085_addr)
                    self.bno085.enable_feature(0x05)  # Rotation vector
                    self.bno085.enable_feature(0x01)  # Accelerometer
                    self.bno085.enable_feature(0x02)  # Gyroscope
                    logger.info("BNO085 initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize BNO085: {e}")
                    self.bno085 = None

                # Initialize BMP388
                try:
                    self.bmp388 = adafruit_bmp3xx.BMP3XX_I2C(self.i2c, address=self.bmp388_addr)
                    self.bmp388.pressure_oversampling = 8
                    self.bmp388.temperature_oversampling = 2
                    logger.info("BMP388 initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize BMP388: {e}")
                    self.bmp388 = None
            else:
                logger.warning("Sensor libraries not available, running in mock mode")

        except Exception as e:
            logger.error(f"Failed to initialize I2C: {e}")

        # Start read thread
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

        logger.info("SensorReader started")

    def stop(self):
        """Stop reading sensors"""
        self.running = False

        if self.read_thread:
            self.read_thread.join(timeout=2.0)

        logger.info("SensorReader stopped")

    def _read_loop(self):
        """Main sensor reading loop"""
        while self.running:
            try:
                # Read IMU
                if self.bno085:
                    try:
                        quat_i, quat_j, quat_k, quat_real = self.bno085.quaternion
                        accel_x, accel_y, accel_z = self.bno085.acceleration
                        gyro_x, gyro_y, gyro_z = self.bno085.gyro

                        with self.data_lock:
                            self.latest_imu_data = {
                                'quat_w': quat_real or 1.0,
                                'quat_x': quat_i or 0.0,
                                'quat_y': quat_j or 0.0,
                                'quat_z': quat_k or 0.0,
                                'accel_x': accel_x or 0.0,
                                'accel_y': accel_y or 0.0,
                                'accel_z': accel_z or 9.8,
                                'gyro_x': gyro_x or 0.0,
                                'gyro_y': gyro_y or 0.0,
                                'gyro_z': gyro_z or 0.0
                            }
                    except Exception as e:
                        logger.error(f"Error reading BNO085: {e}")
                else:
                    # Mock IMU data - deterministic with slight time-based variation
                    t = time.time()
                    with self.data_lock:
                        self.latest_imu_data = {
                            'quat_w': 1.0, 'quat_x': 0.0, 'quat_y': 0.0, 'quat_z': 0.0,
                            'accel_x': 0.01 * math.sin(t * 0.5),
                            'accel_y': 0.01 * math.cos(t * 0.5),
                            'accel_z': 9.81 + 0.01 * math.sin(t * 0.3),
                            'gyro_x': 0.001 * math.sin(t * 0.7),
                            'gyro_y': 0.001 * math.cos(t * 0.7),
                            'gyro_z': 0.001 * math.sin(t * 0.9)
                        }

                # Read Barometer
                if self.bmp388:
                    try:
                        pressure = self.bmp388.pressure
                        temperature = self.bmp388.temperature
                        altitude = self.bmp388.altitude

                        with self.data_lock:
                            self.latest_baro_data = {
                                'pressure': pressure,
                                'temperature': temperature,
                                'altitude': altitude
                            }
                    except Exception as e:
                        logger.error(f"Error reading BMP388: {e}")
                else:
                    # Mock barometer data - deterministic with slight time-based variation
                    t = time.time()
                    with self.data_lock:
                        self.latest_baro_data = {
                            'pressure': 1013.25 + 0.1 * math.sin(t * 0.1),
                            'temperature': 25.0 + 0.5 * math.sin(t * 0.05),
                            'altitude': 100.0 + 0.1 * math.sin(t * 0.2)
                        }

                time.sleep(self.read_interval)

            except Exception as e:
                logger.error(f"Error in sensor read loop: {e}")
                time.sleep(self.read_interval)

    def get_imu_data(self) -> Dict[str, float]:
        """Get latest IMU data"""
        with self.data_lock:
            return self.latest_imu_data.copy()

    def get_barometer_data(self) -> Dict[str, float]:
        """Get latest barometer data"""
        with self.data_lock:
            return self.latest_baro_data.copy()

    def get_all_data(self) -> Dict[str, Any]:
        """Get all sensor data"""
        with self.data_lock:
            return {
                'imu': self.latest_imu_data.copy(),
                'barometer': self.latest_baro_data.copy()
            }

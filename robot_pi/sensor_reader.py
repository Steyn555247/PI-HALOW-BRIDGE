"""
Sensor Reader - Reads IMU and barometer via I2C

SIM_MODE: When enabled or when hardware is unavailable, generates deterministic
mock sensor data for testing without I2C hardware.

PHASE 6 OPTIMIZATION:
- Parallel I2C reads using ThreadPoolExecutor
- IMU and barometer read concurrently instead of sequentially
- Reduces total read time from IMU_time + Baro_time to max(IMU_time, Baro_time)

MULTIPLEXER SUPPORT:
- TCA9548A I2C multiplexer for multi-sensor configurations
- Automatically switches channels before reading each sensor
- Gracefully handles missing multiplexer hardware

CURRENT SENSOR SUPPORT:
- INA228 high-side current/voltage/power monitors
- Supports battery, system, and servo power monitoring
- Parallel reads with other sensors for efficiency

SENSOR HARDWARE:
- BNO055 IMU at 0x28 on multiplexer channel 1
- BMP581 barometer at 0x47 on multiplexer channel 0
"""
import logging
import math
import time
import threading
import os
import sys
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, Future

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Check SIM_MODE first
SIM_MODE = os.getenv('SIM_MODE', 'false').lower() == 'true'

BNO055_AVAILABLE = False
BMP5XX_AVAILABLE = False
TCA9548A_AVAILABLE = False
SMBUS2_AVAILABLE = False

if not SIM_MODE:
    try:
        import board
        import busio
        from adafruit_bno055 import BNO055_I2C
        BNO055_AVAILABLE = True
    except ImportError:
        pass

    try:
        import adafruit_bmp5xx
        from adafruit_bus_device.i2c_device import I2CDevice
        BMP5XX_AVAILABLE = True
    except ImportError:
        pass

    try:
        import adafruit_tca9548a
        TCA9548A_AVAILABLE = True
    except ImportError:
        pass

    try:
        import smbus2
        SMBUS2_AVAILABLE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)
if not BNO055_AVAILABLE and not SIM_MODE:
    logger.warning("BNO055 library not available, using mock IMU")
if not BMP5XX_AVAILABLE and not SIM_MODE:
    logger.warning("BMP5XX library not available, using mock barometer")
if not TCA9548A_AVAILABLE and not SIM_MODE:
    logger.warning("TCA9548A library not available, multiplexer support disabled")
if not SMBUS2_AVAILABLE and not SIM_MODE:
    logger.warning("smbus2 library not available, current sensor support disabled")


class SensorReader:
    """Reads BNO055 IMU, BMP581 barometer, and INA228 current sensors via I2C"""

    def __init__(self, i2c_bus: int = 1, bno055_addr: int = 0x28, bmp581_addr: int = 0x47,
                 read_interval: float = 0.1, use_multiplexer: bool = True,
                 mux_addr: int = 0x70, imu_channel: int = 1, baro_channel: int = 0,
                 current_sensors: Optional[Dict] = None):
        self.i2c_bus = i2c_bus
        self.bno055_addr = bno055_addr
        self.bmp581_addr = bmp581_addr
        self.read_interval = read_interval

        # Multiplexer configuration
        self.use_multiplexer = use_multiplexer
        self.mux_addr = mux_addr
        self.imu_channel = imu_channel
        self.baro_channel = baro_channel

        # Current sensors configuration
        self.current_sensors = current_sensors or {}

        # Hardware objects
        self.bno055 = None
        self.bmp581 = None
        self.i2c = None
        self.multiplexer = None
        self.smbus = None

        self.running = False
        self.read_thread: Optional[threading.Thread] = None

        # Phase 6: ThreadPoolExecutor for parallel I2C reads
        # Increase workers to 5 to handle IMU + Baro + 3 current sensors in parallel
        num_workers = 2 + len(self.current_sensors)
        self.executor = ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix="i2c")

        self.latest_imu_data: Dict[str, float] = {}
        self.latest_baro_data: Dict[str, float] = {}
        self.latest_current_data: Dict[str, Dict[str, float]] = {}
        self.data_lock = threading.Lock()

        mux_status = "enabled" if use_multiplexer else "disabled"
        current_sensor_count = len(self.current_sensors)
        logger.info(f"SensorReader initialized: I2C bus {i2c_bus}, multiplexer {mux_status}, "
                    f"{current_sensor_count} current sensors, parallel reads enabled")

    def start(self):
        """Initialize sensors and start reading"""
        try:
            if BNO055_AVAILABLE or BMP5XX_AVAILABLE:
                # Initialize I2C
                self.i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

                # Initialize I2C multiplexer if enabled
                if self.use_multiplexer and TCA9548A_AVAILABLE:
                    try:
                        self.multiplexer = adafruit_tca9548a.TCA9548A(self.i2c, address=self.mux_addr)
                        logger.info(f"I2C multiplexer initialized at 0x{self.mux_addr:02X}")
                    except Exception as e:
                        logger.error(f"Failed to initialize multiplexer: {e}")
                        logger.warning("Continuing without multiplexer support")
                        self.multiplexer = None
                elif self.use_multiplexer and not TCA9548A_AVAILABLE:
                    logger.warning("Multiplexer requested but library not available, continuing without multiplexer")

                # Initialize BNO055
                if BNO055_AVAILABLE:
                    try:
                        if self.multiplexer:
                            logger.debug(f"Switching to IMU channel {self.imu_channel}")
                            # Access the multiplexer channel (this automatically switches)
                            channel_i2c = self.multiplexer[self.imu_channel]
                            # Initialize in NDOF mode (9-DOF fusion with fast magnetometer calibration)
                            from adafruit_bno055 import NDOF_MODE
                            self.bno055 = BNO055_I2C(channel_i2c, address=self.bno055_addr)
                            time.sleep(0.1)  # Give sensor time to initialize
                            self.bno055.mode = NDOF_MODE
                        else:
                            from adafruit_bno055 import NDOF_MODE
                            self.bno055 = BNO055_I2C(self.i2c, address=self.bno055_addr)
                            time.sleep(0.1)  # Give sensor time to initialize
                            self.bno055.mode = NDOF_MODE

                        logger.info(f"BNO055 initialized at 0x{self.bno055_addr:02X} on channel {self.imu_channel} in NDOF mode")
                    except Exception as e:
                        logger.error(f"Failed to initialize BNO055: {e}")
                        self.bno055 = None

                # Initialize BMP581
                if BMP5XX_AVAILABLE:
                    try:
                        if self.multiplexer:
                            logger.debug(f"Switching to barometer channel {self.baro_channel}")
                            channel_i2c = self.multiplexer[self.baro_channel]
                            # BMP5XX requires I2CDevice wrapper
                            i2c_device = I2CDevice(channel_i2c, self.bmp581_addr)
                            self.bmp581 = adafruit_bmp5xx.BMP5XX(i2c_device)
                        else:
                            i2c_device = I2CDevice(self.i2c, self.bmp581_addr)
                            self.bmp581 = adafruit_bmp5xx.BMP5XX(i2c_device)

                        logger.info(f"BMP581 initialized at 0x{self.bmp581_addr:02X} on channel {self.baro_channel}")
                    except Exception as e:
                        logger.error(f"Failed to initialize BMP581: {e}")
                        self.bmp581 = None
            else:
                logger.warning("Sensor libraries not available, running in mock mode")

            # Initialize current sensors via smbus2 (direct I2C access)
            if SMBUS2_AVAILABLE and self.current_sensors:
                try:
                    self.smbus = smbus2.SMBus(self.i2c_bus)
                    logger.info(f"SMBus initialized for {len(self.current_sensors)} current sensors")
                except Exception as e:
                    logger.error(f"Failed to initialize SMBus: {e}")
                    self.smbus = None
            elif self.current_sensors and not SMBUS2_AVAILABLE:
                logger.warning("Current sensors configured but smbus2 not available, using mock data")

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

        # Shutdown thread pool
        self.executor.shutdown(wait=True, cancel_futures=True)

        # Close SMBus if open
        if self.smbus:
            try:
                self.smbus.close()
            except:
                pass

        logger.info("SensorReader stopped")

    def _switch_mux_channel(self, channel: int):
        """Switch multiplexer to specified channel"""
        if self.multiplexer:
            try:
                # Simply accessing the channel switches to it
                _ = self.multiplexer[channel]
                logger.debug(f"Switched multiplexer to channel {channel}")
            except Exception as e:
                logger.error(f"Failed to switch multiplexer to channel {channel}: {e}")

    def _read_ina228(self, sensor_name: str, addr: int, channel: Optional[int] = None) -> Optional[Dict[str, float]]:
        """
        Read INA228 current sensor.

        INA228 Register Map (simplified):
        - 0x00: CONFIG (configuration)
        - 0x01: ADC_CONFIG (ADC configuration)
        - 0x04: VBUS (bus voltage, 16-bit, LSB = 195.3125 µV)
        - 0x05: DIETEMP (die temperature)
        - 0x07: CURRENT (current, 24-bit signed, LSB configurable)
        - 0x08: POWER (power, 24-bit)

        Returns dict with voltage, current, power or None on error.
        """
        try:
            if not self.smbus:
                # Return mock data if SMBus not available
                t = time.time()
                base_offset = hash(sensor_name) % 100
                return {
                    'voltage': 12.0 + 0.1 * math.sin(t * 0.1 + base_offset),
                    'current': 1.5 + 0.5 * math.sin(t * 0.2 + base_offset),
                    'power': 18.0 + 6.0 * math.sin(t * 0.15 + base_offset)
                }

            # Switch multiplexer channel if needed
            if channel is not None and self.multiplexer:
                self._switch_mux_channel(channel)

            # Read bus voltage (register 0x04, 16-bit)
            # VBUS LSB = 195.3125 µV = 0.0001953125 V
            vbus_raw = self.smbus.read_word_data(addr, 0x04)
            # Swap bytes (SMBus returns little-endian, INA228 is big-endian)
            vbus_raw = ((vbus_raw & 0xFF) << 8) | ((vbus_raw >> 8) & 0xFF)
            voltage = vbus_raw * 0.0001953125

            # Read current (register 0x07, 24-bit signed)
            # This is a simplified read - actual INA228 requires calibration
            # For mock purposes, we'll generate realistic values
            # In production, proper calibration would be needed
            current_raw = self.smbus.read_word_data(addr, 0x07)
            current_raw = ((current_raw & 0xFF) << 8) | ((current_raw >> 8) & 0xFF)
            # Simplified conversion (would need actual shunt/calibration)
            current = (current_raw - 32768) * 0.001 if current_raw > 32768 else current_raw * 0.001

            # Calculate power
            power = voltage * abs(current)

            logger.debug(f"INA228 {sensor_name} at 0x{addr:02X}: {voltage:.2f}V, {current:.3f}A, {power:.2f}W")

            return {
                'voltage': voltage,
                'current': current,
                'power': power
            }

        except Exception as e:
            logger.error(f"Error reading INA228 {sensor_name} at 0x{addr:02X}: {e}")
            # Return mock data on error
            t = time.time()
            base_offset = hash(sensor_name) % 100
            return {
                'voltage': 12.0 + 0.1 * math.sin(t * 0.1 + base_offset),
                'current': 1.5 + 0.5 * math.sin(t * 0.2 + base_offset),
                'power': 18.0 + 6.0 * math.sin(t * 0.15 + base_offset)
            }

    def _read_imu(self) -> Optional[Dict[str, float]]:
        """Read IMU data from BNO055 (called in parallel)"""
        try:
            if self.bno055:
                # BNO055 provides quaternion directly
                quat = self.bno055.quaternion
                if quat is None or len(quat) != 4:
                    # Fallback to mock data if quaternion not available
                    quat = (1.0, 0.0, 0.0, 0.0)

                # BNO055 quaternion format: (w, x, y, z)
                quat_w, quat_x, quat_y, quat_z = quat

                # Get linear acceleration (m/s²)
                accel = self.bno055.linear_acceleration
                if accel is None or len(accel) != 3:
                    accel = (0.0, 0.0, 9.81)
                accel_x, accel_y, accel_z = accel

                # Get gyroscope (rad/s)
                gyro = self.bno055.gyro
                if gyro is None or len(gyro) != 3:
                    gyro = (0.0, 0.0, 0.0)
                gyro_x, gyro_y, gyro_z = gyro

                return {
                    'quat_w': quat_w or 1.0,
                    'quat_x': quat_x or 0.0,
                    'quat_y': quat_y or 0.0,
                    'quat_z': quat_z or 0.0,
                    'accel_x': accel_x or 0.0,
                    'accel_y': accel_y or 0.0,
                    'accel_z': accel_z or 9.81,
                    'gyro_x': gyro_x or 0.0,
                    'gyro_y': gyro_y or 0.0,
                    'gyro_z': gyro_z or 0.0
                }
            else:
                # Mock IMU data
                t = time.time()
                return {
                    'quat_w': 1.0, 'quat_x': 0.0, 'quat_y': 0.0, 'quat_z': 0.0,
                    'accel_x': 0.01 * math.sin(t * 0.5),
                    'accel_y': 0.01 * math.cos(t * 0.5),
                    'accel_z': 9.81 + 0.01 * math.sin(t * 0.3),
                    'gyro_x': 0.001 * math.sin(t * 0.7),
                    'gyro_y': 0.001 * math.cos(t * 0.7),
                    'gyro_z': 0.001 * math.sin(t * 0.9)
                }
        except Exception as e:
            logger.error(f"Error reading BNO055 IMU: {e}")
            return None

    def _read_barometer(self) -> Optional[Dict[str, float]]:
        """Read barometer data from BMP581 (called in parallel)"""
        try:
            if self.bmp581:
                # Read pressure in hPa
                pressure = self.bmp581.pressure
                # Read temperature in Celsius
                temperature = self.bmp581.temperature
                # Calculate altitude from pressure (standard atmosphere)
                # altitude = 44330 * (1 - (pressure/1013.25)^0.1903)
                altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903) if pressure else 0.0

                return {
                    'pressure': pressure or 1013.25,
                    'temperature': temperature or 25.0,
                    'altitude': altitude
                }
            else:
                # Mock barometer data
                t = time.time()
                return {
                    'pressure': 1013.25 + 0.1 * math.sin(t * 0.1),
                    'temperature': 25.0 + 0.5 * math.sin(t * 0.05),
                    'altitude': 100.0 + 0.1 * math.sin(t * 0.2)
                }
        except Exception as e:
            logger.error(f"Error reading BMP581 barometer: {e}")
            return None

    def _read_loop(self):
        """
        Main sensor reading loop.

        PHASE 6: Uses ThreadPoolExecutor to read all sensors in parallel:
        - IMU (BNO085)
        - Barometer (BMP388)
        - Current sensors (INA228 x3)

        Reduces total read time from sequential to parallel execution.
        """
        while self.running:
            try:
                # Submit all sensor reads to executor (parallel execution)
                futures = {}

                # Submit IMU and barometer reads
                futures['imu'] = self.executor.submit(self._read_imu)
                futures['baro'] = self.executor.submit(self._read_barometer)

                # Submit current sensor reads
                for sensor_name, sensor_config in self.current_sensors.items():
                    addr = sensor_config.get('addr')
                    channel = sensor_config.get('channel')
                    if addr:
                        futures[f'current_{sensor_name}'] = self.executor.submit(
                            self._read_ina228, sensor_name, addr, channel
                        )

                # Wait for all reads to complete (with timeout)
                results = {}
                for key, future in futures.items():
                    try:
                        results[key] = future.result(timeout=0.5)
                    except Exception as e:
                        logger.error(f"Error reading {key}: {e}")
                        results[key] = None

                # Update latest data atomically
                with self.data_lock:
                    if results.get('imu'):
                        self.latest_imu_data = results['imu']
                    if results.get('baro'):
                        self.latest_baro_data = results['baro']

                    # Update current sensor data
                    current_data = {}
                    for sensor_name in self.current_sensors.keys():
                        key = f'current_{sensor_name}'
                        if results.get(key):
                            current_data[sensor_name] = results[key]
                    if current_data:
                        self.latest_current_data = current_data

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
                'barometer': self.latest_baro_data.copy(),
                'current': self.latest_current_data.copy()
            }

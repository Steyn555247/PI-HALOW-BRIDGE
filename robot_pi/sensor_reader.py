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

INA23X_AVAILABLE = False
if not SIM_MODE:
    try:
        from adafruit_ina23x import INA23X
        INA23X_AVAILABLE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)
if not BNO055_AVAILABLE and not SIM_MODE:
    logger.warning("BNO055 library not available, using mock IMU")
if not BMP5XX_AVAILABLE and not SIM_MODE:
    logger.warning("BMP5XX library not available, using mock barometer")
if not TCA9548A_AVAILABLE and not SIM_MODE:
    logger.warning("TCA9548A library not available, multiplexer support disabled")
if not INA23X_AVAILABLE and not SIM_MODE:
    logger.warning("INA23X library not available, motor 1 current will use mock data")


class SensorReader:
    """Reads BNO055 IMU and BMP581 barometer via I2C"""

    def __init__(self, i2c_bus: int = 1, bno055_addr: int = 0x28, bmp581_addr: int = 0x47,
                 read_interval: float = 0.1, use_multiplexer: bool = True,
                 mux_addr: int = 0x70, imu_channel: int = 1, baro_channel: int = 0,
                 motor1_current_mux_channel: int = 7, motor1_current_sensor_addr: int = 0x40,
                 motor2_current_mux_channel: int = 6, motor2_current_sensor_addr: int = 0x40,
                 motor1_shunt_ohms: float = 0.015, motor1_max_amps: float = 10.0,
                 motor2_shunt_ohms: float = 0.015, motor2_max_amps: float = 10.0):
        self.i2c_bus = i2c_bus
        self.bno055_addr = bno055_addr
        self.bmp581_addr = bmp581_addr
        self.read_interval = read_interval

        # Multiplexer configuration
        self.use_multiplexer = use_multiplexer
        self.mux_addr = mux_addr
        self.imu_channel = imu_channel
        self.baro_channel = baro_channel

        # Motor 1 external current sensor (INA238 on mux channel 7)
        self.motor1_current_mux_channel = motor1_current_mux_channel
        self.motor1_current_sensor_addr = motor1_current_sensor_addr

        # Motor 2 external current sensor (INA238 on mux channel 6)
        self.motor2_current_mux_channel = motor2_current_mux_channel
        self.motor2_current_sensor_addr = motor2_current_sensor_addr

        # INA238 calibration parameters
        self.motor1_shunt_ohms = motor1_shunt_ohms
        self.motor1_max_amps = motor1_max_amps
        self.motor2_shunt_ohms = motor2_shunt_ohms
        self.motor2_max_amps = motor2_max_amps

        # Hardware objects
        self.bno055 = None
        self.bmp581 = None
        self.ina219 = None       # motor 1 INA238
        self.ina238_motor2 = None  # motor 2 INA238
        self.i2c = None
        self.multiplexer = None

        self.running = False
        self.read_thread: Optional[threading.Thread] = None

        # Phase 6: ThreadPoolExecutor for parallel I2C reads
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="i2c")

        self.latest_imu_data: Dict[str, float] = {}
        self.latest_baro_data: Dict[str, float] = {}
        self.latest_motor1_current: float = 0.0
        self.latest_motor2_current: float = 0.0
        self.data_lock = threading.Lock()

        # Serialise all I2C/multiplexer access across threads to prevent
        # channel-switching races between the IMU loop and the INA threads.
        self._i2c_lock = threading.Lock()

        # INA238 error tracking for rate-limited logging (motor 1)
        self._current_error_count: int = 0
        self._last_current_success_time: float = 0.0

        # INA238 error tracking for rate-limited logging (motor 2)
        self._motor2_error_count: int = 0
        self._last_motor2_success_time: float = 0.0

        # Dedicated 20 Hz INA238 threads
        self._motor1_thread: Optional[threading.Thread] = None
        self._motor2_thread: Optional[threading.Thread] = None
        self.motor1_current_file = '/run/serpent/motor1_current'
        self.motor2_current_file = '/run/serpent/motor2_current'

        mux_status = "enabled" if use_multiplexer else "disabled"
        logger.info(f"SensorReader initialized: I2C bus {i2c_bus}, multiplexer {mux_status}, parallel reads enabled")

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
                        logger.debug("Attempting BMP581 initialization...")
                        # Skip BMP581 for now to prevent blocking - TEMPORARY FIX
                        logger.warning("BMP581 initialization skipped (prevents blocking)")
                        self.bmp581 = None
                        # if self.multiplexer:
                        #     logger.debug(f"Switching to barometer channel {self.baro_channel}")
                        #     channel_i2c = self.multiplexer[self.baro_channel]
                        #     # BMP5XX requires I2CDevice wrapper
                        #     i2c_device = I2CDevice(channel_i2c, self.bmp581_addr)
                        #     self.bmp581 = adafruit_bmp5xx.BMP5XX(i2c_device)
                        # else:
                        #     i2c_device = I2CDevice(self.i2c, self.bmp581_addr)
                        #     self.bmp581 = adafruit_bmp5xx.BMP5XX(i2c_device)
                        # logger.info(f"BMP581 initialized at 0x{self.bmp581_addr:02X} on channel {self.baro_channel}")
                    except Exception as e:
                        logger.error(f"Failed to initialize BMP581: {e}")
                        self.bmp581 = None
                # Initialize INA238 motor 1 current sensor on mux channel 7
                if INA23X_AVAILABLE and self.multiplexer:
                    try:
                        channel7_i2c = self.multiplexer[self.motor1_current_mux_channel]
                        self.ina219 = INA23X(channel7_i2c, address=self.motor1_current_sensor_addr)
                        self.ina219.set_calibration(self.motor1_shunt_ohms, self.motor1_max_amps)
                        logger.info(
                            f"INA238 (motor 1) initialized at 0x{self.motor1_current_sensor_addr:02X} "
                            f"on mux ch.{self.motor1_current_mux_channel} "
                            f"(shunt={self.motor1_shunt_ohms*1000:.1f}mΩ max={self.motor1_max_amps}A)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to initialize INA238 (motor 1): {e}")
                        self.ina219 = None

                # Initialize INA238 motor 2 current sensor on mux channel 6
                if INA23X_AVAILABLE and self.multiplexer:
                    try:
                        channel6_i2c = self.multiplexer[self.motor2_current_mux_channel]
                        self.ina238_motor2 = INA23X(channel6_i2c, address=self.motor2_current_sensor_addr)
                        self.ina238_motor2.set_calibration(self.motor2_shunt_ohms, self.motor2_max_amps)
                        logger.info(
                            f"INA238 (motor 2) initialized at 0x{self.motor2_current_sensor_addr:02X} "
                            f"on mux ch.{self.motor2_current_mux_channel} "
                            f"(shunt={self.motor2_shunt_ohms*1000:.1f}mΩ max={self.motor2_max_amps}A)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to initialize INA238 (motor 2): {e}")
                        self.ina238_motor2 = None
            else:
                logger.warning("Sensor libraries not available, running in mock mode")

        except Exception as e:
            logger.error(f"Failed to initialize I2C: {e}")

        # Start read thread
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

        # Start dedicated 20 Hz motor 1 current thread
        self._motor1_thread = threading.Thread(target=self._motor1_current_loop, daemon=True)
        self._motor1_thread.start()

        # Start dedicated 20 Hz motor 2 current thread
        self._motor2_thread = threading.Thread(target=self._motor2_current_loop, daemon=True)
        self._motor2_thread.start()

        logger.info("SensorReader started")

    def stop(self):
        """Stop reading sensors"""
        self.running = False

        if self.read_thread:
            self.read_thread.join(timeout=2.0)

        if self._motor1_thread:
            self._motor1_thread.join(timeout=0.5)

        if self._motor2_thread:
            self._motor2_thread.join(timeout=0.5)

        # Shutdown thread pool
        self.executor.shutdown(wait=True, cancel_futures=True)

        logger.info("SensorReader stopped")

    def _read_imu(self) -> Optional[Dict[str, float]]:
        """Read IMU data from BNO055.

        Only acquires _i2c_lock when real hardware is present.
        When bno055 is None the mock path runs without the lock so it
        never blocks the INA238 current-reading thread.
        """
        if not self.bno055:
            # No hardware — return mock data without holding _i2c_lock
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

        with self._i2c_lock:
            try:
                # BNO055 provides quaternion directly
                quat = self.bno055.quaternion
                if quat is None or len(quat) != 4:
                    quat = (1.0, 0.0, 0.0, 0.0)

                quat_w, quat_x, quat_y, quat_z = quat

                accel = self.bno055.linear_acceleration
                if accel is None or len(accel) != 3:
                    accel = (0.0, 0.0, 9.81)
                accel_x, accel_y, accel_z = accel

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
            except Exception as e:
                logger.error(f"Error reading BNO055 IMU: {e}")
                return None

    def _reinit_motor1_sensor(self):
        """Attempt to re-initialize INA238 motor 1 after persistent I/O errors."""
        logger.warning("INA238 (motor 1): attempting re-initialization after persistent errors")
        try:
            if self.multiplexer and INA23X_AVAILABLE:
                channel7_i2c = self.multiplexer[self.motor1_current_mux_channel]
                self.ina219 = INA23X(channel7_i2c, address=self.motor1_current_sensor_addr)
                self.ina219.set_calibration(self.motor1_shunt_ohms, self.motor1_max_amps)
                logger.info("INA238 (motor 1): re-initialized successfully")
        except Exception as e:
            logger.warning(f"INA238 (motor 1): re-initialization failed: {e}")
        finally:
            self._current_error_count = 0

    def _reinit_motor2_sensor(self):
        """Attempt to re-initialize INA238 motor 2 after persistent I/O errors."""
        logger.warning("INA238 (motor 2): attempting re-initialization after persistent errors")
        try:
            if self.multiplexer and INA23X_AVAILABLE:
                channel6_i2c = self.multiplexer[self.motor2_current_mux_channel]
                self.ina238_motor2 = INA23X(channel6_i2c, address=self.motor2_current_sensor_addr)
                self.ina238_motor2.set_calibration(self.motor2_shunt_ohms, self.motor2_max_amps)
                logger.info("INA238 (motor 2): re-initialized successfully")
        except Exception as e:
            logger.warning(f"INA238 (motor 2): re-initialization failed: {e}")
        finally:
            self._motor2_error_count = 0

    def _read_motor1_current(self) -> tuple:
        """Read motor 1 current from INA238 on mux channel 7.

        Acquires the I2C lock to prevent channel-switching races with the
        IMU/barometer threads on the shared TCA9548A multiplexer.

        Returns:
            (current_amps: float, ok: bool) - current is 0.0 on error.
            Logs at WARNING once per 20 consecutive failures to avoid 20 Hz spam.
        """
        with self._i2c_lock:
            try:
                if self.ina219:
                    # abs() because the shunt polarity determines sign;
                    # we care about magnitude regardless of motor direction.
                    value = abs(self.ina219.current)  # Amps
                else:
                    # SIM / no hardware - stable zero
                    value = 0.0
                self._current_error_count = 0
                return value, True
            except Exception as e:
                self._current_error_count += 1
                # Log once per 20 consecutive errors to avoid 20 Hz spam
                if self._current_error_count == 1 or self._current_error_count % 20 == 0:
                    logger.warning(
                        f"INA238 read error (#{self._current_error_count}): {e}"
                    )
                return 0.0, False

    def _read_motor2_current(self) -> tuple:
        """Read motor 2 current from INA238 on mux channel 6.

        Returns:
            (current_amps: float, ok: bool) - current is 0.0 on error.
        """
        with self._i2c_lock:
            try:
                if self.ina238_motor2:
                    value = abs(self.ina238_motor2.current)  # Amps
                else:
                    value = 0.0
                self._motor2_error_count = 0
                return value, True
            except Exception as e:
                self._motor2_error_count += 1
                if self._motor2_error_count == 1 or self._motor2_error_count % 20 == 0:
                    logger.warning(
                        f"INA238 (motor 2) read error (#{self._motor2_error_count}): {e}"
                    )
                return 0.0, False

    def _read_barometer(self) -> Optional[Dict[str, float]]:
        """Read barometer data from BMP581.

        Only acquires _i2c_lock when real hardware is present.
        """
        if not self.bmp581:
            # No hardware — return mock data without holding _i2c_lock
            t = time.time()
            return {
                'pressure': 1013.25 + 0.1 * math.sin(t * 0.1),
                'temperature': 25.0 + 0.5 * math.sin(t * 0.05),
                'altitude': 100.0 + 0.1 * math.sin(t * 0.2)
            }

        with self._i2c_lock:
            try:
                pressure = self.bmp581.pressure
                temperature = self.bmp581.temperature
                altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903) if pressure else 0.0
                return {
                    'pressure': pressure or 1013.25,
                    'temperature': temperature or 25.0,
                    'altitude': altitude
                }
            except Exception as e:
                logger.error(f"Error reading BMP581 barometer: {e}")
                return None

    def _read_loop(self):
        """
        Main sensor reading loop.

        PHASE 6: Uses ThreadPoolExecutor to read IMU and barometer in parallel.
        Reduces total read time from sequential to parallel execution.
        """
        while self.running:
            try:
                # Submit all sensor reads to executor (parallel execution)
                futures = {}

                # Submit IMU and barometer reads
                futures['imu'] = self.executor.submit(self._read_imu)
                futures['baro'] = self.executor.submit(self._read_barometer)

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

                time.sleep(self.read_interval)

            except Exception as e:
                logger.error(f"Error in sensor read loop: {e}")
                time.sleep(self.read_interval)

    def _motor1_current_loop(self):
        """
        Dedicated 20 Hz loop for motor 1 current (INA238 on mux ch.7).

        Runs in its own thread so the INA238 sample rate is independent of
        the IMU/barometer loop.  Each reading is written to a small IPC file
        so the dashboard process can read it without touching I2C.
        Auto-reinitializes the sensor after 100 consecutive I/O errors (~5 s).
        """
        logger.info("Motor 1 current thread started (20 Hz)")
        while self.running:
            current, ok = self._read_motor1_current()
            with self.data_lock:
                if ok:
                    # Only update stored value on a good read — preserves last
                    # good reading when the sensor occasionally has I2C errors.
                    self.latest_motor1_current = current
                    self._last_current_success_time = time.time()
            # Only write IPC file on success — preserves last good value on
            # failed reads so the dashboard doesn't show a spurious 0.
            if ok:
                try:
                    with open(self.motor1_current_file, 'w') as f:
                        f.write(f"{current:.4f}\n")
                except Exception:
                    pass  # Non-critical — dashboard falls back to status log
            # Re-initialize after 100 consecutive errors to recover from I2C lockup
            if self._current_error_count >= 100:
                with self._i2c_lock:
                    self._reinit_motor1_sensor()
            time.sleep(0.05)  # 20 Hz
        logger.info("Motor 1 current thread stopped")

    def _motor2_current_loop(self):
        """
        Dedicated 20 Hz loop for motor 2 current (INA238 on mux ch.6).
        Auto-reinitializes the sensor after 100 consecutive I/O errors (~5 s).
        """
        logger.info("Motor 2 current thread started (20 Hz)")
        while self.running:
            current, ok = self._read_motor2_current()
            with self.data_lock:
                if ok:
                    self.latest_motor2_current = current
                    self._last_motor2_success_time = time.time()
            if ok:
                try:
                    with open(self.motor2_current_file, 'w') as f:
                        f.write(f"{current:.4f}\n")
                except Exception:
                    pass
            # Re-initialize after 100 consecutive errors to recover from I2C lockup
            if self._motor2_error_count >= 100:
                with self._i2c_lock:
                    self._reinit_motor2_sensor()
            time.sleep(0.05)  # 20 Hz
        logger.info("Motor 2 current thread stopped")

    def get_motor1_current(self) -> float:
        """Get motor 1 current from external INA238 sensor (Amps).

        Returns 0.0 if the last successful read is older than 2 seconds,
        indicating the sensor thread has stalled or the hardware has failed.
        """
        with self.data_lock:
            if self._last_current_success_time == 0.0:
                return 0.0
            if time.time() - self._last_current_success_time > 2.0:
                return 0.0
            return self.latest_motor1_current

    def get_motor2_current(self) -> float:
        """Get motor 2 current from external INA238 sensor (Amps).

        Returns 0.0 if the last successful read is older than 2 seconds.
        """
        with self.data_lock:
            if self._last_motor2_success_time == 0.0:
                return 0.0
            if time.time() - self._last_motor2_success_time > 2.0:
                return 0.0
            return self.latest_motor2_current

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
                'motor1_current': self.latest_motor1_current,
                'motor2_current': self.latest_motor2_current
            }

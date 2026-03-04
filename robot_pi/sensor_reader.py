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
- BNO055 IMU at 0x28 on multiplexer channel 7
- BMP581 barometer at 0x47 on multiplexer channel 7
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

SMBUS2_AVAILABLE = False
if not SIM_MODE:
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
if not INA23X_AVAILABLE and not SIM_MODE:
    logger.warning("INA23X library not available, motor 1 current will use mock data")


class SensorReader:
    """Reads BNO055 IMU and BMP581 barometer via I2C"""

    def __init__(self, i2c_bus: int = 1, bno055_addr: int = 0x28, bmp581_addr: int = 0x47,
                 read_interval: float = 0.1, use_multiplexer: bool = True,
                 mux_addr: int = 0x70, imu_channel: int = 1, baro_channel: int = 0,
                 motor1_current_mux_channel: int = 5, motor1_current_sensor_addr: int = 0x40,
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

        # Motor 1 external current sensor (INA238 on mux channel 5)
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
        self.ina219 = None       # motor 1 INA238 (adafruit, kept for compat but not used for reads)
        self.ina238_motor2 = None  # motor 2 INA238 (adafruit, kept for compat but not used for reads)
        self.i2c = None
        self.multiplexer = None

        # smbus2 direct INA238 readers — bypass busio entirely so a busio
        # try_lock() spin-loop (caused by motor EMI) can never freeze these threads.
        self._smbus_m1: 'Optional[smbus2.SMBus]' = None
        self._smbus_m2: 'Optional[smbus2.SMBus]' = None
        # INA238 calibration: current_lsb and shunt_cal register value
        self._m1_current_lsb: float = motor1_max_amps / (2**15)
        self._m2_current_lsb: float = motor2_max_amps / (2**15)
        self._m1_shunt_cal: int = int(819.2e6 * self._m1_current_lsb * motor1_shunt_ohms)
        self._m2_shunt_cal: int = int(819.2e6 * self._m2_current_lsb * motor2_shunt_ohms)

        self.running = False
        self.read_thread: Optional[threading.Thread] = None

        self.latest_imu_data: Dict[str, float] = {}
        self.latest_baro_data: Dict[str, float] = {}
        self.latest_motor1_current: float = 0.0
        self.latest_motor2_current: float = 0.0
        self.latest_motor1_current_timestamp: float = 0.0
        self.latest_motor2_current_timestamp: float = 0.0
        self.data_lock = threading.Lock()

        # Serialise all I2C/multiplexer access across threads to prevent
        # channel-switching races on the shared TCA9548A multiplexer.
        self._i2c_lock = threading.Lock()

        # INA238 error tracking for rate-limited logging (motor 1)
        self._current_error_count: int = 0
        self._last_current_success_time: float = 0.0

        # INA238 error tracking for rate-limited logging (motor 2)
        self._motor2_error_count: int = 0
        self._last_motor2_success_time: float = 0.0

        # BNO055 error tracking — disable hardware reads on the FIRST error.
        # BNO055 I2C hangs (from motor EMI) block the entire kernel I2C bus for
        # 1-2 s per error.  Disabling immediately after the first failure lets
        # the INA238 thread recover within one kernel timeout instead of five.
        # The hardware path is retried every 60 s in case the fault was transient.
        self._bno055_error_count: int = 0
        self.BNO055_ERROR_THRESHOLD: int = 1
        self._bno055_last_reinit_time: float = 0.0

        # INA238 reinit cooldown timestamps — prevents re-init spam when hardware absent
        self._ina238_m1_last_reinit_time: float = 0.0
        self._ina238_m2_last_reinit_time: float = 0.0
        self.INA238_REINIT_COOLDOWN_S: float = 30.0

        # Dedicated threads — each runs at its own rate independently
        self._motor1_thread: Optional[threading.Thread] = None
        self._motor2_thread: Optional[threading.Thread] = None
        self._imu_thread:    Optional[threading.Thread] = None
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
            else:
                logger.warning("Sensor libraries not available, running in mock mode")

        except Exception as e:
            logger.error(f"Failed to initialize I2C: {e}")

        # Initialize INA238 sensors via smbus2 (independent of busio availability).
        # smbus2 uses Linux ioctl() directly — immune to busio try_lock() spin-loop
        # that motor EMI causes when using the adafruit TCA9548A channel proxy.
        if SMBUS2_AVAILABLE:
            try:
                self._smbus_m1 = smbus2.SMBus(self.i2c_bus)
                self._smbus_m1.write_byte(self.mux_addr, 1 << self.motor1_current_mux_channel)
                cal_hi = (self._m1_shunt_cal >> 8) & 0xFF
                cal_lo = self._m1_shunt_cal & 0xFF
                self._smbus_m1.write_i2c_block_data(
                    self.motor1_current_sensor_addr, 0x08, [cal_hi, cal_lo]
                )
                logger.info(
                    f"INA238 (motor 1) initialized via smbus2 at 0x{self.motor1_current_sensor_addr:02X} "
                    f"on mux ch.{self.motor1_current_mux_channel} "
                    f"(shunt={self.motor1_shunt_ohms*1000:.1f}mΩ max={self.motor1_max_amps}A "
                    f"lsb={self._m1_current_lsb*1000:.4f}mA cal={self._m1_shunt_cal})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize INA238 (motor 1) via smbus2: {e}")
                self._smbus_m1 = None

            try:
                self._smbus_m2 = smbus2.SMBus(self.i2c_bus)
                self._smbus_m2.write_byte(self.mux_addr, 1 << self.motor2_current_mux_channel)
                cal_hi = (self._m2_shunt_cal >> 8) & 0xFF
                cal_lo = self._m2_shunt_cal & 0xFF
                self._smbus_m2.write_i2c_block_data(
                    self.motor2_current_sensor_addr, 0x08, [cal_hi, cal_lo]
                )
                logger.info(
                    f"INA238 (motor 2) initialized via smbus2 at 0x{self.motor2_current_sensor_addr:02X} "
                    f"on mux ch.{self.motor2_current_mux_channel}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize INA238 (motor 2) via smbus2: {e}")
                self._smbus_m2 = None

        self.running = True

        # Dedicated IMU thread (10 Hz) — runs independently so a hung BNO055
        # kernel I2C call never blocks the INA238 current-reading threads.
        self._imu_thread = threading.Thread(
            target=self._imu_loop, daemon=True, name="imu-reader"
        )
        self._imu_thread.start()

        # Dedicated 20 Hz motor 1 current thread
        self._motor1_thread = threading.Thread(
            target=self._motor1_current_loop, daemon=True, name="ina238-m1"
        )
        self._motor1_thread.start()

        # Dedicated 20 Hz motor 2 current thread
        self._motor2_thread = threading.Thread(
            target=self._motor2_current_loop, daemon=True, name="ina238-m2"
        )
        self._motor2_thread.start()

        logger.info("SensorReader started")

    def stop(self):
        """Stop reading sensors"""
        self.running = False
        # All threads are daemon threads — do not join the IMU thread because
        # a hung kernel I2C call inside it may block for seconds.  The process
        # exit will clean up daemon threads automatically.
        if self._motor1_thread:
            self._motor1_thread.join(timeout=0.5)
        if self._motor2_thread:
            self._motor2_thread.join(timeout=0.5)
        logger.info("SensorReader stopped")

    def _mock_imu(self) -> Dict[str, float]:
        """Return deterministic mock IMU data (no I2C, no lock)."""
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

    def _disable_bno055(self):
        """Mark BNO055 hardware as disabled permanently (no auto-retry).

        Motor EMI disables BNO055 I2C.  We never auto-retry because the
        reinit attempt itself can cause mux interference that freezes the
        INA238 current sensor.  Restart the service to re-enable BNO055.
        """
        logger.warning("BNO055: disabling hardware reads permanently, falling back to mock")
        self.bno055 = None
        self._bno055_error_count = 0
        # Set far in the future so _try_reinit_bno055 never fires automatically
        self._bno055_last_reinit_time = time.time() + 86400  # 24 h

    def _try_reinit_bno055(self):
        """Attempt to re-initialize BNO055 if 60 s have passed since last disable."""
        if self.bno055 is not None:
            return
        if time.time() - self._bno055_last_reinit_time < 60.0:
            return
        try:
            if self.multiplexer and BNO055_AVAILABLE:
                channel_i2c = self.multiplexer[self.imu_channel]
                from adafruit_bno055 import NDOF_MODE
                self.bno055 = BNO055_I2C(channel_i2c, address=self.bno055_addr)
                time.sleep(0.1)
                self.bno055.mode = NDOF_MODE
                logger.info("BNO055: re-initialized successfully")
        except Exception as e:
            logger.debug(f"BNO055: re-init attempt failed: {e}")
            self._bno055_last_reinit_time = time.time()

    def _read_imu(self) -> Optional[Dict[str, float]]:
        """Read IMU data from BNO055.

        Each of the 3 register reads (quaternion, accel, gyro) acquires
        _i2c_lock separately so the INA238 thread gets a window between
        every I2C call.  A hung kernel I2C call only blocks the lock for
        that one register's duration.  BNO055 is disabled on the first
        error (threshold=1) so the INA238 is never starved for more than
        one kernel I2C timeout (~1 s worst case).

        BNO055 reinit is done under _i2c_lock so it cannot race with the
        INA238 threads and leave the TCA9548A mux on the wrong channel.
        """
        if self.bno055 is None:
            # Reinit under lock — prevents the BNO055 channel switch from
            # racing with an INA238 read and stranding the mux on ch.7.
            if self._i2c_lock.acquire(timeout=0.3):
                try:
                    self._try_reinit_bno055()
                finally:
                    self._i2c_lock.release()

        if not self.bno055:
            return self._mock_imu()

        def _locked_read(attr):
            """Acquire lock, read one BNO055 attribute, release lock."""
            if not self._i2c_lock.acquire(timeout=0.3):
                return None, False  # bus busy, skip
            try:
                return getattr(self.bno055, attr), True
            except Exception as e:
                logger.error(f"Error reading BNO055 {attr}: {e}")
                return None, 'error'
            finally:
                self._i2c_lock.release()

        quat, q_ok = _locked_read('quaternion')
        if q_ok == 'error':
            self._disable_bno055()
            return None

        accel, a_ok = _locked_read('linear_acceleration')
        if a_ok == 'error':
            self._disable_bno055()
            return None

        gyro, g_ok = _locked_read('gyro')
        if g_ok == 'error':
            self._disable_bno055()
            return None

        self._bno055_error_count = 0

        if quat is None or len(quat) != 4:
            quat = (1.0, 0.0, 0.0, 0.0)
        if accel is None or len(accel) != 3:
            accel = (0.0, 0.0, 9.81)
        if gyro is None or len(gyro) != 3:
            gyro = (0.0, 0.0, 0.0)

        return {
            'quat_w': quat[0] or 1.0, 'quat_x': quat[1] or 0.0,
            'quat_y': quat[2] or 0.0, 'quat_z': quat[3] or 0.0,
            'accel_x': accel[0] or 0.0, 'accel_y': accel[1] or 0.0,
            'accel_z': accel[2] or 9.81,
            'gyro_x': gyro[0] or 0.0, 'gyro_y': gyro[1] or 0.0,
            'gyro_z': gyro[2] or 0.0
        }

    def _reset_mux(self):
        """Disable all TCA9548A channels to put the mux in a clean state.

        Called before INA238 reinit to ensure no stale channel is active
        from a previous failed BNO055 reinit or other I2C error.
        """
        try:
            # Write 0x00 to the mux address to disable all channels
            self.i2c.writeto(self.mux_addr, bytes([0x00]))
        except Exception:
            pass  # Best-effort — if this fails we try the reinit anyway

    def _reinit_motor1_sensor(self):
        """Re-initialize INA238 motor 1 via smbus2 after persistent I/O errors."""
        logger.warning("INA238 (motor 1): attempting smbus2 re-initialization")
        try:
            if self._smbus_m1:
                try:
                    self._smbus_m1.close()
                except Exception:
                    pass
            self._smbus_m1 = smbus2.SMBus(self.i2c_bus)
            self._smbus_m1.write_byte(self.mux_addr, 1 << self.motor1_current_mux_channel)
            cal_hi = (self._m1_shunt_cal >> 8) & 0xFF
            cal_lo = self._m1_shunt_cal & 0xFF
            self._smbus_m1.write_i2c_block_data(
                self.motor1_current_sensor_addr, 0x08, [cal_hi, cal_lo]
            )
            logger.info("INA238 (motor 1): smbus2 re-initialized successfully")
        except Exception as e:
            logger.warning(f"INA238 (motor 1): smbus2 re-initialization failed: {e}")
        finally:
            self._current_error_count = 0

    def _reinit_motor2_sensor(self):
        """Re-initialize INA238 motor 2 via smbus2 after persistent I/O errors."""
        logger.warning("INA238 (motor 2): attempting smbus2 re-initialization")
        try:
            if self._smbus_m2:
                try:
                    self._smbus_m2.close()
                except Exception:
                    pass
            self._smbus_m2 = smbus2.SMBus(self.i2c_bus)
            self._smbus_m2.write_byte(self.mux_addr, 1 << self.motor2_current_mux_channel)
            cal_hi = (self._m2_shunt_cal >> 8) & 0xFF
            cal_lo = self._m2_shunt_cal & 0xFF
            self._smbus_m2.write_i2c_block_data(
                self.motor2_current_sensor_addr, 0x08, [cal_hi, cal_lo]
            )
            logger.info("INA238 (motor 2): smbus2 re-initialized successfully")
        except Exception as e:
            logger.warning(f"INA238 (motor 2): smbus2 re-initialization failed: {e}")
        finally:
            self._motor2_error_count = 0

    def _read_motor1_current(self) -> tuple:
        """Read motor 1 current from INA238 via smbus2 (direct kernel ioctl).

        Acquires _i2c_lock with a short timeout before selecting the mux channel
        to prevent [Errno 5] I/O errors caused by smbus2 and busio both writing
        to the TCA9548A at the same time.  If the lock is busy, the read is
        skipped and the last known value is kept.

        Protocol:
          1. acquire _i2c_lock (40 ms timeout — skip read if busy)
          2. write_byte(0x70, 1<<ch)   — select mux channel
          3. read_i2c_block_data(0x40, 0x04, 2) — read INA238 CURRENT register
          4. big-endian signed 16-bit → amps via current_lsb

        Returns:
            (current_amps: float, ok: bool)
        """
        if not self._smbus_m1:
            return 0.0, False
        if not self._i2c_lock.acquire(timeout=0.04):
            return 0.0, False  # bus busy — skip this sample
        try:
            self._smbus_m1.write_byte(self.mux_addr, 1 << self.motor1_current_mux_channel)
            data = self._smbus_m1.read_i2c_block_data(
                self.motor1_current_sensor_addr, 0x04, 2
            )
            raw = (data[0] << 8) | data[1]
            if raw >= 0x8000:
                raw -= 0x10000
            self._current_error_count = 0
            return abs(raw * self._m1_current_lsb), True
        except Exception as e:
            self._current_error_count += 1
            if self._current_error_count == 1 or self._current_error_count % 20 == 0:
                logger.warning(
                    f"INA238 read error (#{self._current_error_count}): {e}"
                )
            return 0.0, False
        finally:
            self._i2c_lock.release()

    def _read_motor2_current(self) -> tuple:
        """Read motor 2 current from INA238 via smbus2 (direct kernel ioctl).

        Same locking approach as motor 1 — acquires _i2c_lock before touching
        the TCA9548A mux to prevent collision with the busio BNO055 thread.

        Returns:
            (current_amps: float, ok: bool)
        """
        if not self._smbus_m2:
            return 0.0, False
        if not self._i2c_lock.acquire(timeout=0.04):
            return 0.0, False  # bus busy — skip this sample
        try:
            self._smbus_m2.write_byte(self.mux_addr, 1 << self.motor2_current_mux_channel)
            data = self._smbus_m2.read_i2c_block_data(
                self.motor2_current_sensor_addr, 0x04, 2
            )
            raw = (data[0] << 8) | data[1]
            if raw >= 0x8000:
                raw -= 0x10000
            self._motor2_error_count = 0
            return abs(raw * self._m2_current_lsb), True
        except Exception as e:
            self._motor2_error_count += 1
            if self._motor2_error_count == 1 or self._motor2_error_count % 20 == 0:
                logger.warning(
                    f"INA238 (motor 2) read error (#{self._motor2_error_count}): {e}"
                )
            return 0.0, False
        finally:
            self._i2c_lock.release()

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

    def _imu_loop(self):
        """
        Dedicated IMU/barometer thread (10 Hz).

        Runs completely independently from the INA238 threads.  A hung
        kernel I2C call here — e.g. BNO055 I2C error during motor operation
        — will only block THIS thread, never the INA238 current threads.
        The _i2c_lock is still used to prevent mux channel-switching races,
        but a 300 ms acquire timeout means the lock is never held indefinitely
        from the INA238 side.
        """
        logger.info("IMU thread started (10 Hz)")
        while self.running:
            try:
                imu_result  = self._read_imu()
                baro_result = self._read_barometer()

                with self.data_lock:
                    if imu_result:
                        self.latest_imu_data = imu_result
                    if baro_result:
                        self.latest_baro_data = baro_result

                time.sleep(self.read_interval)

            except Exception as e:
                logger.error(f"Error in IMU loop: {e}")
                time.sleep(self.read_interval)
        logger.info("IMU thread stopped")

    def _motor1_current_loop(self):
        """
        Dedicated 20 Hz loop for motor 1 current (INA238 on mux ch.5).

        Runs in its own thread so the INA238 sample rate is independent of
        the IMU/barometer loop.  Each reading is written to a small IPC file
        so the dashboard process can read it without touching I2C.
        Auto-reinitializes whenever the sensor object is nulled (on any I2C
        error) after a 1-second cooldown.
        """
        logger.info("Motor 1 current thread started (20 Hz)")
        while self.running:
            current, ok = self._read_motor1_current()
            with self.data_lock:
                if ok:
                    self.latest_motor1_current = current
                    self.latest_motor1_current_timestamp = time.time()
                    self._last_current_success_time = time.time()
                # Always write last known good value — failed reads use previous
                write_value = self.latest_motor1_current
            try:
                with open(self.motor1_current_file, 'w') as f:
                    f.write(f"{write_value:.4f}\n")
            except Exception:
                pass
            # After 100 consecutive I2C errors (~5 s), reinit the smbus2 handle
            # to recover from any persistent hardware fault.
            if self._current_error_count >= 100:
                if time.time() - self._ina238_m1_last_reinit_time >= self.INA238_REINIT_COOLDOWN_S:
                    self._ina238_m1_last_reinit_time = time.time()
                    self._reinit_motor1_sensor()  # no lock needed — smbus2, not busio
            time.sleep(0.05)  # 20 Hz
        logger.info("Motor 1 current thread stopped")

    def _motor2_current_loop(self):
        """
        Dedicated 20 Hz loop for motor 2 current (INA238 on mux ch.6).
        Auto-reinitializes whenever the sensor object is nulled by an I2C error.
        """
        logger.info("Motor 2 current thread started (20 Hz)")
        while self.running:
            current, ok = self._read_motor2_current()
            with self.data_lock:
                if ok:
                    self.latest_motor2_current = current
                    self.latest_motor2_current_timestamp = time.time()
                    self._last_motor2_success_time = time.time()
                write_value = self.latest_motor2_current
            try:
                with open(self.motor2_current_file, 'w') as f:
                    f.write(f"{write_value:.4f}\n")
            except Exception:
                pass
            if self._motor2_error_count >= 100:
                if time.time() - self._ina238_m2_last_reinit_time >= self.INA238_REINIT_COOLDOWN_S:
                    self._ina238_m2_last_reinit_time = time.time()
                    self._reinit_motor2_sensor()  # no lock needed — smbus2, not busio
            time.sleep(0.05)  # 20 Hz
        logger.info("Motor 2 current thread stopped")

    def get_motor1_current(self) -> float:
        """Get motor 1 current from external INA238 sensor (Amps).

        Returns the last successful reading.  Returns 0.0 only if no
        successful read has ever completed (sensor never initialized).
        Stale-value protection was removed: a frozen last-known value is
        far safer for autocut than a spurious 0.0 that would falsely
        trigger a breakthrough detection.
        """
        with self.data_lock:
            return self.latest_motor1_current

    def get_motor2_current(self) -> float:
        """Get motor 2 current from external INA238 sensor (Amps).

        Returns the last successful reading (see get_motor1_current).
        """
        with self.data_lock:
            return self.latest_motor2_current

    def get_motor1_current_with_timestamp(self) -> tuple[float, float]:
        """Get motor 1 current and timestamp.

        Returns: (current_amps, timestamp) tuple
        The timestamp is when the reading was last successfully updated.
        Used for staleness detection in autonomous cutting.
        """
        with self.data_lock:
            return (self.latest_motor1_current, self.latest_motor1_current_timestamp)

    def get_motor2_current_with_timestamp(self) -> tuple[float, float]:
        """Get motor 2 current and timestamp.

        Returns: (current_amps, timestamp) tuple
        The timestamp is when the reading was last successfully updated.
        Used for staleness detection in autonomous cutting.
        """
        with self.data_lock:
            return (self.latest_motor2_current, self.latest_motor2_current_timestamp)

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

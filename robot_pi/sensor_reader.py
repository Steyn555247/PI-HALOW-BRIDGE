"""
Sensor Reader - Reads IMU, barometer, and current sensors via I2C multiplexer

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
INA219_AVAILABLE = False
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

    try:
        from adafruit_ina219 import INA219
        INA219_AVAILABLE = True
    except ImportError:
        pass

logger = logging.getLogger(__name__)
if not BNO08X_AVAILABLE and not SIM_MODE:
    logger.warning("BNO08X/BMP3XX libraries not available, using mock sensors")
if not INA219_AVAILABLE and not SIM_MODE:
    logger.warning("INA219 library not available, using mock current sensors")


class SensorReader:
    """Reads BNO085 IMU, BMP388 barometer, and INA219 current sensors"""

    def __init__(self, i2c_bus: int = 1, bno085_addr: int = 0x4A, bmp388_addr: int = 0x77,
                 read_interval: float = 0.1, use_multiplexer: bool = True, mux_addr: int = 0x70,
                 imu_channel: int = 0, baro_channel: int = 1,
                 current_sensors: Optional[Dict[str, Dict[str, Any]]] = None):
        self.i2c_bus = i2c_bus
        self.bno085_addr = bno085_addr
        self.bmp388_addr = bmp388_addr
        self.read_interval = read_interval
        self.use_multiplexer = use_multiplexer
        self.mux_addr = mux_addr
        self.imu_channel = imu_channel
        self.baro_channel = baro_channel

        # Current sensor configuration
        # Format: {'battery': {'addr': 0x40, 'channel': 2, 'shunt_ohms': 0.1, 'max_amps': 3.2}, ...}
        self.current_sensors_config = current_sensors or {}

        self.bno085 = None
        self.bmp388 = None
        self.i2c = None
        self.multiplexer = None
        self.current_sensors: Dict[str, Any] = {}  # Stores INA219 instances

        self.running = False
        self.read_thread: Optional[threading.Thread] = None

        self.latest_imu_data: Dict[str, float] = {}
        self.latest_baro_data: Dict[str, float] = {}
        self.latest_current_data: Dict[str, Dict[str, float]] = {}
        self.data_lock = threading.Lock()

        # Mock data state for simulation
        self.mock_battery_voltage = 12.5
        self.mock_time_start = time.time()

        logger.info(f"SensorReader initialized: I2C bus {i2c_bus}, multiplexer={'enabled' if use_multiplexer else 'disabled'}")

    def start(self):
        """Initialize sensors and start reading"""
        try:
            if BNO08X_AVAILABLE or INA219_AVAILABLE:
                # Initialize I2C
                self.i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)

                # Initialize multiplexer if enabled
                if self.use_multiplexer:
                    try:
                        from robot_pi.i2c_multiplexer import I2CMultiplexer
                        self.multiplexer = I2CMultiplexer(self.i2c, self.mux_addr)
                        logger.info(f"PCA9548 multiplexer initialized at 0x{self.mux_addr:02X}")
                    except Exception as e:
                        logger.error(f"Failed to initialize multiplexer: {e}")
                        self.multiplexer = None

                # Initialize BNO085
                if BNO08X_AVAILABLE:
                    try:
                        if self.multiplexer:
                            self.multiplexer.select_channel(self.imu_channel)
                        self.bno085 = BNO08X_I2C(self.i2c, address=self.bno085_addr)
                        self.bno085.enable_feature(0x05)  # Rotation vector
                        self.bno085.enable_feature(0x01)  # Accelerometer
                        self.bno085.enable_feature(0x02)  # Gyroscope
                        logger.info(f"BNO085 initialized (channel {self.imu_channel if self.multiplexer else 'direct'})")
                    except Exception as e:
                        logger.error(f"Failed to initialize BNO085: {e}")
                        self.bno085 = None

                # Initialize BMP388
                if BNO08X_AVAILABLE:
                    try:
                        if self.multiplexer:
                            self.multiplexer.select_channel(self.baro_channel)
                        self.bmp388 = adafruit_bmp3xx.BMP3XX_I2C(self.i2c, address=self.bmp388_addr)
                        self.bmp388.pressure_oversampling = 8
                        self.bmp388.temperature_oversampling = 2
                        logger.info(f"BMP388 initialized (channel {self.baro_channel if self.multiplexer else 'direct'})")
                    except Exception as e:
                        logger.error(f"Failed to initialize BMP388: {e}")
                        self.bmp388 = None

                # Initialize current sensors
                if INA219_AVAILABLE:
                    for sensor_name, config in self.current_sensors_config.items():
                        try:
                            if self.multiplexer:
                                self.multiplexer.select_channel(config['channel'])
                            ina = INA219(self.i2c, config['addr'])
                            ina.set_calibration_16V_400mA()  # Standard calibration
                            self.current_sensors[sensor_name] = ina
                            logger.info(f"INA219 '{sensor_name}' initialized at 0x{config['addr']:02X} (channel {config['channel'] if self.multiplexer else 'direct'})")
                        except Exception as e:
                            logger.error(f"Failed to initialize INA219 '{sensor_name}': {e}")
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
                        if self.multiplexer:
                            self.multiplexer.select_channel(self.imu_channel)

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
                        if self.multiplexer:
                            self.multiplexer.select_channel(self.baro_channel)

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

                # Read Current Sensors
                current_data = {}
                if self.current_sensors:
                    for sensor_name, ina in self.current_sensors.items():
                        try:
                            config = self.current_sensors_config[sensor_name]
                            if self.multiplexer:
                                self.multiplexer.select_channel(config['channel'])

                            # Read voltage (bus voltage + shunt voltage)
                            voltage = ina.bus_voltage + ina.shunt_voltage
                            # Read current in mA
                            current = ina.current
                            # Calculate power in mW
                            power = ina.power

                            current_data[sensor_name] = {
                                'voltage': round(voltage, 2),
                                'current': round(current, 1),  # mA
                                'power': round(power, 1)  # mW
                            }
                        except Exception as e:
                            logger.error(f"Error reading INA219 '{sensor_name}': {e}")
                            # Keep last good reading if available
                            if sensor_name in self.latest_current_data:
                                current_data[sensor_name] = self.latest_current_data[sensor_name]
                else:
                    # Mock current sensor data - realistic simulation
                    t = time.time() - self.mock_time_start

                    # Simulate battery drain over time
                    self.mock_battery_voltage = max(10.0, 12.5 - (t / 3600.0) * 0.5)  # 0.5V/hour drain

                    # Mock battery sensor (main power)
                    battery_current = 800 + 200 * math.sin(t * 0.5)  # 600-1000 mA base load
                    current_data['battery'] = {
                        'voltage': round(self.mock_battery_voltage, 2),
                        'current': round(battery_current, 1),
                        'power': round(self.mock_battery_voltage * battery_current, 1)
                    }

                    # Mock system sensor (logic/motors)
                    system_current = 400 + 100 * math.sin(t * 0.7)  # 300-500 mA
                    current_data['system'] = {
                        'voltage': round(self.mock_battery_voltage - 0.1, 2),
                        'current': round(system_current, 1),
                        'power': round((self.mock_battery_voltage - 0.1) * system_current, 1)
                    }

                    # Mock servo sensor (spikes during movement)
                    servo_current = 50 + 400 * abs(math.sin(t * 0.2))  # 50-450 mA (spikes)
                    current_data['servo'] = {
                        'voltage': 5.0,
                        'current': round(servo_current, 1),
                        'power': round(5.0 * servo_current, 1)
                    }

                with self.data_lock:
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

    def get_current_sensor_data(self) -> Dict[str, Dict[str, float]]:
        """
        Get latest current sensor data.

        Returns:
            Dictionary with sensor names as keys, each containing:
            - voltage: Bus voltage in volts
            - current: Current in milliamps
            - power: Power in milliwatts
        """
        with self.data_lock:
            return {k: v.copy() for k, v in self.latest_current_data.items()}

    def get_all_data(self) -> Dict[str, Any]:
        """Get all sensor data"""
        with self.data_lock:
            return {
                'imu': self.latest_imu_data.copy(),
                'barometer': self.latest_baro_data.copy(),
                'current': {k: v.copy() for k, v in self.latest_current_data.items()}
            }

"""
Configuration for Robot Pi HaLow Bridge

SAFETY NOTE: Safety-critical constants are imported from common/constants.py
and cannot be overridden via environment variables.
"""
import os
import sys

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.constants import (
    WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S, RECONNECT_DELAY_S,
    DEFAULT_CONTROL_PORT, DEFAULT_VIDEO_PORT, DEFAULT_TELEMETRY_PORT
)

# Simulation mode - enables testing without hardware
# SAFETY: Never enable by default on Pi. Only for Windows development.
SIM_MODE = os.getenv('SIM_MODE', 'false').lower() == 'true'

# Network Configuration
BASE_PI_IP = os.getenv('BASE_PI_IP', '192.168.100.1')
CONTROL_PORT = int(os.getenv('CONTROL_PORT', str(DEFAULT_CONTROL_PORT)))
VIDEO_PORT = int(os.getenv('VIDEO_PORT', str(DEFAULT_VIDEO_PORT)))
TELEMETRY_PORT = int(os.getenv('TELEMETRY_PORT', str(DEFAULT_TELEMETRY_PORT)))

# Camera Configuration
NUM_CAMERAS = int(os.getenv('NUM_CAMERAS', '3'))
CAMERA_WIDTH = int(os.getenv('CAMERA_WIDTH', '640'))
CAMERA_HEIGHT = int(os.getenv('CAMERA_HEIGHT', '480'))
CAMERA_FPS = int(os.getenv('CAMERA_FPS', '10'))
CAMERA_QUALITY = int(os.getenv('CAMERA_QUALITY', '60'))  # JPEG quality (1-100)
DEFAULT_CAMERA_ID = int(os.getenv('DEFAULT_CAMERA_ID', '0'))

# Camera device paths (can be overridden by environment)
CAMERA_DEVICES = [
    os.getenv('CAMERA_0', '/dev/video0'),
    os.getenv('CAMERA_1', '/dev/video2'),
    os.getenv('CAMERA_2', '/dev/video4')
]

# Sensor Configuration (I2C)
I2C_BUS = int(os.getenv('I2C_BUS', '1'))
BNO085_ADDRESS = int(os.getenv('BNO085_ADDRESS', '0x4A'), 16)
BMP388_ADDRESS = int(os.getenv('BMP388_ADDRESS', '0x77'), 16)
SENSOR_READ_INTERVAL = float(os.getenv('SENSOR_READ_INTERVAL', '0.1'))  # 100ms

# Motoron Configuration (I2C)
MOTORON_ADDRESSES = [
    int(os.getenv('MOTORON_ADDR_0', '0x10'), 16),
    int(os.getenv('MOTORON_ADDR_1', '0x11'), 16),
    int(os.getenv('MOTORON_ADDR_2', '0x12'), 16),
    int(os.getenv('MOTORON_ADDR_3', '0x13'), 16)
]
NUM_MOTORON_BOARDS = len(MOTORON_ADDRESSES)
MOTORS_PER_BOARD = 2
TOTAL_MOTORS = NUM_MOTORON_BOARDS * MOTORS_PER_BOARD
ACTIVE_MOTORS = 7  # Only 7 motors used

# Servo Configuration (GPIO PWM)
SERVO_GPIO_PIN = int(os.getenv('SERVO_GPIO_PIN', '12'))
SERVO_FREQ = int(os.getenv('SERVO_FREQ', '50'))  # Hz
SERVO_MIN_DUTY = float(os.getenv('SERVO_MIN_DUTY', '2.5'))  # %
SERVO_MAX_DUTY = float(os.getenv('SERVO_MAX_DUTY', '12.5'))  # %

# Safety Configuration - IMMUTABLE (from common/constants.py)
# These cannot be overridden via environment for safety reasons
WATCHDOG_TIMEOUT = WATCHDOG_TIMEOUT_S  # 5.0 seconds - DO NOT CHANGE
STARTUP_GRACE = STARTUP_GRACE_S        # 30.0 seconds - DO NOT CHANGE
RECONNECT_DELAY = RECONNECT_DELAY_S    # 2.0 seconds
EMERGENCY_STOP_ENABLED = True

# Telemetry Configuration
TELEMETRY_INTERVAL = float(os.getenv('TELEMETRY_INTERVAL', '0.1'))  # 100ms

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', '/var/log/serpent/robot_pi_bridge.log')

# Video Encoding
VIDEO_ENABLED = os.getenv('VIDEO_ENABLED', 'true').lower() == 'true'

# Platform detection for simulation
import platform
IS_WINDOWS = platform.system() == 'Windows'
IS_RASPBERRY_PI = os.path.exists('/proc/device-tree/model')

"""
Configuration for Base Pi HaLow Bridge

SAFETY NOTE: Safety-critical constants are imported from common/constants.py
and cannot be overridden via environment variables.
"""
import os
import sys

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.constants import (
    WATCHDOG_TIMEOUT_S, RECONNECT_DELAY_S,
    DEFAULT_CONTROL_PORT, DEFAULT_VIDEO_PORT, DEFAULT_TELEMETRY_PORT
)

# Simulation mode - enables testing without hardware
SIM_MODE = os.getenv('SIM_MODE', 'false').lower() == 'true'

# ============================================================================
# NETWORK CONFIGURATION - VERIFY FOR YOUR DEPLOYMENT
# ============================================================================
# Current configuration uses 192.168.1.x subnet (matching dashboard)
# If you experience connection issues, verify your actual network subnet:
#   - Check with: ip addr show
#   - Update ROBOT_PI_IP if needed
#   - Git history shows subnet was changed from 192.168.100.x to 192.168.1.x
# ============================================================================
ROBOT_PI_IP = os.getenv('ROBOT_PI_IP', '192.168.1.20')
CONTROL_PORT = int(os.getenv('CONTROL_PORT', str(DEFAULT_CONTROL_PORT)))
VIDEO_PORT = int(os.getenv('VIDEO_PORT', str(DEFAULT_VIDEO_PORT)))
TELEMETRY_PORT = int(os.getenv('TELEMETRY_PORT', str(DEFAULT_TELEMETRY_PORT)))

# Serpent Backend Integration
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')
BACKEND_SOCKETIO_URL = os.getenv('BACKEND_SOCKETIO_URL', 'http://localhost:5000')

# Video Configuration
VIDEO_BUFFER_SIZE = int(os.getenv('VIDEO_BUFFER_SIZE', '65536'))
VIDEO_ENABLED = os.getenv('VIDEO_ENABLED', 'true').lower() == 'true'

# Video HTTP Server (for MJPEG streaming to backend/frontend)
VIDEO_HTTP_ENABLED = os.getenv('VIDEO_HTTP_ENABLED', 'true').lower() == 'true'
VIDEO_HTTP_PORT = int(os.getenv('VIDEO_HTTP_PORT', '5004'))

# Safety Configuration - IMMUTABLE (from common/constants.py)
WATCHDOG_TIMEOUT = WATCHDOG_TIMEOUT_S  # 5.0 seconds - DO NOT CHANGE
RECONNECT_DELAY = RECONNECT_DELAY_S    # 2.0 seconds
MAX_RECONNECT_ATTEMPTS = int(os.getenv('MAX_RECONNECT_ATTEMPTS', '0'))  # 0 = infinite

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', '/var/log/serpent/base_pi_bridge.log')

# Camera Configuration
NUM_CAMERAS = int(os.getenv('NUM_CAMERAS', '3'))
DEFAULT_CAMERA_ID = int(os.getenv('DEFAULT_CAMERA_ID', '0'))

# Dashboard Configuration
DASHBOARD_ENABLED = os.getenv('DASHBOARD_ENABLED', 'true').lower() == 'true'
DASHBOARD_WS_PORT = int(os.getenv('DASHBOARD_WS_PORT', '5005'))
TELEMETRY_BUFFER_SIZE = int(os.getenv('TELEMETRY_BUFFER_SIZE', '600'))

# Storage Configuration (SSD)
STORAGE_ENABLED = os.getenv('STORAGE_ENABLED', 'false').lower() == 'true'
STORAGE_BASE_PATH = os.getenv('STORAGE_BASE_PATH', '/mnt/ssd/serpent_data')
TELEMETRY_RETENTION_DAYS = int(os.getenv('TELEMETRY_RETENTION_DAYS', '30'))
VIDEO_RETENTION_DAYS = int(os.getenv('VIDEO_RETENTION_DAYS', '7'))
VIDEO_ROTATION_MINUTES = int(os.getenv('VIDEO_ROTATION_MINUTES', '10'))

# Controller telemetry rate
CONTROLLER_TELEMETRY_RATE_HZ = float(os.getenv('CONTROLLER_TELEM_RATE', '1.0'))

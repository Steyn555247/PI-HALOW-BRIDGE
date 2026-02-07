"""
Dashboard Configuration

Configurable via environment variables:
- DASHBOARD_PORT: Web server port (default: 5005 for robot, 5006 for base)
- DASHBOARD_ROLE: 'robot_pi' | 'base_pi' | 'auto' (default: 'auto')
- ENABLE_DIRECT_INSPECTION: Import bridge modules for real-time data
- ENABLE_SERVICE_CONTROL: Allow service restart actions (requires sudo)
"""

import os
import socket

# Network Configuration
ROBOT_PI_IP = '192.168.1.20'
BASE_PI_IP = '192.168.1.10'

# Ports (from common/constants.py)
CONTROL_PORT = 5001
VIDEO_PORT = 5002
TELEMETRY_PORT = 5003
BACKEND_VIDEO_PORT = 5004

# Auto-detect role based on hostname/IP
def detect_role():
    """Auto-detect if running on robot_pi or base_pi"""
    hostname = socket.gethostname().lower()

    if 'robot' in hostname:
        return 'robot_pi'
    elif 'base' in hostname or 'hub' in hostname:
        return 'base_pi'

    # Try to detect by IP address
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        if local_ip == ROBOT_PI_IP:
            return 'robot_pi'
        elif local_ip == BASE_PI_IP:
            return 'base_pi'
    except:
        pass

    return 'robot_pi'  # Default fallback

# Dashboard Configuration
DASHBOARD_ROLE = os.environ.get('DASHBOARD_ROLE', 'auto')
if DASHBOARD_ROLE == 'auto':
    DASHBOARD_ROLE = detect_role()

DASHBOARD_PORT = int(os.environ.get('DASHBOARD_PORT',
                                     5005 if DASHBOARD_ROLE == 'robot_pi' else 5006))

# Feature Flags
ENABLE_DIRECT_INSPECTION = os.environ.get('ENABLE_DIRECT_INSPECTION', 'True').lower() == 'true'
ENABLE_SERVICE_CONTROL = os.environ.get('ENABLE_SERVICE_CONTROL', 'False').lower() == 'true'

# Safety Feature Toggles (for local testing only)
# WARNING: Disabling watchdog removes critical safety protections
# Only disable for local manual testing where external control is not expected
DISABLE_WATCHDOG_FOR_LOCAL_TESTING = os.environ.get('DISABLE_WATCHDOG_FOR_LOCAL_TESTING', 'True').lower() == 'true'

# Update Intervals
STATUS_UPDATE_INTERVAL = 1.0  # seconds - WebSocket push rate
STATUS_CACHE_TTL = 1.0  # seconds - Cache aggregated status

# Systemd Services
ROBOT_BRIDGE_SERVICE = 'serpent-robot-bridge.service'
BASE_BRIDGE_SERVICE = 'serpent-base-bridge.service'
BACKEND_SERVICE = 'serpent-backend.service'

# Role-aware service mapping: only check services that exist on this Pi
ROLE_SERVICES = {
    'robot_pi': [ROBOT_BRIDGE_SERVICE],
    'base_pi': [BASE_BRIDGE_SERVICE, BACKEND_SERVICE],
}

# Log Configuration
DEFAULT_LOG_LINES = 100
MAX_LOG_LINES = 1000

# Video Configuration
VIDEO_STREAM_URL = f"http://{BASE_PI_IP}:{BACKEND_VIDEO_PORT}/video"

# Issue Detection Thresholds
ESTOP_WARN_AGE_S = 30
CONTROL_AGE_STALE_MS = 5000
VIDEO_DROP_RATE_WARN = 0.10  # 10%
CAMERA_ERROR_THRESHOLD = 10

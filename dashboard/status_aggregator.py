"""
Status Aggregator

Collects and aggregates system status from multiple sources:
1. JSON logs from systemd journal (primary, always works)
2. Direct component inspection (optional, when available)
3. Telemetry stream (Base Pi only)
"""

import time
import logging
from typing import Dict, Optional
import sys
from pathlib import Path

from . import config
from . import log_parser

logger = logging.getLogger(__name__)

# Cache
_status_cache = None
_cache_timestamp = 0


def get_aggregated_status() -> Dict:
    """
    Get unified system status from all available sources.

    Returns:
        Dictionary with complete system status including:
        - role: 'robot_pi' or 'base_pi'
        - connections: Status of all network connections
        - sensors: Sensor data (if available)
        - actuators: Motor/servo status (if available)
        - video: Video streaming stats (if available)
        - estop: E-STOP status and reason
        - health: Overall system health indicators
        - timestamp: Status collection timestamp
    """
    global _status_cache, _cache_timestamp

    # Return cached status if still valid
    now = time.time()
    if _status_cache and (now - _cache_timestamp) < config.STATUS_CACHE_TTL:
        return _status_cache

    # Collect status
    if config.DASHBOARD_ROLE == 'robot_pi':
        status = _collect_robot_status()
    else:
        status = _collect_base_status()

    # Add metadata
    status['role'] = config.DASHBOARD_ROLE
    status['timestamp'] = now

    # Cache the result
    _status_cache = status
    _cache_timestamp = now

    return status


def _collect_robot_status() -> Dict:
    """Collect status from Robot Pi bridge"""
    status = {
        'connections': {},
        'sensors': {},
        'actuators': {},
        'video': {},
        'estop': {},
        'health': {}
    }

    # 1. Parse logs for connection status
    log_status = log_parser.get_latest_status_event(config.ROBOT_BRIDGE_SERVICE)

    if log_status:
        status['connections'] = {
            'control': 'connected' if log_status.get('control_connected') else 'disconnected',
            'control_established': log_status.get('control_established', False),
            'control_age_ms': log_status.get('control_age_ms', 0),
            'telemetry': 'connected' if log_status.get('telemetry_connected') else 'disconnected',
        }

        status['estop'] = {
            'engaged': log_status.get('estop_engaged', False),
            'reason': log_status.get('estop_reason', 'unknown'),
        }

        status['health'] = {
            'uptime_s': log_status.get('uptime_s', 0),
            'psk_valid': log_status.get('psk_valid', False),
        }
    else:
        # No recent logs - service may be down
        status['connections'] = {
            'control': 'unknown',
            'telemetry': 'unknown',
        }
        status['estop'] = {'engaged': False, 'reason': 'unknown'}
        status['health'] = {'uptime_s': 0, 'psk_valid': False}

    # 2. Direct inspection (optional)
    if config.ENABLE_DIRECT_INSPECTION:
        _add_direct_robot_data(status)

    return status


def _collect_base_status() -> Dict:
    """Collect status from Base Pi bridge"""
    status = {
        'connections': {},
        'sensors': {},
        'actuators': {},
        'video': {},
        'estop': {},
        'health': {}
    }

    # Parse logs for connection status
    log_status = log_parser.get_latest_status_event(config.BASE_BRIDGE_SERVICE)

    # Fallback: If base bridge logs not found, try robot bridge (for dev/test systems)
    using_robot_logs = False
    if not log_status:
        logger.debug("No base bridge logs found, trying robot bridge as fallback")
        log_status = log_parser.get_latest_status_event(config.ROBOT_BRIDGE_SERVICE)
        using_robot_logs = True

    if log_status:
        # Handle different log formats (base vs robot bridge)
        if using_robot_logs:
            # Robot bridge format
            status['connections'] = {
                'backend': 'unknown',  # Robot bridge doesn't know about backend
                'control': 'connected' if log_status.get('control_connected') else 'disconnected',
                'telemetry': 'connected' if log_status.get('telemetry_connected') else 'disconnected',
                'video': 'unknown',  # Video status not in robot logs
            }
            status['estop'] = {
                'engaged': log_status.get('estop_engaged', False),
                'reason': log_status.get('estop_reason', 'unknown'),
            }
        else:
            # Base bridge format
            status['connections'] = {
                'backend': log_status.get('backend', 'unknown'),
                'control': log_status.get('control', 'unknown'),
                'telemetry': log_status.get('telemetry', 'unknown'),
                'video': log_status.get('video', 'unknown'),
            }
            status['estop'] = {
                'engaged': log_status.get('robot_estop', False),
                'reason': 'forwarded from robot',
            }

        status['health'] = {
            'psk_valid': log_status.get('psk_valid', False),
            'uptime_s': log_status.get('uptime_s', 0) if using_robot_logs else 0,
        }
    else:
        status['connections'] = {
            'backend': 'unknown',
            'control': 'unknown',
            'telemetry': 'unknown',
            'video': 'unknown',
        }
        status['estop'] = {'engaged': False, 'reason': 'unknown'}
        status['health'] = {'psk_valid': False}

    # Direct inspection (optional)
    if config.ENABLE_DIRECT_INSPECTION:
        _add_direct_base_data(status)

    return status


def _add_direct_robot_data(status: Dict):
    """
    Add real-time data from direct component inspection (Robot Pi).
    Gracefully falls back if imports fail.
    """
    try:
        # Add project root to path
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Try importing video_capture for stats
        try:
            from robot_pi import video_capture
            video_stats = video_capture.get_stats()
            status['video'] = {
                'frames_sent': video_stats.get('frames_sent', 0),
                'frames_dropped': video_stats.get('frames_dropped', 0),
                'drop_rate': video_stats.get('drop_rate', 0.0),
                'camera_errors': video_stats.get('camera_errors', 0),
                'active_camera': video_stats.get('active_camera_id', 0),
            }
        except ImportError as e:
            logger.debug(f"Cannot import video_capture: {e}")
        except Exception as e:
            logger.warning(f"Failed to get video stats: {e}")

        # Try importing actuator_controller for motor/estop data
        try:
            from robot_pi import actuator_controller
            estop_info = actuator_controller.get_estop_info()
            motor_currents = actuator_controller.get_motor_currents()

            status['estop'].update({
                'engaged': estop_info.get('engaged', False),
                'reason': estop_info.get('reason', 'unknown'),
                'age_s': estop_info.get('age_s', 0),
            })

            status['actuators'] = {
                'motor_currents': motor_currents,
                'servo_position': actuator_controller.get_servo_position(),
            }
        except ImportError as e:
            logger.debug(f"Cannot import actuator_controller: {e}")
        except Exception as e:
            logger.warning(f"Failed to get actuator data: {e}")

        # Try importing sensor_reader for IMU/barometer
        try:
            from robot_pi import sensor_reader
            sensor_data = sensor_reader.get_all_data()
            status['sensors'] = sensor_data
        except ImportError as e:
            logger.debug(f"Cannot import sensor_reader: {e}")
        except Exception as e:
            logger.warning(f"Failed to get sensor data: {e}")

    except Exception as e:
        logger.warning(f"Direct inspection failed: {e}")


def _add_direct_base_data(status: Dict):
    """
    Add real-time data from direct component inspection (Base Pi).
    Could tap into telemetry receiver for real-time sensor data.
    """
    try:
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Base Pi could inspect telemetry_receiver for real-time data
        # For now, rely on logs which already have everything needed

    except Exception as e:
        logger.warning(f"Direct inspection failed: {e}")


def clear_cache():
    """Clear the status cache to force fresh collection"""
    global _status_cache, _cache_timestamp
    _status_cache = None
    _cache_timestamp = 0

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


def _transform_imu_data(imu_data: Dict) -> Dict:
    """
    Transform IMU data from flat format to nested format expected by dashboard.

    Input format:
        {'accel_x': ..., 'accel_y': ..., 'accel_z': ...,
         'gyro_x': ..., 'gyro_y': ..., 'gyro_z': ...,
         'quat_w': ..., 'quat_x': ..., 'quat_y': ..., 'quat_z': ...}

    Output format:
        {'accel': {'x': ..., 'y': ..., 'z': ...},
         'gyro': {'x': ..., 'y': ..., 'z': ...},
         'quaternion': {'w': ..., 'x': ..., 'y': ..., 'z': ...}}
    """
    return {
        'accel': {
            'x': imu_data.get('accel_x', 0.0),
            'y': imu_data.get('accel_y', 0.0),
            'z': imu_data.get('accel_z', 0.0)
        },
        'gyro': {
            'x': imu_data.get('gyro_x', 0.0),
            'y': imu_data.get('gyro_y', 0.0),
            'z': imu_data.get('gyro_z', 0.0)
        },
        'quaternion': {
            'w': imu_data.get('quat_w', 1.0),
            'x': imu_data.get('quat_x', 0.0),
            'y': imu_data.get('quat_y', 0.0),
            'z': imu_data.get('quat_z', 0.0)
        }
    }


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
        'data_flow': {},
        'sensors': {},
        'actuators': {},
        'video': {},
        'estop': {},
        'health': {}
    }

    # 1. Parse logs for connection and E-STOP status
    # Logs from the bridge service are the source of truth for connection
    # and E-STOP state - they reflect the actual bridge process state.
    log_status = log_parser.get_latest_status_event(config.ROBOT_BRIDGE_SERVICE)

    if log_status:
        control_connected = bool(log_status.get('control_connected'))
        control_established = log_status.get('control_established', False)
        control_age_ms = log_status.get('control_age_ms', 0)
        telemetry_connected = bool(log_status.get('telemetry_connected'))

        status['connections'] = {
            'control': {
                'state': 'connected' if control_connected else 'disconnected',
                'established': control_established,
                'age_ms': control_age_ms,
            },
            'telemetry': {
                'state': 'connected' if telemetry_connected else 'disconnected',
                'direction': 'tx',
            },
            'video': {
                'state': 'unknown',
                'direction': 'tx',
            },
        }

        status['data_flow'] = {
            'control_rx': {
                'connected': control_connected,
                'established': control_established,
                'age_ms': control_age_ms,
                'seq': log_status.get('control_seq', 0),
            },
            'telemetry_tx': {
                'connected': telemetry_connected,
            },
            'video_tx': {
                'connected': False,
                'frames_sent': 0,
                'frames_dropped': 0,
                'drop_rate': 0.0,
            },
        }

        # E-STOP from logs is authoritative - it reflects the actual bridge
        # process state. Direct inspection creates a separate ActuatorController
        # instance that does NOT share state with the bridge, so we must NOT
        # override this from direct inspection.
        status['estop'] = {
            'engaged': log_status.get('estop_engaged', False),
            'reason': log_status.get('estop_reason', 'unknown'),
        }

        status['health'] = {
            'uptime_s': log_status.get('uptime_s', 0),
            'psk_valid': log_status.get('psk_valid', False),
            'watchdog_disabled': config.DISABLE_WATCHDOG_FOR_LOCAL_TESTING,
        }

        # Extract sensor data from logs
        if 'imu' in log_status:
            status['sensors']['imu'] = _transform_imu_data(log_status['imu'])
        if 'barometer' in log_status:
            status['sensors']['barometer'] = log_status['barometer']
    else:
        # No recent logs - service may be down
        _unknown = {'state': 'unknown'}
        status['connections'] = {
            'control': {**_unknown, 'established': False, 'age_ms': 0},
            'telemetry': {**_unknown, 'direction': 'tx'},
            'video': {**_unknown, 'direction': 'tx'},
        }
        status['data_flow'] = {
            'control_rx': {'connected': False, 'established': False, 'age_ms': 0, 'seq': 0},
            'telemetry_tx': {'connected': False},
            'video_tx': {'connected': False, 'frames_sent': 0, 'frames_dropped': 0, 'drop_rate': 0.0},
        }
        status['estop'] = {'engaged': False, 'reason': 'unknown'}
        status['health'] = {
            'uptime_s': 0,
            'psk_valid': False,
            'watchdog_disabled': config.DISABLE_WATCHDOG_FOR_LOCAL_TESTING,
        }

    # 2. Direct inspection (optional) - for non-safety data only
    if config.ENABLE_DIRECT_INSPECTION:
        _add_direct_robot_data(status)

    return status


def _collect_base_status() -> Dict:
    """Collect status from Base Pi bridge"""
    status = {
        'connections': {},
        'data_flow': {},
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
            # Robot bridge log format: uses boolean fields for connections
            control_connected = bool(log_status.get('control_connected'))
            telemetry_connected = bool(log_status.get('telemetry_connected'))

            status['connections'] = {
                'control': {
                    'state': 'connected' if control_connected else 'disconnected',
                },
                'telemetry': {
                    'state': 'connected' if telemetry_connected else 'disconnected',
                    'direction': 'rx',
                },
                'video': {
                    'state': 'unknown',
                    'direction': 'rx',
                },
                'backend': {'state': 'unknown'},
            }
            status['data_flow'] = {
                'control_tx': {'connected': control_connected},
                'telemetry_rx': {'connected': telemetry_connected, 'rtt_ms': 0},
                'video_rx': {'connected': False},
            }
            status['estop'] = {
                'engaged': log_status.get('estop_engaged', False),
                'reason': log_status.get('estop_reason', 'unknown'),
            }
        else:
            # Base bridge log format: uses string fields for connections
            control_state = log_status.get('control', 'unknown')
            telemetry_state = log_status.get('telemetry', 'unknown')
            video_state = log_status.get('video', 'unknown')
            backend_state = log_status.get('backend', 'unknown')

            status['connections'] = {
                'control': {'state': control_state},
                'telemetry': {
                    'state': telemetry_state,
                    'direction': 'rx',
                },
                'video': {
                    'state': video_state,
                    'direction': 'rx',
                },
                'backend': {'state': backend_state},
            }
            status['data_flow'] = {
                'control_tx': {'connected': control_state == 'connected'},
                'telemetry_rx': {
                    'connected': telemetry_state == 'connected',
                    'rtt_ms': log_status.get('rtt_ms', 0),
                },
                'video_rx': {'connected': video_state == 'connected'},
            }
            # E-STOP reason now logged by base bridge watchdog as 'robot_estop_reason'
            estop_reason = log_status.get('robot_estop_reason')
            if not estop_reason:
                estop_reason = 'forwarded from robot' if log_status.get('robot_estop', False) else 'unknown'

            status['estop'] = {
                'engaged': log_status.get('robot_estop', False),
                'reason': estop_reason,
            }

        status['health'] = {
            'psk_valid': log_status.get('psk_valid', False),
            'uptime_s': log_status.get('uptime_s', 0) if using_robot_logs else 0,
            'watchdog_disabled': config.DISABLE_WATCHDOG_FOR_LOCAL_TESTING,
        }

        # Extract sensor data from logs (received via telemetry from Robot Pi)
        if 'imu' in log_status:
            status['sensors']['imu'] = _transform_imu_data(log_status['imu'])
        if 'barometer' in log_status:
            status['sensors']['barometer'] = log_status['barometer']
    else:
        _unknown = {'state': 'unknown'}
        status['connections'] = {
            'control': {**_unknown},
            'telemetry': {**_unknown, 'direction': 'rx'},
            'video': {**_unknown, 'direction': 'rx'},
            'backend': {**_unknown},
        }
        status['data_flow'] = {
            'control_tx': {'connected': False},
            'telemetry_rx': {'connected': False, 'rtt_ms': 0},
            'video_rx': {'connected': False},
        }
        status['estop'] = {'engaged': False, 'reason': 'unknown'}
        status['health'] = {
            'psk_valid': False,
            'watchdog_disabled': config.DISABLE_WATCHDOG_FOR_LOCAL_TESTING,
        }

    # Direct inspection (optional)
    if config.ENABLE_DIRECT_INSPECTION:
        _add_direct_base_data(status)

    return status


def _add_direct_robot_data(status: Dict):
    """
    Add real-time data from direct component inspection (Robot Pi).
    Gracefully falls back if imports fail.

    IMPORTANT: This function must NOT override E-STOP status from logs.
    The dashboard's ActuatorController instance is SEPARATE from the bridge's
    ActuatorController. It does not share state with the bridge process.
    Overriding E-STOP from direct inspection would show the dashboard's own
    E-STOP state instead of the bridge's actual E-STOP state, causing
    safety-critical inconsistencies between dashboards.

    Only non-safety data (video stats, motor currents, sensor data) should
    be added from direct inspection.
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
            frames_sent = video_stats.get('frames_sent', 0)
            frames_dropped = video_stats.get('frames_dropped', 0)
            drop_rate = video_stats.get('drop_rate', 0.0)
            video_active = frames_sent > 0

            status['video'] = {
                'frames_sent': frames_sent,
                'frames_dropped': frames_dropped,
                'drop_rate': drop_rate,
                'camera_errors': video_stats.get('camera_errors', 0),
                'active_camera': video_stats.get('active_camera_id', 0),
            }

            # Update connections and data_flow with video info
            status['connections']['video'] = {
                'state': 'connected' if video_active else 'disconnected',
                'direction': 'tx',
            }
            status['data_flow']['video_tx'] = {
                'connected': video_active,
                'frames_sent': frames_sent,
                'frames_dropped': frames_dropped,
                'drop_rate': drop_rate,
            }
        except ImportError as e:
            logger.debug(f"Cannot import video_capture: {e}")
        except Exception as e:
            logger.warning(f"Failed to get video stats: {e}")

        # Try importing actuator_controller for motor current data ONLY.
        # DO NOT read E-STOP from this - the dashboard's ActuatorController
        # is a separate instance from the bridge and does not share E-STOP state.
        try:
            from robot_pi import actuator_controller
            motor_currents = actuator_controller.get_motor_currents()

            status['actuators'] = {
                'motor_currents': motor_currents,
            }
        except ImportError as e:
            logger.debug(f"Cannot import actuator_controller: {e}")
        except Exception as e:
            logger.warning(f"Failed to get actuator data: {e}")

        # Note: Sensor data is extracted from logs in _collect_robot_status()
        # not here, to avoid conflicts with the bridge's sensor reader

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

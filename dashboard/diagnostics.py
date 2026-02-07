"""
Diagnostics

Network tests, camera detection, issue detection, and troubleshooting suggestions.
"""

import subprocess
import socket
import logging
from typing import List, Dict, Tuple
import os
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


def test_network_connectivity(target_ip: str, ports: List[int]) -> Dict:
    """
    Test network connectivity to a target IP and ports.

    Args:
        target_ip: Target IP address
        ports: List of ports to test

    Returns:
        Dictionary with:
        - ping: True if ping successful
        - rtt_ms: Round-trip time in milliseconds
        - ports: Dict of {port: reachable_bool}
    """
    result = {
        'ping': False,
        'rtt_ms': None,
        'ports': {}
    }

    # Test ping
    try:
        ping_result = subprocess.run(
            ['ping', '-c', '1', '-W', '2', target_ip],
            capture_output=True,
            text=True,
            timeout=3
        )

        if ping_result.returncode == 0:
            result['ping'] = True

            # Extract RTT from output
            for line in ping_result.stdout.split('\n'):
                if 'time=' in line:
                    try:
                        rtt_str = line.split('time=')[1].split()[0]
                        result['rtt_ms'] = float(rtt_str)
                    except:
                        pass

    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Ping to {target_ip} failed: {e}")

    # Test ports
    for port in ports:
        result['ports'][port] = _test_port(target_ip, port)

    return result


def _test_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    """Test if a port is reachable"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"Port test {ip}:{port} failed: {e}")
        return False


def scan_cameras() -> List[Dict]:
    """
    Scan for available camera devices and test their accessibility.

    Returns:
        List of camera info dictionaries:
        - device: Device path (/dev/video0, etc.)
        - exists: File exists
        - readable: Has read permissions
        - openable: Can be opened with cv2.VideoCapture
        - info: Additional device info if available
    """
    cameras = []

    # Scan /dev/video* devices
    video_devices = sorted(Path('/dev').glob('video*'))

    for device_path in video_devices:
        camera_info = {
            'device': str(device_path),
            'exists': device_path.exists(),
            'readable': os.access(device_path, os.R_OK),
            'openable': False,
            'info': {}
        }

        # Try to open with OpenCV
        if camera_info['readable']:
            try:
                import cv2
                cap = cv2.VideoCapture(str(device_path))
                camera_info['openable'] = cap.isOpened()

                if camera_info['openable']:
                    # Get camera properties
                    camera_info['info'] = {
                        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        'fps': int(cap.get(cv2.CAP_PROP_FPS)),
                    }

                cap.release()
            except Exception as e:
                logger.debug(f"Failed to test camera {device_path}: {e}")

        cameras.append(camera_info)

    return cameras


def check_service_status(service_name: str) -> Dict:
    """
    Check systemd service status.

    Args:
        service_name: Systemd service name

    Returns:
        Dictionary with:
        - active: Service is active
        - state: Service state string
        - enabled: Service is enabled
    """
    result = {
        'active': False,
        'state': 'unknown',
        'enabled': False
    }

    try:
        # Check if active
        active_result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=2
        )
        result['state'] = active_result.stdout.strip()
        result['active'] = active_result.returncode == 0

        # Check if enabled
        enabled_result = subprocess.run(
            ['systemctl', 'is-enabled', service_name],
            capture_output=True,
            text=True,
            timeout=2
        )
        result['enabled'] = enabled_result.returncode == 0

    except Exception as e:
        logger.warning(f"Failed to check service {service_name}: {e}")

    return result


def get_system_resources() -> Dict:
    """
    Get system resource usage.

    Returns:
        Dictionary with:
        - cpu_percent: CPU usage percentage
        - memory_percent: Memory usage percentage
        - disk_percent: Disk usage percentage
        - temperature_c: CPU temperature (if available)
    """
    result = {}

    try:
        import psutil

        result['cpu_percent'] = psutil.cpu_percent(interval=0.5)
        result['memory_percent'] = psutil.virtual_memory().percent
        result['disk_percent'] = psutil.disk_usage('/').percent

        # Try to get CPU temperature (Raspberry Pi specific)
        try:
            temp_result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if temp_result.returncode == 0:
                # Output format: temp=42.8'C
                temp_str = temp_result.stdout.strip()
                temp_c = float(temp_str.split('=')[1].split("'")[0])
                result['temperature_c'] = temp_c
        except:
            pass

    except ImportError:
        logger.warning("psutil not available for system resources")
    except Exception as e:
        logger.warning(f"Failed to get system resources: {e}")

    return result


def detect_issues(status_data: Dict) -> List[Dict]:
    """
    Detect issues from aggregated status data and provide suggestions.

    Args:
        status_data: Status dictionary from status_aggregator

    Returns:
        List of issue dictionaries:
        - severity: 'critical' | 'warning' | 'info'
        - title: Short issue description
        - description: Detailed description
        - suggestion: Actionable troubleshooting suggestion
    """
    issues = []

    connections = status_data.get('connections', {})
    data_flow = status_data.get('data_flow', {})
    estop = status_data.get('estop', {})
    video = status_data.get('video', {})
    health = status_data.get('health', {})

    # E-STOP engaged for too long
    if estop.get('engaged') and estop.get('age_s', 0) > config.ESTOP_WARN_AGE_S:
        issues.append({
            'severity': 'warning',
            'title': f"E-STOP engaged for {estop.get('age_s', 0):.0f}s",
            'description': f"E-STOP reason: {estop.get('reason', 'unknown')}",
            'suggestion': "Check if all connections are healthy. Try clearing E-STOP from diagnostics page."
        })

    # Control disconnected
    control_state = connections.get('control', {}).get('state', 'unknown')
    if control_state == 'disconnected':
        issues.append({
            'severity': 'critical',
            'title': "Control connection disconnected",
            'description': "Robot cannot receive commands",
            'suggestion': f"Check network connectivity. Verify Robot Pi port {config.CONTROL_PORT}. Check firewall rules."
        })

    # Control commands stale (robot_pi receives control, check data_flow)
    control_age = connections.get('control', {}).get('age_ms', 0)
    if control_state == 'connected' and control_age > config.CONTROL_AGE_STALE_MS:
        issues.append({
            'severity': 'warning',
            'title': f"Control commands stale ({control_age}ms old)",
            'description': "No recent commands received",
            'suggestion': "Check if backend is sending commands. Verify serpent_backend service is running."
        })

    # Video high drop rate (from data_flow on robot, or video dict from direct inspection)
    drop_rate = data_flow.get('video_tx', {}).get('drop_rate', 0.0) or video.get('drop_rate', 0.0)
    if drop_rate > config.VIDEO_DROP_RATE_WARN:
        frames_dropped = data_flow.get('video_tx', {}).get('frames_dropped', 0) or video.get('frames_dropped', 0)
        issues.append({
            'severity': 'warning',
            'title': f"High video frame drop rate ({drop_rate*100:.1f}%)",
            'description': f"Dropped {frames_dropped} frames",
            'suggestion': "Network may be congested. Check HaLow signal strength. Consider reducing resolution or FPS."
        })

    # Camera errors
    camera_errors = video.get('camera_errors', 0)
    if camera_errors > config.CAMERA_ERROR_THRESHOLD:
        issues.append({
            'severity': 'warning',
            'title': f"Camera errors detected ({camera_errors} errors)",
            'description': "Camera may be disconnected or failing",
            'suggestion': "Check camera physical connections. Try restarting video service. Verify /dev/video* permissions."
        })

    # Telemetry disconnected
    telemetry_state = connections.get('telemetry', {}).get('state', 'unknown')
    if telemetry_state == 'disconnected':
        issues.append({
            'severity': 'warning',
            'title': "Telemetry connection disconnected",
            'description': "Cannot receive sensor data",
            'suggestion': f"Check network connectivity. Verify Base Pi port {config.TELEMETRY_PORT}."
        })

    # Backend disconnected (Base Pi only)
    backend_state = connections.get('backend', {}).get('state', 'unknown')
    if status_data.get('role') == 'base_pi' and backend_state == 'disconnected':
        issues.append({
            'severity': 'critical',
            'title': "Backend connection disconnected",
            'description': "Cannot receive commands from backend",
            'suggestion': f"Check if {config.BACKEND_SERVICE} is running. Verify backend is listening on expected port."
        })

    # Invalid PSK
    if not health.get('psk_valid', True):
        issues.append({
            'severity': 'critical',
            'title': "Invalid PSK authentication",
            'description': "Pre-shared key validation failed",
            'suggestion': "Verify PSK matches on all components. Check environment variables or config files."
        })

    return issues


def restart_service(service_name: str) -> Tuple[bool, str]:
    """
    Restart a systemd service (requires ENABLE_SERVICE_CONTROL=True and sudo).

    Args:
        service_name: Systemd service name

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not config.ENABLE_SERVICE_CONTROL:
        return False, "Service control disabled in configuration"

    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', service_name],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return True, f"Service {service_name} restarted successfully"
        else:
            return False, f"Failed to restart: {result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Service restart timed out"
    except Exception as e:
        return False, f"Failed to restart service: {e}"

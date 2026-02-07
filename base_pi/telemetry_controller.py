"""
Telemetry Controller Module

Prepare condensed telemetry for TrimUI controller (rate-limited).
"""

import time
from typing import Dict, Any, List
from telemetry_metrics import quaternion_to_euler, check_thresholds


def format_for_controller(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format telemetry for controller display (comprehensive format).

    Args:
        telemetry: Full telemetry dictionary

    Returns:
        Controller-optimized telemetry with all relevant datapoints
    """
    # E-STOP status
    estop = telemetry.get('estop', {})
    estop_engaged = estop.get('engaged', False)
    estop_reason = estop.get('reason', '')

    # Determine overall status
    if estop_engaged:
        status = 'ESTOP'
    else:
        alerts = check_thresholds(telemetry)
        red_alerts = [a for a in alerts if a['severity'] == 'red']
        if red_alerts:
            status = 'WARN'
        else:
            status = 'OK'

    # Get Euler angles from quaternion
    orientation = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0}
    imu = telemetry.get('imu', {})
    if all(k in imu for k in ['quat_w', 'quat_x', 'quat_y', 'quat_z']):
        orientation = quaternion_to_euler(
            imu['quat_w'],
            imu['quat_x'],
            imu['quat_y'],
            imu['quat_z']
        )
        # Round to 1 decimal
        orientation = {k: round(v, 1) for k, v in orientation.items()}

    # Barometer data
    baro = telemetry.get('barometer', {})
    altitude = round(baro.get('altitude', 0.0), 1)
    pressure = round(baro.get('pressure', 0.0) / 100, 1)  # Pa to mBar
    temperature = round(baro.get('temperature', 0.0), 1)

    # Power data
    voltage = round(telemetry.get('voltage', 0.0), 1)

    # Network health
    rtt_ms = telemetry.get('rtt_ms', 0)
    control_age_ms = telemetry.get('control_age_ms', 0)

    # Motor currents
    motor_currents = telemetry.get('motor_currents', [])
    motors_active = [current > 0.5 for current in motor_currents]

    # Round motor currents to 1 decimal
    motor_currents_rounded = [round(c, 1) for c in motor_currents]

    # Calculate total motor current
    total_motor_current = round(sum(motor_currents), 1) if motor_currents else 0.0

    # Height and force (if available)
    height = telemetry.get('height')
    force = telemetry.get('force')
    if height is not None:
        height = round(height, 1)
    if force is not None:
        force = round(force, 1)

    # Get top 3 alerts
    alerts = check_thresholds(telemetry)
    alert_messages = [a['message'] for a in alerts[:3]]

    # Timestamp
    timestamp = telemetry.get('timestamp', 0.0)

    # Accelerometer magnitude (for vibration monitoring)
    accel_mag = 0.0
    if 'accel_x' in imu and 'accel_y' in imu and 'accel_z' in imu:
        accel_mag = (imu['accel_x']**2 + imu['accel_y']**2 + imu['accel_z']**2)**0.5
        accel_mag = round(accel_mag, 2)

    return {
        # System status
        'status': status,
        'timestamp': timestamp,

        # E-STOP
        'estop_engaged': estop_engaged,
        'estop_reason': estop_reason,

        # Orientation (Euler angles in degrees)
        'orientation': orientation,

        # Barometer
        'altitude': altitude,
        'pressure': pressure,  # mBar
        'temperature': temperature,  # °C

        # Power
        'voltage': voltage,

        # Network health
        'rtt_ms': rtt_ms,
        'control_age_ms': control_age_ms,

        # Motors
        'motor_currents': motor_currents_rounded,
        'motors_active': motors_active,
        'total_motor_current': total_motor_current,

        # Height/Force (if available)
        'height': height,
        'force': force,

        # Motion
        'accel_magnitude': accel_mag,

        # Alerts
        'alerts': alert_messages,
        'alert_count': len(alerts)
    }


def should_send_update(last_send_time: float, rate_hz: float) -> bool:
    """
    Check if enough time has passed to send another update.

    Args:
        last_send_time: Timestamp of last send
        rate_hz: Target rate in Hz

    Returns:
        True if update should be sent
    """
    now = time.time()
    interval = 1.0 / rate_hz
    return (now - last_send_time) >= interval

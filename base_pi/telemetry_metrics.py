"""
Telemetry Metrics Module

Compute derived metrics and health scores from telemetry data.
"""

import math
from typing import Dict, List, Any, Tuple


# Threshold definitions
THRESHOLDS = {
    'rtt_ms': {'green': 100, 'yellow': 500},
    'control_age_ms': {'green': 2000, 'yellow': 4000},
    'motor_current': {'green': 6.0, 'yellow': 8.0},
    'voltage': {'green': 11.5, 'yellow': 10.5},  # Below yellow is red
    'total_current': {'green': 20.0, 'yellow': 30.0},
    'cpu_usage': {'green': 70.0, 'yellow': 85.0},   # % above yellow is red
    'cpu_temp': {'green': 70.0, 'yellow': 80.0},    # °C above yellow is red
}


def quaternion_to_euler(qw: float, qx: float, qy: float, qz: float) -> Dict[str, float]:
    """
    Convert quaternion to Euler angles (roll, pitch, yaw) in degrees.

    Args:
        qw, qx, qy, qz: Quaternion components

    Returns:
        Dict with 'roll', 'pitch', 'yaw' in degrees
    """
    # Roll (x-axis rotation)
    sinr_cosp = 2 * (qw * qx + qy * qz)
    cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2 * (qw * qy - qz * qx)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)  # Use 90 degrees if out of range
    else:
        pitch = math.asin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2 * (qw * qz + qx * qy)
    cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    # Convert to degrees
    return {
        'roll': math.degrees(roll),
        'pitch': math.degrees(pitch),
        'yaw': math.degrees(yaw)
    }


def compute_health_score(telemetry: Dict[str, Any]) -> int:
    """
    Compute overall health score (0-100) based on telemetry metrics.

    Args:
        telemetry: Telemetry dictionary

    Returns:
        Health score from 0 (critical) to 100 (excellent)
    """
    score = 100

    # E-STOP engaged = critical
    estop = telemetry.get('estop', {})
    if estop.get('engaged', False):
        return 0

    # RTT penalty
    rtt_ms = telemetry.get('rtt_ms', 0)
    if rtt_ms > THRESHOLDS['rtt_ms']['yellow']:
        score -= 20
    elif rtt_ms > THRESHOLDS['rtt_ms']['green']:
        score -= 10

    # Control age penalty
    control_age_ms = telemetry.get('control_age_ms', 0)
    if control_age_ms > THRESHOLDS['control_age_ms']['yellow']:
        score -= 20
    elif control_age_ms > THRESHOLDS['control_age_ms']['green']:
        score -= 10

    # Voltage penalty
    voltage = telemetry.get('voltage', 12.0)
    if voltage < THRESHOLDS['voltage']['yellow']:
        score -= 30
    elif voltage < THRESHOLDS['voltage']['green']:
        score -= 15

    # Motor current penalty
    motor_currents = telemetry.get('motor_currents', [])
    if motor_currents:
        max_current = max(motor_currents)
        total_current = sum(motor_currents)

        if max_current > THRESHOLDS['motor_current']['yellow']:
            score -= 15
        elif max_current > THRESHOLDS['motor_current']['green']:
            score -= 5

        if total_current > THRESHOLDS['total_current']['yellow']:
            score -= 15
        elif total_current > THRESHOLDS['total_current']['green']:
            score -= 5

    # CPU usage and temperature penalties (Robot Pi and Base Pi)
    for cpu_key in ('robot_cpu', 'base_cpu'):
        cpu = telemetry.get(cpu_key, {})
        usage = cpu.get('usage_percent')
        temp = cpu.get('temp_c')
        if usage is not None:
            if usage > THRESHOLDS['cpu_usage']['yellow']:
                score -= 10
            elif usage > THRESHOLDS['cpu_usage']['green']:
                score -= 5
        if temp is not None:
            if temp > THRESHOLDS['cpu_temp']['yellow']:
                score -= 10
            elif temp > THRESHOLDS['cpu_temp']['green']:
                score -= 5

    return max(0, score)


def check_thresholds(telemetry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check telemetry values against thresholds and return warnings.

    Args:
        telemetry: Telemetry dictionary

    Returns:
        List of threshold violations with severity (green/yellow/red)
    """
    violations = []

    # RTT check
    rtt_ms = telemetry.get('rtt_ms', 0)
    if rtt_ms > THRESHOLDS['rtt_ms']['yellow']:
        violations.append({
            'metric': 'rtt_ms',
            'value': rtt_ms,
            'severity': 'red',
            'message': f'High RTT: {rtt_ms}ms'
        })
    elif rtt_ms > THRESHOLDS['rtt_ms']['green']:
        violations.append({
            'metric': 'rtt_ms',
            'value': rtt_ms,
            'severity': 'yellow',
            'message': f'Elevated RTT: {rtt_ms}ms'
        })

    # Control age check
    control_age_ms = telemetry.get('control_age_ms', 0)
    if control_age_ms > THRESHOLDS['control_age_ms']['yellow']:
        violations.append({
            'metric': 'control_age_ms',
            'value': control_age_ms,
            'severity': 'red',
            'message': f'Stale control: {control_age_ms}ms'
        })
    elif control_age_ms > THRESHOLDS['control_age_ms']['green']:
        violations.append({
            'metric': 'control_age_ms',
            'value': control_age_ms,
            'severity': 'yellow',
            'message': f'Old control: {control_age_ms}ms'
        })

    # Voltage check
    voltage = telemetry.get('voltage', 12.0)
    if voltage < THRESHOLDS['voltage']['yellow']:
        violations.append({
            'metric': 'voltage',
            'value': voltage,
            'severity': 'red',
            'message': f'Low battery: {voltage:.1f}V'
        })
    elif voltage < THRESHOLDS['voltage']['green']:
        violations.append({
            'metric': 'voltage',
            'value': voltage,
            'severity': 'yellow',
            'message': f'Battery warning: {voltage:.1f}V'
        })

    # Motor current checks
    motor_currents = telemetry.get('motor_currents', [])
    if motor_currents:
        for idx, current in enumerate(motor_currents):
            if current > THRESHOLDS['motor_current']['yellow']:
                violations.append({
                    'metric': f'motor_{idx}_current',
                    'value': current,
                    'severity': 'red',
                    'message': f'Motor {idx} overload: {current:.1f}A'
                })
            elif current > THRESHOLDS['motor_current']['green']:
                violations.append({
                    'metric': f'motor_{idx}_current',
                    'value': current,
                    'severity': 'yellow',
                    'message': f'Motor {idx} high current: {current:.1f}A'
                })

        # Total current check
        total_current = sum(motor_currents)
        if total_current > THRESHOLDS['total_current']['yellow']:
            violations.append({
                'metric': 'total_current',
                'value': total_current,
                'severity': 'red',
                'message': f'Total current critical: {total_current:.1f}A'
            })
        elif total_current > THRESHOLDS['total_current']['green']:
            violations.append({
                'metric': 'total_current',
                'value': total_current,
                'severity': 'yellow',
                'message': f'Total current elevated: {total_current:.1f}A'
            })

    # E-STOP check
    estop = telemetry.get('estop', {})
    if estop.get('engaged', False):
        violations.append({
            'metric': 'estop',
            'value': True,
            'severity': 'red',
            'message': f'E-STOP: {estop.get("reason", "unknown")}'
        })

    # CPU usage and temperature checks (Robot Pi and Base Pi)
    for cpu_key, label in (('robot_cpu', 'Robot'), ('base_cpu', 'Base')):
        cpu = telemetry.get(cpu_key, {})
        usage = cpu.get('usage_percent')
        temp = cpu.get('temp_c')
        if usage is not None:
            if usage > THRESHOLDS['cpu_usage']['yellow']:
                violations.append({
                    'metric': f'{cpu_key}_usage',
                    'value': usage,
                    'severity': 'red',
                    'message': f'{label} Pi CPU critical: {usage:.0f}%'
                })
            elif usage > THRESHOLDS['cpu_usage']['green']:
                violations.append({
                    'metric': f'{cpu_key}_usage',
                    'value': usage,
                    'severity': 'yellow',
                    'message': f'{label} Pi CPU high: {usage:.0f}%'
                })
        if temp is not None:
            if temp > THRESHOLDS['cpu_temp']['yellow']:
                violations.append({
                    'metric': f'{cpu_key}_temp',
                    'value': temp,
                    'severity': 'red',
                    'message': f'{label} Pi temp critical: {temp:.1f}°C'
                })
            elif temp > THRESHOLDS['cpu_temp']['green']:
                violations.append({
                    'metric': f'{cpu_key}_temp',
                    'value': temp,
                    'severity': 'yellow',
                    'message': f'{label} Pi temp high: {temp:.1f}°C'
                })

    return violations


def add_derived_metrics(telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add derived metrics to telemetry (Euler angles, health score, etc.).

    Args:
        telemetry: Original telemetry dictionary

    Returns:
        Enhanced telemetry with derived metrics
    """
    enhanced = telemetry.copy()

    # Add Euler angles from quaternion
    imu = telemetry.get('imu', {})
    if all(k in imu for k in ['quat_w', 'quat_x', 'quat_y', 'quat_z']):
        euler = quaternion_to_euler(
            imu['quat_w'],
            imu['quat_x'],
            imu['quat_y'],
            imu['quat_z']
        )
        enhanced['orientation'] = euler

    # Add health score
    enhanced['health_score'] = compute_health_score(telemetry)

    # Add threshold violations
    enhanced['alerts'] = check_thresholds(telemetry)

    # Add total motor current
    motor_currents = telemetry.get('motor_currents', [])
    if motor_currents:
        enhanced['total_motor_current'] = sum(motor_currents)

    return enhanced

#!/usr/bin/env python3
"""
Terminal Dashboard for SERPENT Base Pi
Real-time monitoring in the terminal
"""

import requests
import time
import sys
import subprocess
from datetime import datetime

def clear_screen():
    """Clear terminal screen"""
    print("\033[2J\033[H", end="")

def color_text(text, color):
    """Color terminal text"""
    colors = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m',
        'bold': '\033[1m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

def get_status():
    """Fetch status from dashboard API"""
    try:
        response = requests.get('http://localhost:5006/api/status', timeout=2)
        return response.json()
    except:
        return None

def get_service_status(service):
    """Get systemd service status"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service],
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except:
        return "unknown"

def connection_indicator(status):
    """Return colored connection status indicator"""
    if status == "connected":
        return color_text("● CONNECTED", 'green')
    elif status == "disconnected":
        return color_text("○ DISCONNECTED", 'red')
    else:
        return color_text("? UNKNOWN", 'yellow')

def draw_dashboard(status):
    """Draw the dashboard"""
    clear_screen()

    print(color_text("═" * 80, 'cyan'))
    print(color_text("║" + " " * 20 + "SERPENT BASE PI - TERMINAL DASHBOARD" + " " * 23 + "║", 'cyan'))
    print(color_text("═" * 80, 'cyan'))
    print()

    # Current time
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  {color_text('Time:', 'bold')} {now}")
    print()

    if status is None:
        print(color_text("  ⚠ Unable to fetch system status", 'red'))
        print(color_text("  Check if dashboard service is running: systemctl status serpent-web-dashboard", 'yellow'))
        return

    # Connection Status
    print(color_text("  CONNECTIONS:", 'bold'))
    print(f"    Control:    {connection_indicator(status['connections'].get('control', 'unknown'))}")
    print(f"    Telemetry:  {connection_indicator(status['connections'].get('telemetry', 'unknown'))}")
    print(f"    Video:      {connection_indicator(status['connections'].get('video', 'unknown'))}")
    print(f"    Backend:    {connection_indicator(status['connections'].get('backend', 'unknown'))}")
    print()

    # E-STOP Status
    estop_engaged = status.get('estop', {}).get('engaged')
    estop_reason = status.get('estop', {}).get('reason', 'unknown')

    print(color_text("  E-STOP STATUS:", 'bold'))
    if estop_engaged:
        print(f"    {color_text('⚠ ENGAGED', 'red')} - Reason: {estop_reason}")
    elif estop_engaged is False:
        print(f"    {color_text('✓ CLEAR', 'green')}")
    else:
        print(f"    {color_text('? UNKNOWN', 'yellow')}")
    print()

    # Health
    health = status.get('health', {})
    psk_valid = health.get('psk_valid', False)

    print(color_text("  SYSTEM HEALTH:", 'bold'))
    print(f"    PSK:        {color_text('✓ VALID', 'green') if psk_valid else color_text('✗ INVALID', 'red')}")
    print(f"    Uptime:     {health.get('uptime_s', 0):.0f}s")
    print()

    # Services
    print(color_text("  SERVICES:", 'bold'))
    base_status = get_service_status('serpent-base-bridge')
    dashboard_status = get_service_status('serpent-web-dashboard')

    base_color = 'green' if base_status == 'active' else 'red'
    dash_color = 'green' if dashboard_status == 'active' else 'red'

    print(f"    Base Bridge:    {color_text(base_status.upper(), base_color)}")
    print(f"    Dashboard:      {color_text(dashboard_status.upper(), dash_color)}")
    print()

    # Sensor Data (if available)
    sensors = status.get('sensors', {})
    if sensors:
        print(color_text("  SENSORS:", 'bold'))
        imu = sensors.get('imu', {})
        if imu:
            print(f"    IMU:        qw={imu.get('quat_w', 0):.3f}")
        baro = sensors.get('barometer', {})
        if baro:
            print(f"    Barometer:  {baro.get('pressure', 0):.1f} hPa, {baro.get('temperature', 0):.1f}°C")
        print()

    # Quick Stats
    print(color_text("═" * 80, 'cyan'))
    print(color_text(f"  Dashboard: http://192.168.1.10:5006  |  Press Ctrl+C to exit", 'cyan'))
    print(color_text("═" * 80, 'cyan'))

def main():
    """Main loop"""
    print(color_text("\n🚀 Starting SERPENT Terminal Dashboard...\n", 'bold'))
    time.sleep(1)

    try:
        while True:
            status = get_status()
            draw_dashboard(status)
            time.sleep(1)  # Update every second
    except KeyboardInterrupt:
        clear_screen()
        print(color_text("\n👋 Terminal Dashboard stopped.\n", 'bold'))
        sys.exit(0)
    except Exception as e:
        print(color_text(f"\n❌ Error: {e}\n", 'red'))
        sys.exit(1)

if __name__ == "__main__":
    main()

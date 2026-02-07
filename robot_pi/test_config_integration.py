#!/usr/bin/env python3
"""
Test sensor_reader.py with actual config.py configuration.

This verifies that the sensor reader properly uses the configuration
from robot_pi/config.py.
"""
import os
import sys
import time

# Set SIM_MODE to ensure we don't try to access real hardware
os.environ['SIM_MODE'] = 'true'

sys.path.insert(0, os.path.dirname(__file__))

import config
from sensor_reader import SensorReader

def test_config_integration():
    """Test sensor reader with configuration from config.py"""
    print("\n=== Testing with robot_pi/config.py ===")

    # Build current sensors config from config.py
    current_sensors_config = {
        'battery': {
            'addr': config.CURRENT_SENSOR_BATTERY_ADDR,
            'channel': config.CURRENT_SENSOR_BATTERY_CHANNEL,
            'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
            'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        },
        'system': {
            'addr': config.CURRENT_SENSOR_SYSTEM_ADDR,
            'channel': config.CURRENT_SENSOR_SYSTEM_CHANNEL,
            'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
            'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        },
        'servo': {
            'addr': config.CURRENT_SENSOR_SERVO_ADDR,
            'channel': config.CURRENT_SENSOR_SERVO_CHANNEL,
            'shunt_ohms': config.CURRENT_SENSOR_SHUNT_OHMS,
            'max_amps': config.CURRENT_SENSOR_MAX_EXPECTED_AMPS
        }
    }

    print(f"Configuration:")
    print(f"  I2C Bus: {config.I2C_BUS}")
    print(f"  BNO085 Address: 0x{config.BNO085_ADDRESS:02X}")
    print(f"  BMP388 Address: 0x{config.BMP388_ADDRESS:02X}")
    print(f"  Use Multiplexer: {config.USE_I2C_MULTIPLEXER}")
    print(f"  Multiplexer Address: 0x{config.I2C_MUX_ADDRESS:02X}")
    print(f"  IMU Channel: {config.IMU_MUX_CHANNEL}")
    print(f"  Barometer Channel: {config.BAROMETER_MUX_CHANNEL}")
    print(f"  Current Sensors:")
    for name, cfg in current_sensors_config.items():
        print(f"    {name}: addr=0x{cfg['addr']:02X}, channel={cfg['channel']}, "
              f"shunt={cfg['shunt_ohms']}Ω, max={cfg['max_amps']}A")

    # Initialize sensor reader with config
    reader = SensorReader(
        i2c_bus=config.I2C_BUS,
        bno085_addr=config.BNO085_ADDRESS,
        bmp388_addr=config.BMP388_ADDRESS,
        read_interval=config.SENSOR_READ_INTERVAL,
        use_multiplexer=config.USE_I2C_MULTIPLEXER,
        mux_addr=config.I2C_MUX_ADDRESS,
        imu_channel=config.IMU_MUX_CHANNEL,
        baro_channel=config.BAROMETER_MUX_CHANNEL,
        current_sensors=current_sensors_config
    )

    reader.start()
    time.sleep(0.5)

    # Get all data
    all_data = reader.get_all_data()

    print(f"\nData retrieved:")
    print(f"  IMU: {len(all_data.get('imu', {}))} fields")
    print(f"  Barometer: {len(all_data.get('barometer', {}))} fields")
    print(f"  Current sensors: {list(all_data.get('current', {}).keys())}")

    # Verify expected sensors
    assert all_data.get('imu'), "IMU data missing"
    assert all_data.get('barometer'), "Barometer data missing"

    current = all_data.get('current', {})
    if config.USE_I2C_MULTIPLEXER or current_sensors_config:
        # Current sensors should be present
        assert 'battery' in current, "Battery sensor missing"
        assert 'system' in current, "System sensor missing"
        assert 'servo' in current, "Servo sensor missing"

        # Display current sensor readings
        print(f"\nCurrent Sensor Readings:")
        for name, data in current.items():
            print(f"  {name.capitalize()}: {data['voltage']:.2f}V, "
                  f"{data['current']:.3f}A, {data['power']:.2f}W")

    reader.stop()
    print("\n✓ Config integration test passed")

if __name__ == '__main__':
    try:
        test_config_integration()
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

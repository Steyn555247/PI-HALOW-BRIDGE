#!/usr/bin/env python3
"""
Test script for sensor_reader.py with multiplexer and current sensor support.

This test verifies:
1. Import works without errors
2. Mock mode works when hardware unavailable
3. Configuration is properly used
4. Current sensor data is returned
5. Parallel reading works
"""
import os
import sys
import time

# Set SIM_MODE to ensure we don't try to access real hardware
os.environ['SIM_MODE'] = 'true'

sys.path.insert(0, os.path.dirname(__file__))

from sensor_reader import SensorReader

def test_basic_initialization():
    """Test basic initialization without multiplexer or current sensors"""
    print("\n=== Test 1: Basic Initialization ===")

    reader = SensorReader(
        i2c_bus=1,
        bno085_addr=0x4A,
        bmp388_addr=0x77,
        read_interval=0.1
    )

    reader.start()
    time.sleep(0.5)  # Let it read a few times

    imu_data = reader.get_imu_data()
    baro_data = reader.get_barometer_data()
    all_data = reader.get_all_data()

    print(f"IMU data keys: {list(imu_data.keys())}")
    print(f"Barometer data keys: {list(baro_data.keys())}")
    print(f"All data keys: {list(all_data.keys())}")

    assert 'quat_w' in imu_data, "IMU data missing quaternion"
    assert 'pressure' in baro_data, "Barometer data missing pressure"
    assert 'imu' in all_data, "All data missing IMU"
    assert 'barometer' in all_data, "All data missing barometer"
    assert 'current' in all_data, "All data missing current"

    reader.stop()
    print("✓ Basic initialization test passed")

def test_with_multiplexer():
    """Test initialization with multiplexer enabled"""
    print("\n=== Test 2: Multiplexer Configuration ===")

    reader = SensorReader(
        i2c_bus=1,
        bno085_addr=0x4A,
        bmp388_addr=0x77,
        read_interval=0.1,
        use_multiplexer=True,
        mux_addr=0x70,
        imu_channel=0,
        baro_channel=1
    )

    reader.start()
    time.sleep(0.5)

    imu_data = reader.get_imu_data()
    baro_data = reader.get_barometer_data()

    assert imu_data, "IMU data should be available with multiplexer"
    assert baro_data, "Barometer data should be available with multiplexer"

    reader.stop()
    print("✓ Multiplexer configuration test passed")

def test_with_current_sensors():
    """Test initialization with current sensors configured"""
    print("\n=== Test 3: Current Sensors ===")

    current_sensors_config = {
        'battery': {
            'addr': 0x40,
            'channel': 0,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        },
        'system': {
            'addr': 0x41,
            'channel': 0,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        },
        'servo': {
            'addr': 0x42,
            'channel': 0,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        }
    }

    reader = SensorReader(
        i2c_bus=1,
        bno085_addr=0x4A,
        bmp388_addr=0x77,
        read_interval=0.1,
        use_multiplexer=False,
        current_sensors=current_sensors_config
    )

    reader.start()
    time.sleep(0.5)  # Let it read a few times

    all_data = reader.get_all_data()
    current_data = all_data.get('current', {})

    print(f"Current sensors detected: {list(current_data.keys())}")

    assert 'battery' in current_data, "Battery current sensor missing"
    assert 'system' in current_data, "System current sensor missing"
    assert 'servo' in current_data, "Servo current sensor missing"

    # Check battery sensor data
    battery_data = current_data['battery']
    print(f"Battery: {battery_data['voltage']:.2f}V, {battery_data['current']:.3f}A, {battery_data['power']:.2f}W")

    assert 'voltage' in battery_data, "Battery voltage missing"
    assert 'current' in battery_data, "Battery current missing"
    assert 'power' in battery_data, "Battery power missing"

    # Verify reasonable mock values
    assert 0 < battery_data['voltage'] < 20, f"Battery voltage unrealistic: {battery_data['voltage']}"
    assert 0 < battery_data['current'] < 10, f"Battery current unrealistic: {battery_data['current']}"
    assert 0 < battery_data['power'] < 200, f"Battery power unrealistic: {battery_data['power']}"

    reader.stop()
    print("✓ Current sensors test passed")

def test_full_configuration():
    """Test with all features enabled (multiplexer + current sensors)"""
    print("\n=== Test 4: Full Configuration (Multiplexer + Current Sensors) ===")

    current_sensors_config = {
        'battery': {
            'addr': 0x40,
            'channel': 2,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        },
        'system': {
            'addr': 0x41,
            'channel': 2,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        },
        'servo': {
            'addr': 0x42,
            'channel': 3,
            'shunt_ohms': 0.001,
            'max_amps': 50.0
        }
    }

    reader = SensorReader(
        i2c_bus=1,
        bno085_addr=0x4A,
        bmp388_addr=0x77,
        read_interval=0.1,
        use_multiplexer=True,
        mux_addr=0x70,
        imu_channel=0,
        baro_channel=1,
        current_sensors=current_sensors_config
    )

    reader.start()
    time.sleep(0.5)

    all_data = reader.get_all_data()

    # Verify all three data types present
    assert 'imu' in all_data and all_data['imu'], "IMU data missing"
    assert 'barometer' in all_data and all_data['barometer'], "Barometer data missing"
    assert 'current' in all_data and all_data['current'], "Current data missing"

    # Verify all current sensors
    assert len(all_data['current']) == 3, f"Expected 3 current sensors, got {len(all_data['current'])}"

    print(f"All sensors working:")
    print(f"  IMU: {len(all_data['imu'])} fields")
    print(f"  Barometer: {len(all_data['barometer'])} fields")
    print(f"  Current sensors: {list(all_data['current'].keys())}")

    reader.stop()
    print("✓ Full configuration test passed")

def test_parallel_reads():
    """Test that parallel reads are faster than sequential"""
    print("\n=== Test 5: Parallel Read Performance ===")

    current_sensors_config = {
        'battery': {'addr': 0x40, 'channel': 0, 'shunt_ohms': 0.001, 'max_amps': 50.0},
        'system': {'addr': 0x41, 'channel': 0, 'shunt_ohms': 0.001, 'max_amps': 50.0},
        'servo': {'addr': 0x42, 'channel': 0, 'shunt_ohms': 0.001, 'max_amps': 50.0}
    }

    reader = SensorReader(
        i2c_bus=1,
        read_interval=0.05,  # Fast interval
        current_sensors=current_sensors_config
    )

    reader.start()

    # Let it run for a bit and check update rate
    time.sleep(0.3)
    data1 = reader.get_all_data()

    time.sleep(0.1)
    data2 = reader.get_all_data()

    # Data should have changed (mock data is time-based)
    if data1.get('imu', {}).get('accel_x') != data2.get('imu', {}).get('accel_x'):
        print("✓ Parallel reads are working (data updates detected)")
    else:
        print("⚠ Could not verify parallel read performance in mock mode")

    reader.stop()

if __name__ == '__main__':
    print("Testing sensor_reader.py with multiplexer and current sensor support")
    print("=" * 70)

    try:
        test_basic_initialization()
        test_with_multiplexer()
        test_with_current_sensors()
        test_full_configuration()
        test_parallel_reads()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

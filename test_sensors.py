#!/usr/bin/env python3
"""Test script to verify BNO055 and BMP581 sensors"""

import time
import sys
import os

# Add robot_pi to path
sys.path.insert(0, os.path.dirname(__file__))

from robot_pi.sensor_reader import SensorReader
from robot_pi import config

print("=" * 60)
print("Testing BNO055 IMU and BMP581 Barometer")
print("=" * 60)
print(f"Configuration:")
print(f"  - BNO055 at 0x{config.BNO055_ADDRESS:02X} on channel {config.IMU_MUX_CHANNEL}")
print(f"  - BMP581 at 0x{config.BMP581_ADDRESS:02X} on channel {config.BAROMETER_MUX_CHANNEL}")
print(f"  - Multiplexer at 0x{config.I2C_MUX_ADDRESS:02X} (enabled: {config.USE_I2C_MULTIPLEXER})")
print()

# Create sensor reader
sensor_reader = SensorReader(
    i2c_bus=config.I2C_BUS,
    bno055_addr=config.BNO055_ADDRESS,
    bmp581_addr=config.BMP581_ADDRESS,
    read_interval=0.1,
    use_multiplexer=config.USE_I2C_MULTIPLEXER,
    mux_addr=config.I2C_MUX_ADDRESS,
    imu_channel=config.IMU_MUX_CHANNEL,
    baro_channel=config.BAROMETER_MUX_CHANNEL
)

print("Starting sensor reader...")
sensor_reader.start()

# Give sensors time to initialize
time.sleep(2.0)

print("\nReading sensors for 10 seconds...\n")

try:
    for i in range(10):
        data = sensor_reader.get_all_data()

        imu = data.get('imu', {})
        baro = data.get('barometer', {})

        print(f"[{i+1:2d}] IMU:")
        print(f"      Quaternion: w={imu.get('quat_w', 0):.3f}, "
              f"x={imu.get('quat_x', 0):.3f}, "
              f"y={imu.get('quat_y', 0):.3f}, "
              f"z={imu.get('quat_z', 0):.3f}")
        print(f"      Accel: x={imu.get('accel_x', 0):.2f}, "
              f"y={imu.get('accel_y', 0):.2f}, "
              f"z={imu.get('accel_z', 0):.2f} m/s²")
        print(f"      Gyro:  x={imu.get('gyro_x', 0):.3f}, "
              f"y={imu.get('gyro_y', 0):.3f}, "
              f"z={imu.get('gyro_z', 0):.3f} rad/s")

        print(f"      Barometer:")
        print(f"      Pressure: {baro.get('pressure', 0):.2f} hPa")
        print(f"      Temperature: {baro.get('temperature', 0):.2f} °C")
        print(f"      Altitude: {baro.get('altitude', 0):.2f} m")
        print()

        time.sleep(1.0)

except KeyboardInterrupt:
    print("\nTest interrupted by user")

finally:
    print("\nStopping sensor reader...")
    sensor_reader.stop()
    print("Done!")

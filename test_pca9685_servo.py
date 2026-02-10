#!/usr/bin/env python3
"""
Test PCA9685 servo by sweeping through its range
"""
import time
from adafruit_servokit import ServoKit

# Initialize PCA9685 at address 0x40 with 16 channels
print("Initializing PCA9685...")
kit = ServoKit(channels=16, address=0x40)

# Configure servo on channel 0
print("Configuring servo on channel 0...")
kit.servo[0].actuation_range = 180
kit.servo[0].set_pulse_width_range(500, 2500)

print("\n=== PCA9685 Servo Test ===")
print("This will sweep the servo through its full range")
print("Watch the servo to verify it moves smoothly\n")

# Start at neutral (90°)
print("Moving to neutral position (90°)...")
kit.servo[0].angle = 90
time.sleep(1)

# Sweep from 0° to 180°
print("\nSweeping from 0° to 180°...")
for angle in range(0, 181, 10):
    print(f"  Position: {angle}°", end='\r')
    kit.servo[0].angle = angle
    time.sleep(0.1)
print("\n")

time.sleep(0.5)

# Sweep back from 180° to 0°
print("Sweeping from 180° back to 0°...")
for angle in range(180, -1, -10):
    print(f"  Position: {angle}°", end='\r')
    kit.servo[0].angle = angle
    time.sleep(0.1)
print("\n")

time.sleep(0.5)

# Return to neutral
print("Returning to neutral (90°)...")
kit.servo[0].angle = 90
time.sleep(0.5)

print("\n✓ Test complete!")
print("If the servo moved smoothly through its range, the PCA9685 is working correctly.")

#!/usr/bin/env python3
"""Test script to verify servo control"""

import time
import sys
import os

# Add robot_pi to path
sys.path.insert(0, os.path.dirname(__file__))

from robot_pi.actuator_controller import ActuatorController
from robot_pi import config

print("=" * 60)
print("Testing Servo Control")
print("=" * 60)
print(f"Configuration:")
if config.USE_PCA9685:
    print(f"  - Mode: PCA9685 I2C Servo Controller")
    print(f"  - I2C Address: 0x{config.PCA9685_ADDRESS:02X}")
    print(f"  - Servo Channel: {config.SERVO_CHANNEL}")
    print(f"  - Pulse Width: {config.SERVO_MIN_PULSE}-{config.SERVO_MAX_PULSE}us")
    print(f"  - Actuation Range: {config.SERVO_ACTUATION_RANGE}°")
else:
    print(f"  - Mode: GPIO PWM (Legacy)")
    print(f"  - GPIO Pin: {config.SERVO_GPIO_PIN}")
    print(f"  - Frequency: {config.SERVO_FREQ} Hz")
    print(f"  - Duty Cycle Range: {config.SERVO_MIN_DUTY}% - {config.SERVO_MAX_DUTY}%")
print()

# Create actuator controller
print("Creating ActuatorController...")
controller = ActuatorController(
    motoron_addresses=config.MOTORON_ADDRESSES,
    use_pca9685=config.USE_PCA9685,
    pca9685_address=config.PCA9685_ADDRESS,
    pca9685_channels=config.PCA9685_CHANNELS,
    servo_channel=config.SERVO_CHANNEL,
    servo_min_pulse=config.SERVO_MIN_PULSE,
    servo_max_pulse=config.SERVO_MAX_PULSE,
    servo_actuation_range=config.SERVO_ACTUATION_RANGE,
    servo_gpio=config.SERVO_GPIO_PIN,
    servo_freq=config.SERVO_FREQ,
    active_motors=config.ACTIVE_MOTORS,
    servo_min_duty=config.SERVO_MIN_DUTY,
    servo_max_duty=config.SERVO_MAX_DUTY
)

print("Starting ActuatorController (initializing hardware)...")
controller.start()

# Clear E-STOP to allow servo commands (local testing mode)
print("Clearing E-STOP...")
controller.clear_estop_local()

print("Servo initialized and ready!")
print()

try:
    print("Test 1: Sweep servo through full range (0.0 to 1.0)")
    print("-" * 60)

    # Sweep from min to max
    for i in range(11):
        position = i / 10.0
        print(f"Setting position: {position:.1f}", end="")
        success = controller.set_servo_position(position)
        if success:
            print(" ✓")
        else:
            print(" ✗ FAILED")
        time.sleep(0.5)

    print()
    print("Test 2: Move to specific positions")
    print("-" * 60)

    positions = [0.0, 0.25, 0.5, 0.75, 1.0, 0.5, 0.0]
    for pos in positions:
        print(f"Moving to position {pos:.2f}...", end="")
        success = controller.set_servo_position(pos)
        if success:
            print(" ✓")
        else:
            print(" ✗ FAILED")
        time.sleep(1.0)

    print()
    print("Test 3: Center position (0.5)")
    print("-" * 60)
    success = controller.set_servo_position(0.5)
    if success:
        print("Servo centered ✓")
    else:
        print("Failed to center servo ✗")

except KeyboardInterrupt:
    print("\n\nTest interrupted by user")

finally:
    print("\nCleaning up...")
    # Return to center position
    controller.set_servo_position(0.5)
    # Stop controller
    controller.stop()
    print("Done!")

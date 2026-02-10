#!/usr/bin/env python3
"""
Test PCA9685 access through TCA9548A multiplexer
"""
import busio
import board
import adafruit_tca9548a

print("=== Multiplexer PCA9685 Test ===\n")

# Initialize I2C
print("Initializing I2C bus...")
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize multiplexer
print(f"Initializing multiplexer at 0x70...")
try:
    mux = adafruit_tca9548a.TCA9548A(i2c, address=0x70)
    print("✓ Multiplexer found at 0x70\n")
except Exception as e:
    print(f"✗ Multiplexer initialization failed: {e}")
    exit(1)

# Scan all multiplexer channels
print("Scanning all multiplexer channels for devices:\n")
for channel in range(8):
    print(f"Channel {channel}:", end=" ")
    try:
        # Get the multiplexed I2C bus for this channel
        mux_channel = mux[channel]

        # Try to scan for devices on this channel
        while not mux_channel.try_lock():
            pass

        devices = mux_channel.scan()
        mux_channel.unlock()

        if devices:
            device_addrs = [f"0x{addr:02X}" for addr in devices]
            print(f"Found devices: {', '.join(device_addrs)}")
        else:
            print("No devices found")
    except Exception as e:
        print(f"Error: {e}")

# Test PCA9685 on channel 2
print("\n--- Testing PCA9685 on Channel 2 ---")
print("Attempting to initialize PCA9685 at 0x40 on multiplexer channel 2...")
try:
    from adafruit_servokit import ServoKit

    mux_channel_2 = mux[2]
    servo_kit = ServoKit(channels=16, address=0x40, i2c=mux_channel_2)

    print("✓ PCA9685 initialized successfully!")
    print("\nTesting servo movement...")

    # Test servo on channel 0
    servo_kit.servo[0].actuation_range = 180
    servo_kit.servo[0].set_pulse_width_range(500, 2500)

    print("  Moving to 90° (neutral)...")
    servo_kit.servo[0].angle = 90

    print("✓ Test complete! PCA9685 is working through multiplexer channel 2")

except Exception as e:
    print(f"✗ PCA9685 initialization failed: {e}")
    print("\nTroubleshooting:")
    print("1. Check that PCA9685 is connected to multiplexer channel 2 (SD2/SC2)")
    print("2. Verify PCA9685 has power (VCC, GND, and V+ for servos)")
    print("3. Check that address jumpers on PCA9685 are set for 0x40 (default)")

#!/usr/bin/env python3
"""
I2C Device Scanner with PCA9548 Multiplexer Support

Scans all channels of the PCA9548 multiplexer and discovers connected I2C devices.
Helps with initial setup, troubleshooting, and verification of sensor connections.

Usage:
    python3 scripts/scan_i2c_devices.py

Expected devices:
    Channel 0: 0x40 (PCA9685 Servo Controller)
    Channel 1: 0x28 (BNO055 IMU)
    Channel 0: 0x47 (BMP581 Barometer)
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import board
    import busio
    from robot_pi.i2c_multiplexer import I2CMultiplexer
except ImportError as e:
    print(f"Error: Required libraries not found: {e}")
    print("Please install dependencies: pip install adafruit-blinka")
    sys.exit(1)

# Known device types by address
KNOWN_DEVICES = {
    0x28: "BNO055 IMU",
    0x47: "BMP581 Barometer",
    0x40: "PCA9685 Servo Controller",
    0x70: "TCA9548A I2C Multiplexer",
    0x10: "Motoron Motor Controller #0",
    0x11: "Motoron Motor Controller #1",
    0x12: "Motoron Motor Controller #2",
    0x13: "Motoron Motor Controller #3"
}


def scan_direct_bus(i2c):
    """Scan I2C bus directly (without multiplexer)"""
    print("Scanning I2C bus directly (no multiplexer)...")
    print("-" * 60)

    devices_found = []
    while not i2c.try_lock():
        pass

    try:
        devices = i2c.scan()
        for addr in devices:
            device_name = KNOWN_DEVICES.get(addr, "Unknown Device")
            print(f"  0x{addr:02X} ({addr:3d}) - {device_name}")
            devices_found.append(addr)
    finally:
        i2c.unlock()

    if not devices_found:
        print("  No devices found")

    print()
    return devices_found


def scan_with_multiplexer(i2c, mux_addr=0x70):
    """Scan I2C bus through PCA9548 multiplexer"""
    try:
        mux = I2CMultiplexer(i2c, mux_addr)
        print(f"PCA9548 multiplexer found at 0x{mux_addr:02X}")
        print("Scanning all multiplexer channels...")
        print("-" * 60)

        total_devices = 0

        for channel in range(8):
            try:
                mux.select_channel(channel)

                # Small delay for channel switching
                import time
                time.sleep(0.01)

                while not i2c.try_lock():
                    pass

                try:
                    devices = i2c.scan()
                    # Filter out the multiplexer itself
                    devices = [d for d in devices if d != mux_addr]

                    if devices:
                        print(f"\nChannel {channel}:")
                        for addr in devices:
                            device_name = KNOWN_DEVICES.get(addr, "Unknown Device")
                            print(f"  0x{addr:02X} ({addr:3d}) - {device_name}")
                            total_devices += 1
                    else:
                        print(f"\nChannel {channel}: (empty)")

                finally:
                    i2c.unlock()

            except Exception as e:
                print(f"\nChannel {channel}: Error - {e}")

        mux.disable_all()

        print()
        print("-" * 60)
        print(f"Total devices found: {total_devices} (across all channels)")

        # Print expected configuration
        print()
        print("Expected configuration:")
        print("  Channel 0: 0x40 (PCA9685 Servo Controller), 0x47 (BMP581 Barometer)")
        print("  Channel 1: 0x28 (BNO055 IMU)")

    except Exception as e:
        print(f"Failed to initialize multiplexer at 0x{mux_addr:02X}: {e}")
        print("Scanning direct bus instead...")
        print()
        scan_direct_bus(i2c)


def main():
    print("=" * 60)
    print("I2C Device Scanner with PCA9548 Multiplexer Support")
    print("=" * 60)
    print()

    try:
        # Initialize I2C bus
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        print("I2C bus initialized (400 kHz)")
        print()

        # First, scan direct bus to find multiplexer
        direct_devices = scan_direct_bus(i2c)

        # If multiplexer found, scan through it
        if 0x70 in direct_devices:
            print()
            scan_with_multiplexer(i2c, 0x70)
        else:
            print("Note: PCA9548 multiplexer not found at 0x70")
            print("Only direct I2C devices are shown above.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("Scan complete!")


if __name__ == '__main__':
    main()

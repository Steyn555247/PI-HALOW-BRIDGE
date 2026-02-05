#!/usr/bin/env python3
"""
PCA9548 I2C Multiplexer Driver

Manages channel selection for the PCA9548 8-channel I2C multiplexer.
Thread-safe implementation for use with multiple sensors on shared I2C bus.
"""

import threading
import logging

logger = logging.getLogger(__name__)


class I2CMultiplexer:
    """
    Driver for PCA9548 I2C multiplexer.

    The PCA9548 has 8 channels (0-7). Only one channel can be active at a time.
    Channel selection is done by writing a control byte where bit N corresponds to channel N.
    """

    def __init__(self, i2c_bus, address=0x70):
        """
        Initialize the multiplexer.

        Args:
            i2c_bus: The I2C bus object (busio.I2C)
            address: I2C address of the PCA9548 (default 0x70)
        """
        self.i2c_bus = i2c_bus
        self.address = address
        self.lock = threading.Lock()
        self.current_channel = None

        logger.info(f"Initializing PCA9548 multiplexer at address 0x{address:02X}")

        # Verify multiplexer is present
        try:
            self.disable_all()
            logger.info("PCA9548 multiplexer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PCA9548 multiplexer: {e}")
            raise

    def select_channel(self, channel):
        """
        Select a specific multiplexer channel (0-7).

        Args:
            channel: Channel number (0-7)

        Raises:
            ValueError: If channel number is invalid
            RuntimeError: If I2C communication fails
        """
        if not 0 <= channel <= 7:
            raise ValueError(f"Invalid channel {channel}. Must be 0-7.")

        with self.lock:
            # Only switch if needed (optimization)
            if self.current_channel == channel:
                return

            control_byte = 1 << channel  # Set bit N to select channel N

            try:
                while not self.i2c_bus.try_lock():
                    pass
                try:
                    self.i2c_bus.writeto(self.address, bytes([control_byte]))
                    self.current_channel = channel
                    logger.debug(f"Selected multiplexer channel {channel}")
                finally:
                    self.i2c_bus.unlock()
            except Exception as e:
                logger.error(f"Failed to select channel {channel}: {e}")
                raise RuntimeError(f"Multiplexer channel selection failed: {e}")

    def disable_all(self):
        """
        Disable all multiplexer channels.

        This is useful for initialization and cleanup.

        Raises:
            RuntimeError: If I2C communication fails
        """
        with self.lock:
            try:
                while not self.i2c_bus.try_lock():
                    pass
                try:
                    self.i2c_bus.writeto(self.address, bytes([0x00]))
                    self.current_channel = None
                    logger.debug("Disabled all multiplexer channels")
                finally:
                    self.i2c_bus.unlock()
            except Exception as e:
                logger.error(f"Failed to disable multiplexer channels: {e}")
                raise RuntimeError(f"Multiplexer disable failed: {e}")

    def get_current_channel(self):
        """
        Get the currently selected channel.

        Returns:
            int or None: Current channel number (0-7) or None if all disabled
        """
        with self.lock:
            return self.current_channel


if __name__ == '__main__':
    # Basic test
    import board
    import busio

    logging.basicConfig(level=logging.DEBUG)

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        mux = I2CMultiplexer(i2c, 0x70)

        print("Testing multiplexer channel selection...")
        for channel in range(8):
            mux.select_channel(channel)
            print(f"Selected channel {channel}")

        mux.disable_all()
        print("Test complete")

    except Exception as e:
        print(f"Test failed: {e}")

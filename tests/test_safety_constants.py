"""
Tests for safety constants.

Ensures safety-critical constants have correct values and cannot be
accidentally changed.
"""

import unittest
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.constants import (
    WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S, ESTOP_CLEAR_MAX_AGE_S,
    ESTOP_CLEAR_CONFIRM, MAX_FRAME_SIZE, MAX_CONTROL_BUFFER, MAX_VIDEO_BUFFER
)


class TestSafetyConstants(unittest.TestCase):
    """Test safety-critical constants have expected values"""

    def test_watchdog_timeout(self):
        """Watchdog timeout must be 5 seconds"""
        self.assertEqual(WATCHDOG_TIMEOUT_S, 5.0)

    def test_startup_grace(self):
        """Startup grace must be 30 seconds"""
        self.assertEqual(STARTUP_GRACE_S, 30.0)

    def test_estop_clear_max_age(self):
        """E-STOP clear max age must be 1.5 seconds"""
        self.assertEqual(ESTOP_CLEAR_MAX_AGE_S, 1.5)

    def test_estop_clear_confirm(self):
        """E-STOP clear confirm string must be exact"""
        self.assertEqual(ESTOP_CLEAR_CONFIRM, "CLEAR_ESTOP")

    def test_watchdog_less_than_grace(self):
        """Watchdog timeout must be less than startup grace"""
        self.assertLess(WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S)

    def test_clear_age_less_than_watchdog(self):
        """Clear max age must be less than watchdog timeout"""
        self.assertLess(ESTOP_CLEAR_MAX_AGE_S, WATCHDOG_TIMEOUT_S)


class TestBufferLimits(unittest.TestCase):
    """Test buffer limits are reasonable"""

    def test_max_frame_size(self):
        """Max frame size should be reasonable"""
        self.assertGreater(MAX_FRAME_SIZE, 1000)  # At least 1KB
        self.assertLessEqual(MAX_FRAME_SIZE, 65536)  # At most 64KB

    def test_max_control_buffer(self):
        """Max control buffer should be reasonable"""
        self.assertGreater(MAX_CONTROL_BUFFER, MAX_FRAME_SIZE)

    def test_max_video_buffer(self):
        """Max video buffer should be larger than control"""
        self.assertGreater(MAX_VIDEO_BUFFER, MAX_CONTROL_BUFFER)


class TestConfigImmutability(unittest.TestCase):
    """Test that config imports safety constants correctly"""

    def test_robot_config_uses_constants(self):
        """Robot config should import safety constants"""
        # Force SIM_MODE
        os.environ['SIM_MODE'] = 'true'

        from robot_pi import config

        self.assertEqual(config.WATCHDOG_TIMEOUT, WATCHDOG_TIMEOUT_S)
        self.assertEqual(config.STARTUP_GRACE, STARTUP_GRACE_S)
        self.assertEqual(config.RECONNECT_DELAY, 2.0)  # From constants

    def test_base_config_uses_constants(self):
        """Base config should import safety constants"""
        from base_pi import config

        self.assertEqual(config.WATCHDOG_TIMEOUT, WATCHDOG_TIMEOUT_S)
        self.assertEqual(config.RECONNECT_DELAY, 2.0)  # From constants


if __name__ == '__main__':
    unittest.main()

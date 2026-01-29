"""
Tests for E-STOP safety invariants.

Tests that E-STOP behaves correctly:
- Boot latched
- Cannot clear without proper validation
- Watchdog triggers correctly
- Thread safety
"""

import unittest
import os
import sys
import time
import threading

# Force SIM_MODE for tests
os.environ['SIM_MODE'] = 'true'

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.constants import (
    ESTOP_CLEAR_CONFIRM, ESTOP_CLEAR_MAX_AGE_S,
    ESTOP_REASON_BOOT, ESTOP_REASON_COMMAND, ESTOP_REASON_WATCHDOG
)


class TestEstopBootLatched(unittest.TestCase):
    """Test E-STOP is latched on boot"""

    def test_estop_engaged_on_construction(self):
        """E-STOP must be engaged immediately on construction"""
        # Import after setting SIM_MODE
        from robot_pi.actuator_controller import ActuatorController

        controller = ActuatorController(
            motoron_addresses=[0x10, 0x11],
            servo_gpio=12,
            active_motors=4
        )

        # E-STOP must be engaged before start() is called
        self.assertTrue(controller.is_estop_engaged())

        info = controller.get_estop_info()
        self.assertTrue(info['engaged'])
        self.assertEqual(info['reason'], ESTOP_REASON_BOOT)

    def test_estop_engaged_after_start(self):
        """E-STOP remains engaged after start()"""
        from robot_pi.actuator_controller import ActuatorController

        controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        controller.start()

        # E-STOP must still be engaged
        self.assertTrue(controller.is_estop_engaged())

        controller.stop()


class TestEstopClearValidation(unittest.TestCase):
    """Test E-STOP clear requires proper validation"""

    def setUp(self):
        from robot_pi.actuator_controller import ActuatorController

        self.controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        self.controller.start()

    def tearDown(self):
        self.controller.stop()

    def test_clear_requires_confirm_string(self):
        """Clear must have exact confirm string"""
        # Wrong confirm string
        result = self.controller.clear_estop(
            confirm="wrong",
            control_age_s=0.1,
            control_connected=True
        )
        self.assertFalse(result)
        self.assertTrue(self.controller.is_estop_engaged())

        # Empty confirm string
        result = self.controller.clear_estop(
            confirm="",
            control_age_s=0.1,
            control_connected=True
        )
        self.assertFalse(result)
        self.assertTrue(self.controller.is_estop_engaged())

    def test_clear_requires_connected(self):
        """Clear requires control to be connected"""
        result = self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=False  # Not connected
        )
        self.assertFalse(result)
        self.assertTrue(self.controller.is_estop_engaged())

    def test_clear_requires_fresh_control(self):
        """Clear requires fresh control (not stale)"""
        # Control too old
        result = self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=ESTOP_CLEAR_MAX_AGE_S + 1.0,  # Too stale
            control_connected=True
        )
        self.assertFalse(result)
        self.assertTrue(self.controller.is_estop_engaged())

    def test_clear_succeeds_with_valid_params(self):
        """Clear succeeds with all valid parameters"""
        result = self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,  # Fresh
            control_connected=True
        )
        self.assertTrue(result)
        self.assertFalse(self.controller.is_estop_engaged())

    def test_clear_idempotent(self):
        """Clearing already-cleared E-STOP returns True"""
        # First clear
        self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=True
        )

        # Second clear (already cleared)
        result = self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=True
        )
        self.assertTrue(result)
        self.assertFalse(self.controller.is_estop_engaged())


class TestEstopEngage(unittest.TestCase):
    """Test E-STOP engage behavior"""

    def setUp(self):
        from robot_pi.actuator_controller import ActuatorController

        self.controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        self.controller.start()

        # Clear E-STOP for tests
        self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=True
        )

    def tearDown(self):
        self.controller.stop()

    def test_engage_always_succeeds(self):
        """Engage E-STOP always succeeds"""
        self.assertFalse(self.controller.is_estop_engaged())

        self.controller.engage_estop(ESTOP_REASON_COMMAND, "test")

        self.assertTrue(self.controller.is_estop_engaged())
        info = self.controller.get_estop_info()
        self.assertEqual(info['reason'], ESTOP_REASON_COMMAND)

    def test_engage_idempotent(self):
        """Multiple engage calls are safe"""
        self.controller.engage_estop(ESTOP_REASON_COMMAND, "first")
        self.controller.engage_estop(ESTOP_REASON_WATCHDOG, "second")

        self.assertTrue(self.controller.is_estop_engaged())
        # Reason should be the latest
        info = self.controller.get_estop_info()
        self.assertEqual(info['reason'], ESTOP_REASON_WATCHDOG)


class TestEstopActuationBlocking(unittest.TestCase):
    """Test E-STOP blocks actuation"""

    def setUp(self):
        from robot_pi.actuator_controller import ActuatorController

        self.controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        self.controller.start()

    def tearDown(self):
        self.controller.stop()

    def test_motor_blocked_when_estop_engaged(self):
        """Motor commands blocked when E-STOP engaged"""
        self.assertTrue(self.controller.is_estop_engaged())

        result = self.controller.set_motor_speed(0, 500)
        self.assertFalse(result)

    def test_servo_blocked_when_estop_engaged(self):
        """Servo commands blocked when E-STOP engaged"""
        self.assertTrue(self.controller.is_estop_engaged())

        result = self.controller.set_servo_position(0.5)
        self.assertFalse(result)

    def test_motor_allowed_when_estop_cleared(self):
        """Motor commands allowed when E-STOP cleared"""
        self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=True
        )
        self.assertFalse(self.controller.is_estop_engaged())

        result = self.controller.set_motor_speed(0, 500)
        self.assertTrue(result)

    def test_servo_allowed_when_estop_cleared(self):
        """Servo commands allowed when E-STOP cleared"""
        self.controller.clear_estop(
            confirm=ESTOP_CLEAR_CONFIRM,
            control_age_s=0.1,
            control_connected=True
        )
        self.assertFalse(self.controller.is_estop_engaged())

        result = self.controller.set_servo_position(0.5)
        self.assertTrue(result)


class TestEstopThreadSafety(unittest.TestCase):
    """Test E-STOP thread safety"""

    def test_concurrent_engage_clear(self):
        """Test concurrent engage/clear operations"""
        from robot_pi.actuator_controller import ActuatorController

        controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        controller.start()

        errors = []
        engage_count = [0]
        clear_count = [0]

        def engage_loop():
            try:
                for _ in range(100):
                    controller.engage_estop(ESTOP_REASON_COMMAND, "test")
                    engage_count[0] += 1
            except Exception as e:
                errors.append(e)

        def clear_loop():
            try:
                for _ in range(100):
                    controller.clear_estop(
                        confirm=ESTOP_CLEAR_CONFIRM,
                        control_age_s=0.1,
                        control_connected=True
                    )
                    clear_count[0] += 1
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=engage_loop),
            threading.Thread(target=engage_loop),
            threading.Thread(target=clear_loop),
            threading.Thread(target=clear_loop),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        controller.stop()

        # No errors should occur
        self.assertEqual(len(errors), 0)
        # All operations should complete
        self.assertEqual(engage_count[0], 200)
        self.assertEqual(clear_count[0], 200)


class TestLegacyAPI(unittest.TestCase):
    """Test legacy API compatibility"""

    def test_legacy_clear_disabled(self):
        """Legacy clear_emergency_stop() is disabled"""
        from robot_pi.actuator_controller import ActuatorController

        controller = ActuatorController(
            motoron_addresses=[0x10],
            servo_gpio=12,
            active_motors=2
        )
        controller.start()

        # Legacy clear should fail
        result = controller.clear_emergency_stop()
        self.assertFalse(result)
        self.assertTrue(controller.is_estop_engaged())

        controller.stop()


if __name__ == '__main__':
    unittest.main()

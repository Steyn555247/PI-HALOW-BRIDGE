"""
Tests for chainsaw on/off press-release behavior.
"""

import os
import sys
import unittest

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robot_pi.core.command_executor import CommandExecutor


class _FakeActuatorController:
    """Minimal actuator stub for CommandExecutor unit tests."""

    def __init__(self):
        self.estop_engaged = False
        self.motor_commands = []

    def set_motor_speed(self, motor_id: int, speed: int) -> bool:
        self.motor_commands.append((motor_id, speed))
        return True

    def is_estop_engaged(self) -> bool:
        return self.estop_engaged


class TestChainsawOnOffTimeout(unittest.TestCase):
    """Chainsaw on/off should follow press/release, not idle timeout."""

    def setUp(self):
        self.actuator = _FakeActuatorController()
        self.executor = CommandExecutor(
            actuator_controller=self.actuator,
            framer=object(),
        )

    def tearDown(self):
        self.executor.stop_chainsaw_timeout_monitor()

    def test_idle_stop_preserves_active_chainsaw(self):
        self.executor._handle_chainsaw_command({'chainsaw_id': 1, 'action': 'press'})

        self.assertTrue(self.executor._chainsaw1_onoff_active)
        self.assertEqual(self.executor._cs1_ramp._target, self.executor._chainsaw_onoff_speed)

        self.executor._stop_all_motors()

        self.assertEqual(self.executor._cs1_ramp._target, self.executor._chainsaw_onoff_speed)

    def test_force_stop_stops_active_chainsaw(self):
        self.executor._handle_chainsaw_command({'chainsaw_id': 1, 'action': 'press'})

        self.executor._stop_all_motors(force_stop_chainsaws=True)

        self.assertEqual(self.executor._cs1_ramp._target, 0)

    def test_release_clears_active_state(self):
        self.executor._handle_chainsaw_command({'chainsaw_id': 2, 'action': 'press'})
        self.executor._handle_chainsaw_command({'chainsaw_id': 2, 'action': 'release'})

        self.assertFalse(self.executor._chainsaw2_onoff_active)
        self.assertEqual(self.executor._cs2_ramp._target, 0)


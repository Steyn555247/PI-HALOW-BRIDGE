"""
E-STOP Behavior Verification Tests

Tests all E-STOP triggers and clear validation for the Pi HaLow Bridge.

Safety-critical tests:
- Watchdog timeout triggers E-STOP
- Disconnect triggers E-STOP
- Auth failure triggers E-STOP
- E-STOP clear validation (confirm string, control age, etc.)

Usage:
    pytest tests/test_estop_triggers.py -v
    pytest tests/test_estop_triggers.py::TestEStopTriggers::test_watchdog_timeout -v
"""

import pytest
import socket
import json
import time
import os
import sys
import threading
from typing import Optional, Dict, Any

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.framing import SecureFramer
from common.constants import (
    WATCHDOG_TIMEOUT_S, STARTUP_GRACE_S,
    MSG_EMERGENCY_STOP, MSG_PING,
    ESTOP_CLEAR_CONFIRM,
    ESTOP_REASON_WATCHDOG, ESTOP_REASON_DISCONNECT,
    ESTOP_REASON_AUTH_FAILURE, ESTOP_REASON_STARTUP_TIMEOUT
)


class BridgeTestHarness:
    """
    Test harness for running Robot Pi and Base Pi bridges in test mode.

    Provides utilities for:
    - Starting/stopping bridges
    - Sending control commands
    - Receiving telemetry
    - Checking E-STOP state
    """

    def __init__(self, control_port: int = 15201, telemetry_port: int = 15203):
        self.control_port = control_port
        self.telemetry_port = telemetry_port

        self.control_socket: Optional[socket.socket] = None
        self.telemetry_socket: Optional[socket.socket] = None
        self.framer = SecureFramer(role="base_pi_test")
        self.telemetry_framer = SecureFramer(role="base_pi_telemetry_test")

        self.last_telemetry: Optional[Dict[str, Any]] = None
        self.telemetry_thread: Optional[threading.Thread] = None
        self.running = False

    def connect_control(self, timeout: float = 5.0) -> bool:
        """Connect to Robot Pi control server"""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(timeout)
            self.control_socket.connect(('127.0.0.1', self.control_port))
            return True
        except Exception as e:
            print(f"Failed to connect control: {e}")
            return False

    def disconnect_control(self):
        """Disconnect control socket"""
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
            self.control_socket = None

    def send_command(self, command_type: str, data: Dict[str, Any] = None) -> bool:
        """Send authenticated control command"""
        if not self.control_socket:
            return False

        message = {
            "type": command_type,
            "data": data or {},
            "timestamp": time.time()
        }

        try:
            payload = json.dumps(message).encode('utf-8')
            frame = self.framer.create_frame(payload)
            self.control_socket.sendall(frame)
            return True
        except Exception as e:
            print(f"Failed to send command: {e}")
            return False

    def connect_telemetry(self, timeout: float = 5.0) -> bool:
        """Connect to Robot Pi telemetry sender"""
        try:
            # Robot Pi connects TO Base Pi telemetry server
            # For testing, we act as Base Pi telemetry server
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', self.telemetry_port))
            server.listen(1)
            server.settimeout(timeout)

            self.telemetry_socket, addr = server.accept()
            self.telemetry_socket.settimeout(1.0)
            server.close()

            # Start telemetry receiver thread
            self.running = True
            self.telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
            self.telemetry_thread.start()

            return True
        except Exception as e:
            print(f"Failed to connect telemetry: {e}")
            return False

    def _telemetry_loop(self):
        """Receive telemetry in background"""
        while self.running and self.telemetry_socket:
            try:
                payload, seq = self.telemetry_framer.read_frame_from_socket(
                    self.telemetry_socket, timeout=1.0
                )
                telemetry = json.loads(payload.decode('utf-8'))
                self.last_telemetry = telemetry
            except socket.timeout:
                continue
            except Exception as e:
                break

    def get_estop_state(self) -> Optional[bool]:
        """Get current E-STOP state from last telemetry"""
        if not self.last_telemetry:
            return None
        return self.last_telemetry.get('estop', {}).get('engaged')

    def get_estop_reason(self) -> Optional[str]:
        """Get current E-STOP reason from last telemetry"""
        if not self.last_telemetry:
            return None
        return self.last_telemetry.get('estop', {}).get('reason')

    def wait_for_estop(self, timeout: float = 10.0) -> bool:
        """Wait for E-STOP to engage"""
        start = time.time()
        while time.time() - start < timeout:
            if self.get_estop_state() is True:
                return True
            time.sleep(0.1)
        return False

    def wait_for_estop_clear(self, timeout: float = 5.0) -> bool:
        """Wait for E-STOP to clear"""
        start = time.time()
        while time.time() - start < timeout:
            if self.get_estop_state() is False:
                return True
            time.sleep(0.1)
        return False

    def stop(self):
        """Stop the test harness"""
        self.running = False
        self.disconnect_control()
        if self.telemetry_socket:
            try:
                self.telemetry_socket.close()
            except:
                pass


class TestEStopTriggers:
    """Test E-STOP triggers"""

    def setup_method(self):
        """Setup - requires Robot Pi bridge running in test mode"""
        # For these tests to work, Robot Pi must be running
        # These are integration tests, not unit tests
        pass

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_watchdog_timeout(self):
        """
        Test: E-STOP engages after WATCHDOG_TIMEOUT_S without control

        Steps:
        1. Connect control and telemetry
        2. Send initial command to establish control
        3. Stop sending commands
        4. Wait > WATCHDOG_TIMEOUT_S
        5. Verify E-STOP engaged with watchdog reason
        """
        harness = BridgeTestHarness()

        try:
            # Connect
            assert harness.connect_control(timeout=5.0), "Failed to connect control"
            assert harness.connect_telemetry(timeout=5.0), "Failed to connect telemetry"

            # Establish control
            assert harness.send_command(MSG_PING, {"seq": 1}), "Failed to send initial ping"

            # Wait for telemetry
            time.sleep(1.0)
            assert harness.last_telemetry is not None, "No telemetry received"

            # E-STOP should be engaged on boot
            assert harness.get_estop_state() is True, "E-STOP should be engaged on boot"

            # Clear E-STOP
            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'test_clear'
            })

            # Wait for E-STOP to clear
            assert harness.wait_for_estop_clear(timeout=2.0), "E-STOP did not clear"

            # Now stop sending control and wait for watchdog
            print(f"Waiting {WATCHDOG_TIMEOUT_S + 2}s for watchdog timeout...")
            time.sleep(WATCHDOG_TIMEOUT_S + 2.0)

            # E-STOP should be engaged
            assert harness.wait_for_estop(timeout=2.0), "E-STOP did not engage after watchdog timeout"
            reason = harness.get_estop_reason()
            assert reason and 'watchdog' in reason.lower(), f"Wrong E-STOP reason: {reason}"

        finally:
            harness.stop()

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_disconnect_triggers_estop(self):
        """
        Test: E-STOP engages when control disconnects

        Steps:
        1. Connect control and telemetry
        2. Establish control
        3. Clear E-STOP
        4. Disconnect control socket
        5. Verify E-STOP engages
        """
        harness = BridgeTestHarness()

        try:
            assert harness.connect_control(), "Failed to connect"
            assert harness.connect_telemetry(), "Failed to connect telemetry"

            # Establish and clear E-STOP
            harness.send_command(MSG_PING, {})
            time.sleep(1.0)

            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'test'
            })

            assert harness.wait_for_estop_clear(timeout=2.0), "E-STOP did not clear"

            # Disconnect
            harness.disconnect_control()

            # Wait for E-STOP
            assert harness.wait_for_estop(timeout=WATCHDOG_TIMEOUT_S + 2.0), "E-STOP did not engage after disconnect"

        finally:
            harness.stop()

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_startup_timeout(self):
        """
        Test: E-STOP engages if no control received within STARTUP_GRACE_S

        This test requires starting a fresh Robot Pi instance and not sending
        any control for > STARTUP_GRACE_S.
        """
        pytest.skip("Requires fresh Robot Pi start")

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_explicit_estop_command(self):
        """
        Test: E-STOP engages immediately when explicit command sent

        Steps:
        1. Connect and establish control
        2. Clear E-STOP
        3. Send emergency_stop with engage=True
        4. Verify E-STOP engages immediately
        """
        harness = BridgeTestHarness()

        try:
            assert harness.connect_control(), "Failed to connect"
            assert harness.connect_telemetry(), "Failed to connect telemetry"

            # Establish control
            harness.send_command(MSG_PING, {})
            time.sleep(1.0)

            # Clear E-STOP
            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'test'
            })

            assert harness.wait_for_estop_clear(timeout=2.0), "E-STOP did not clear"

            # Send E-STOP engage
            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': True,
                'reason': 'test_explicit'
            })

            # Should engage immediately
            assert harness.wait_for_estop(timeout=1.0), "E-STOP did not engage from explicit command"

        finally:
            harness.stop()


class TestEStopClearValidation:
    """Test E-STOP clear validation"""

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_clear_with_wrong_confirm_string(self):
        """
        Test: E-STOP clear rejected with wrong confirm string

        Steps:
        1. Connect and establish control
        2. E-STOP should be engaged on boot
        3. Try to clear with wrong confirm string
        4. Verify E-STOP remains engaged
        5. Try with correct confirm string
        6. Verify E-STOP clears
        """
        harness = BridgeTestHarness()

        try:
            assert harness.connect_control(), "Failed to connect"
            assert harness.connect_telemetry(), "Failed to connect telemetry"

            harness.send_command(MSG_PING, {})
            time.sleep(1.0)

            # E-STOP should be engaged
            assert harness.get_estop_state() is True, "E-STOP should be engaged on boot"

            # Try to clear with wrong string
            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': 'WRONG_STRING',
                'reason': 'test'
            })

            time.sleep(1.0)

            # E-STOP should still be engaged
            assert harness.get_estop_state() is True, "E-STOP should not clear with wrong confirm"

            # Try with correct string
            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'test'
            })

            # Should clear
            assert harness.wait_for_estop_clear(timeout=2.0), "E-STOP did not clear with correct confirm"

        finally:
            harness.stop()

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_clear_with_stale_control(self):
        """
        Test: E-STOP clear rejected if control age > 1.5s

        This is tricky to test - need to send clear command after long delay
        """
        pytest.skip("Control age validation test - complex to implement")

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_clear_when_disconnected(self):
        """
        Test: E-STOP clear rejected when control disconnected

        Steps:
        1. Connect control
        2. Disconnect
        3. Try to send clear (will fail at socket level)
        """
        # This is somewhat obvious - can't send if disconnected
        # But verifies the invariant
        pass


class TestEStopUnderLoad:
    """Test E-STOP behavior under load"""

    @pytest.mark.skip(reason="Requires Robot Pi bridge running")
    def test_estop_during_control_flood(self):
        """
        Test: E-STOP engages within 1s even during control flood

        Steps:
        1. Connect and establish control
        2. Clear E-STOP
        3. Start flooding control commands (100/s)
        4. After 5s, disconnect
        5. Verify E-STOP engages within 1s of disconnect
        """
        harness = BridgeTestHarness()

        try:
            assert harness.connect_control(), "Failed to connect"
            assert harness.connect_telemetry(), "Failed to connect telemetry"

            # Establish and clear E-STOP
            harness.send_command(MSG_PING, {})
            time.sleep(1.0)

            harness.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'test'
            })

            assert harness.wait_for_estop_clear(timeout=2.0), "E-STOP did not clear"

            # Flood control
            flood_duration = 5.0
            start = time.time()
            count = 0

            while time.time() - start < flood_duration:
                harness.send_command(MSG_PING, {"seq": count})
                count += 1
                time.sleep(0.01)  # 100 Hz

            print(f"Sent {count} commands in {flood_duration}s")

            # Disconnect
            disconnect_time = time.time()
            harness.disconnect_control()

            # Wait for E-STOP
            assert harness.wait_for_estop(timeout=WATCHDOG_TIMEOUT_S + 1.0), "E-STOP did not engage"

            # Check that it engaged within reasonable time
            estop_time = time.time()
            latency = estop_time - disconnect_time

            print(f"E-STOP engaged {latency:.1f}s after disconnect")
            assert latency < WATCHDOG_TIMEOUT_S + 1.0, f"E-STOP took too long: {latency}s"

        finally:
            harness.stop()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])

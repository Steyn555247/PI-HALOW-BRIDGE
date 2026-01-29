#!/usr/bin/env python3
"""
Load & Throughput Stress Testing for Pi HaLow Bridge

Tests high-rate control commands, telemetry floods, video throughput, and concurrent channels.

Usage:
    python scripts/stress_load.py --test control_flood --duration 60
    python scripts/stress_load.py --test all --duration 120
"""

import argparse
import socket
import json
import time
import sys
import os
import threading
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import statistics

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.framing import SecureFramer
from common.constants import MSG_PING


@dataclass
class LoadTestResult:
    """Result of a load stress test"""
    test_name: str
    duration_s: float
    commands_sent: int
    commands_acked: int
    telemetry_received: int
    video_frames_received: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    passed: bool
    errors: List[str]


class LoadStressTester:
    """Runs load stress tests on simulated bridges"""

    def __init__(self):
        self.robot_proc: Optional[subprocess.Popen] = None
        self.base_proc: Optional[subprocess.Popen] = None

        self.control_port = 15401
        self.video_port = 15402
        self.telemetry_port = 15403

        # Test state
        self.control_socket: Optional[socket.socket] = None
        self.framer: Optional[SecureFramer] = None

        self.telemetry_socket: Optional[socket.socket] = None
        self.telemetry_framer: Optional[SecureFramer] = None
        self.telemetry_count = 0
        self.telemetry_running = False

        self.video_socket: Optional[socket.socket] = None
        self.video_frame_count = 0
        self.video_running = False

        self.latencies_ms = []

    def start_bridges(self):
        """Start Robot and Base Pi bridges"""
        # Start Robot Pi
        env = os.environ.copy()
        env.update({
            'SIM_MODE': 'true',
            'LOG_LEVEL': 'WARNING',
            'CONTROL_PORT': str(self.control_port),
            'VIDEO_PORT': str(self.video_port),
            'TELEMETRY_PORT': str(self.telemetry_port),
            'BASE_PI_IP': '127.0.0.1',
        })

        self.robot_proc = subprocess.Popen(
            [sys.executable, 'robot_pi/halow_bridge.py'],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent.parent
        )

        time.sleep(2.0)

        # Start Base Pi
        env.update({
            'ROBOT_PI_IP': '127.0.0.1',
            'VIDEO_HTTP_ENABLED': 'false',
        })

        self.base_proc = subprocess.Popen(
            [sys.executable, 'base_pi/halow_bridge.py'],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent.parent
        )

        time.sleep(2.0)

    def stop_bridges(self):
        """Stop all bridges"""
        if self.base_proc:
            self.base_proc.terminate()
            try:
                self.base_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.base_proc.kill()

        if self.robot_proc:
            self.robot_proc.terminate()
            try:
                self.robot_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.robot_proc.kill()

    def connect_control(self) -> bool:
        """Connect to Robot Pi control server"""
        try:
            self.framer = SecureFramer(role="base_pi_load_test")
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.settimeout(5.0)
            self.control_socket.connect(('127.0.0.1', self.control_port))
            return True
        except Exception as e:
            print(f"Failed to connect control: {e}")
            return False

    def connect_telemetry(self) -> bool:
        """Start telemetry receiver server"""
        try:
            self.telemetry_framer = SecureFramer(role="base_pi_telemetry_rx_test")
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', self.telemetry_port))
            server.listen(1)
            server.settimeout(5.0)

            self.telemetry_socket, addr = server.accept()
            self.telemetry_socket.settimeout(1.0)
            server.close()

            # Start receiver thread
            self.telemetry_running = True
            threading.Thread(target=self._telemetry_receiver_thread, daemon=True).start()

            return True
        except Exception as e:
            print(f"Failed to connect telemetry: {e}")
            return False

    def _telemetry_receiver_thread(self):
        """Receive telemetry in background"""
        while self.telemetry_running and self.telemetry_socket:
            try:
                payload, seq = self.telemetry_framer.read_frame_from_socket(
                    self.telemetry_socket, timeout=1.0
                )
                telemetry = json.loads(payload.decode('utf-8'))
                self.telemetry_count += 1
            except socket.timeout:
                continue
            except Exception:
                break

    def connect_video(self) -> bool:
        """Start video receiver server"""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', self.video_port))
            server.listen(1)
            server.settimeout(5.0)

            self.video_socket, addr = server.accept()
            self.video_socket.settimeout(1.0)
            server.close()

            # Start receiver thread
            self.video_running = True
            threading.Thread(target=self._video_receiver_thread, daemon=True).start()

            return True
        except Exception as e:
            print(f"Failed to connect video: {e}")
            return False

    def _video_receiver_thread(self):
        """Receive video frames in background"""
        buffer = b""
        while self.video_running and self.video_socket:
            try:
                data = self.video_socket.recv(65536)
                if not data:
                    break

                buffer += data

                # Count JPEG frames (SOI: 0xFFD8, EOI: 0xFFD9)
                while True:
                    soi = buffer.find(b'\xff\xd8')
                    if soi == -1:
                        if len(buffer) > 2:
                            buffer = buffer[-2:]
                        break

                    eoi = buffer.find(b'\xff\xd9', soi + 2)
                    if eoi == -1:
                        break

                    # Found frame
                    buffer = buffer[eoi + 2:]
                    self.video_frame_count += 1

            except socket.timeout:
                continue
            except Exception:
                break

    def send_command(self, command_type: str, data: Dict[str, Any] = None) -> bool:
        """Send control command and measure latency"""
        if not self.control_socket or not self.framer:
            return False

        message = {
            "type": command_type,
            "data": data or {},
            "timestamp": time.time()
        }

        try:
            send_time = time.time()
            payload = json.dumps(message).encode('utf-8')
            frame = self.framer.create_frame(payload)
            self.control_socket.sendall(frame)

            # For latency measurement, we approximate using send time
            # In reality, we'd need ACK from Robot Pi
            # For now, just record that we sent
            return True

        except Exception as e:
            return False

    def test_control_flood(self, duration: float = 60.0, rate: int = 100) -> LoadTestResult:
        """
        Test: Send control commands at high rate

        Args:
            duration: Test duration in seconds
            rate: Commands per second
        """
        print(f"\n{'='*60}")
        print(f"Test: Control Flood ({rate} cmd/s for {duration}s)")
        print(f"{'='*60}\n")

        errors = []
        self.start_bridges()

        if not self.connect_control():
            errors.append("Failed to connect control")
            self.stop_bridges()
            return LoadTestResult("control_flood", 0, 0, 0, 0, 0, 0, 0, 0, False, errors)

        if not self.connect_telemetry():
            errors.append("Failed to connect telemetry")
            self.stop_bridges()
            return LoadTestResult("control_flood", 0, 0, 0, 0, 0, 0, 0, 0, False, errors)

        time.sleep(1.0)

        # Flood control
        start_time = time.time()
        commands_sent = 0
        interval = 1.0 / rate

        print(f"Flooding control at {rate} Hz...")
        while time.time() - start_time < duration:
            if self.send_command(MSG_PING, {"seq": commands_sent}):
                commands_sent += 1
            else:
                errors.append(f"Failed to send command {commands_sent}")

            time.sleep(interval)

        elapsed = time.time() - start_time

        # Give telemetry time to catch up
        time.sleep(2.0)

        # Stop
        self.telemetry_running = False
        telemetry_count = self.telemetry_count

        self.stop_bridges()

        # Results
        actual_rate = commands_sent / elapsed
        telemetry_rate = telemetry_count / elapsed

        print(f"\nResults:")
        print(f"  Commands sent: {commands_sent} ({actual_rate:.1f} Hz)")
        print(f"  Telemetry received: {telemetry_count} ({telemetry_rate:.1f} Hz)")
        print(f"  Duration: {elapsed:.1f}s")

        # Pass criteria:
        # - At least 80% of commands sent
        # - Telemetry continues (at least 50% of expected)
        # - No crashes
        expected_telemetry = duration * 10  # Telemetry at ~10 Hz
        passed = (
            commands_sent >= duration * rate * 0.8 and
            telemetry_count >= expected_telemetry * 0.5 and
            len(errors) == 0
        )

        return LoadTestResult(
            "control_flood", elapsed, commands_sent, commands_sent,
            telemetry_count, 0, 0, 0, 0, passed, errors
        )

    def test_concurrent_channels(self, duration: float = 120.0) -> LoadTestResult:
        """
        Test: All channels active simultaneously

        - Control flood at 50 Hz
        - Telemetry at 10 Hz
        - Video at 10 FPS
        """
        print(f"\n{'='*60}")
        print(f"Test: Concurrent Channels ({duration}s)")
        print(f"{'='*60}\n")

        errors = []
        self.start_bridges()

        if not self.connect_control():
            errors.append("Failed to connect control")
            self.stop_bridges()
            return LoadTestResult("concurrent_channels", 0, 0, 0, 0, 0, 0, 0, 0, False, errors)

        if not self.connect_telemetry():
            errors.append("Failed to connect telemetry")

        if not self.connect_video():
            errors.append("Failed to connect video")

        time.sleep(1.0)

        # Start control flood
        control_rate = 50
        start_time = time.time()
        commands_sent = 0
        interval = 1.0 / control_rate

        print(f"Running all channels for {duration}s...")

        while time.time() - start_time < duration:
            if self.send_command(MSG_PING, {"seq": commands_sent}):
                commands_sent += 1
            time.sleep(interval)

        elapsed = time.time() - start_time

        # Give time to settle
        time.sleep(2.0)

        # Stop
        self.telemetry_running = False
        self.video_running = False

        telemetry_count = self.telemetry_count
        video_count = self.video_frame_count

        self.stop_bridges()

        # Results
        print(f"\nResults:")
        print(f"  Commands sent: {commands_sent} ({commands_sent / elapsed:.1f} Hz)")
        print(f"  Telemetry received: {telemetry_count} ({telemetry_count / elapsed:.1f} Hz)")
        print(f"  Video frames: {video_count} ({video_count / elapsed:.1f} FPS)")

        # Pass criteria: All channels functioning
        passed = (
            commands_sent >= duration * control_rate * 0.7 and
            telemetry_count >= duration * 5 and  # At least 5 Hz
            video_count >= duration * 3 and      # At least 3 FPS
            len(errors) == 0
        )

        return LoadTestResult(
            "concurrent_channels", elapsed, commands_sent, commands_sent,
            telemetry_count, video_count, 0, 0, 0, passed, errors
        )


def main():
    parser = argparse.ArgumentParser(
        description='Load & throughput stress testing for Pi HaLow Bridge'
    )
    parser.add_argument('--test', choices=['control_flood', 'concurrent', 'all'],
                        default='all', help='Test to run')
    parser.add_argument('--duration', type=float, default=60.0,
                        help='Test duration in seconds')
    args = parser.parse_args()

    tester = LoadStressTester()

    try:
        results = []

        if args.test == 'all':
            results.append(tester.test_control_flood(duration=args.duration))
            time.sleep(2.0)
            results.append(tester.test_concurrent_channels(duration=args.duration))

        elif args.test == 'control_flood':
            results.append(tester.test_control_flood(duration=args.duration))

        elif args.test == 'concurrent':
            results.append(tester.test_concurrent_channels(duration=args.duration))

        # Summary
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")

        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"[{status}] {r.test_name}")
            print(f"  Commands: {r.commands_sent}")
            print(f"  Telemetry: {r.telemetry_received}")
            print(f"  Video: {r.video_frames_received}")
            print(f"  Duration: {r.duration_s:.1f}s")
            if r.errors:
                print(f"  Errors: {len(r.errors)}")

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        print(f"\nOverall: {passed}/{total} passed")
        print(f"{'='*60}\n")

        return 0 if passed == total else 1

    finally:
        tester.stop_bridges()


if __name__ == '__main__':
    sys.exit(main())

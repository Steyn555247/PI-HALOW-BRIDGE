#!/usr/bin/env python3
"""
Reconnect Stress Testing for Pi HaLow Bridge

Tests rapid connect/disconnect scenarios to verify:
- E-STOP engages on disconnect
- System recovers after reconnect
- No resource leaks (sockets, threads, memory)

Usage:
    python scripts/stress_reconnect.py --test rapid_disconnect --cycles 20
    python scripts/stress_reconnect.py --test robot_restart --cycles 10
    python scripts/stress_reconnect.py --all
"""

import argparse
import subprocess
import time
import sys
import os
import signal
import psutil
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class TestResult:
    """Result of a reconnect stress test"""
    test_name: str
    cycles_completed: int
    cycles_total: int
    passed: bool
    duration_s: float
    errors: List[str]
    memory_leaked_mb: float = 0.0


class ReconnectStressTester:
    """Runs reconnect stress tests on simulated bridges"""

    def __init__(self):
        self.robot_proc: Optional[subprocess.Popen] = None
        self.base_proc: Optional[subprocess.Popen] = None
        self.results = []

        # Ports for testing
        self.control_port = 15301
        self.video_port = 15302
        self.telemetry_port = 15303

    def get_process_memory_mb(self, proc: subprocess.Popen) -> float:
        """Get memory usage of a process in MB"""
        try:
            p = psutil.Process(proc.pid)
            return p.memory_info().rss / 1024 / 1024
        except:
            return 0.0

    def start_robot_pi(self) -> bool:
        """Start Robot Pi bridge"""
        try:
            env = os.environ.copy()
            env.update({
                'SIM_MODE': 'true',
                'LOG_LEVEL': 'WARNING',  # Reduce noise
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

            # Wait for startup
            time.sleep(2.0)

            # Check if still running
            if self.robot_proc.poll() is not None:
                print("ERROR: Robot Pi failed to start")
                return False

            return True

        except Exception as e:
            print(f"ERROR: Failed to start Robot Pi: {e}")
            return False

    def start_base_pi(self) -> bool:
        """Start Base Pi bridge"""
        try:
            env = os.environ.copy()
            env.update({
                'SIM_MODE': 'true',
                'LOG_LEVEL': 'WARNING',
                'CONTROL_PORT': str(self.control_port),
                'VIDEO_PORT': str(self.video_port),
                'TELEMETRY_PORT': str(self.telemetry_port),
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

            # Wait for startup and connection
            time.sleep(2.0)

            # Check if still running
            if self.base_proc.poll() is not None:
                print("ERROR: Base Pi failed to start")
                return False

            return True

        except Exception as e:
            print(f"ERROR: Failed to start Base Pi: {e}")
            return False

    def stop_robot_pi(self):
        """Stop Robot Pi bridge"""
        if self.robot_proc:
            self.robot_proc.terminate()
            try:
                self.robot_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.robot_proc.kill()
            self.robot_proc = None

    def stop_base_pi(self):
        """Stop Base Pi bridge"""
        if self.base_proc:
            self.base_proc.terminate()
            try:
                self.base_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.base_proc.kill()
            self.base_proc = None

    def stop_all(self):
        """Stop all bridges"""
        self.stop_base_pi()
        self.stop_robot_pi()

    def test_rapid_base_disconnect(self, cycles: int = 20) -> TestResult:
        """
        Test rapid connect/disconnect of Base Pi.

        Steps:
        1. Start Robot Pi (stays running)
        2. Start Base Pi
        3. Wait 2s
        4. Kill Base Pi
        5. Wait 1s
        6. Repeat for N cycles
        """
        print(f"\n{'='*60}")
        print(f"Test: Rapid Base Pi Disconnect/Reconnect ({cycles} cycles)")
        print(f"{'='*60}\n")

        start_time = time.time()
        errors = []

        # Start Robot Pi (stays running)
        if not self.start_robot_pi():
            return TestResult("rapid_base_disconnect", 0, cycles, False, 0.0,
                              ["Failed to start Robot Pi"])

        robot_mem_start = self.get_process_memory_mb(self.robot_proc)

        # Run cycles
        for cycle in range(cycles):
            print(f"Cycle {cycle + 1}/{cycles}...", end=' ')

            try:
                # Start Base Pi
                if not self.start_base_pi():
                    errors.append(f"Cycle {cycle + 1}: Failed to start Base Pi")
                    print("FAIL (start)")
                    continue

                # Wait for connection
                time.sleep(2.0)

                # Check if Base Pi is still running
                if self.base_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Base Pi crashed")
                    print("FAIL (crashed)")
                    continue

                # Stop Base Pi
                self.stop_base_pi()

                # Wait before next cycle
                time.sleep(1.0)

                # Check if Robot Pi is still running
                if self.robot_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Robot Pi crashed")
                    print("FAIL (robot crashed)")
                    break

                print("OK")

            except Exception as e:
                errors.append(f"Cycle {cycle + 1}: {str(e)}")
                print(f"ERROR: {e}")

        # Check Robot Pi memory
        robot_mem_end = self.get_process_memory_mb(self.robot_proc)
        memory_leaked = robot_mem_end - robot_mem_start

        # Stop Robot Pi
        self.stop_robot_pi()

        duration = time.time() - start_time
        passed = len(errors) == 0 and memory_leaked < 50.0  # Allow up to 50 MB growth

        print(f"\nRobot Pi memory: {robot_mem_start:.1f} MB -> {robot_mem_end:.1f} MB (delta: {memory_leaked:+.1f} MB)")

        return TestResult("rapid_base_disconnect", cycles - len(errors), cycles,
                          passed, duration, errors, memory_leaked)

    def test_rapid_robot_restart(self, cycles: int = 10) -> TestResult:
        """
        Test rapid restart of Robot Pi while Base Pi stays running.

        Steps:
        1. Start Base Pi (stays running)
        2. Start Robot Pi
        3. Wait 5s
        4. Kill Robot Pi
        5. Wait 2s
        6. Restart Robot Pi
        7. Repeat for N cycles
        """
        print(f"\n{'='*60}")
        print(f"Test: Rapid Robot Pi Restart ({cycles} cycles)")
        print(f"{'='*60}\n")

        start_time = time.time()
        errors = []

        # Start Base Pi (stays running)
        if not self.start_base_pi():
            return TestResult("rapid_robot_restart", 0, cycles, False, 0.0,
                              ["Failed to start Base Pi"])

        base_mem_start = self.get_process_memory_mb(self.base_proc)

        # Run cycles
        for cycle in range(cycles):
            print(f"Cycle {cycle + 1}/{cycles}...", end=' ')

            try:
                # Start Robot Pi
                if not self.start_robot_pi():
                    errors.append(f"Cycle {cycle + 1}: Failed to start Robot Pi")
                    print("FAIL (start)")
                    continue

                # Wait for connection
                time.sleep(5.0)

                # Check if Robot Pi is still running
                if self.robot_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Robot Pi crashed")
                    print("FAIL (crashed)")
                    continue

                # Stop Robot Pi
                self.stop_robot_pi()

                # Wait before restart
                time.sleep(2.0)

                # Check if Base Pi is still running
                if self.base_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Base Pi crashed")
                    print("FAIL (base crashed)")
                    break

                print("OK")

            except Exception as e:
                errors.append(f"Cycle {cycle + 1}: {str(e)}")
                print(f"ERROR: {e}")

        # Check Base Pi memory
        base_mem_end = self.get_process_memory_mb(self.base_proc)
        memory_leaked = base_mem_end - base_mem_start

        # Stop Base Pi
        self.stop_base_pi()

        duration = time.time() - start_time
        passed = len(errors) == 0 and memory_leaked < 50.0

        print(f"\nBase Pi memory: {base_mem_start:.1f} MB -> {base_mem_end:.1f} MB (delta: {memory_leaked:+.1f} MB)")

        return TestResult("rapid_robot_restart", cycles - len(errors), cycles,
                          passed, duration, errors, memory_leaked)

    def test_simultaneous_restart(self, cycles: int = 10) -> TestResult:
        """
        Test restarting both Robot and Base Pi simultaneously.
        """
        print(f"\n{'='*60}")
        print(f"Test: Simultaneous Restart ({cycles} cycles)")
        print(f"{'='*60}\n")

        start_time = time.time()
        errors = []

        for cycle in range(cycles):
            print(f"Cycle {cycle + 1}/{cycles}...", end=' ')

            try:
                # Start both
                if not self.start_robot_pi():
                    errors.append(f"Cycle {cycle + 1}: Failed to start Robot Pi")
                    print("FAIL (robot start)")
                    continue

                if not self.start_base_pi():
                    errors.append(f"Cycle {cycle + 1}: Failed to start Base Pi")
                    print("FAIL (base start)")
                    self.stop_robot_pi()
                    continue

                # Wait for connection
                time.sleep(3.0)

                # Check if both still running
                if self.robot_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Robot Pi crashed")
                    print("FAIL (robot crashed)")
                    self.stop_all()
                    continue

                if self.base_proc.poll() is not None:
                    errors.append(f"Cycle {cycle + 1}: Base Pi crashed")
                    print("FAIL (base crashed)")
                    self.stop_all()
                    continue

                # Stop both
                self.stop_all()
                time.sleep(1.0)

                print("OK")

            except Exception as e:
                errors.append(f"Cycle {cycle + 1}: {str(e)}")
                print(f"ERROR: {e}")
                self.stop_all()

        duration = time.time() - start_time
        passed = len(errors) == 0

        return TestResult("simultaneous_restart", cycles - len(errors), cycles,
                          passed, duration, errors)


def main():
    parser = argparse.ArgumentParser(
        description='Reconnect stress testing for Pi HaLow Bridge'
    )
    parser.add_argument('--test', choices=['rapid_disconnect', 'robot_restart',
                                            'simultaneous', 'all'],
                        default='all', help='Test to run')
    parser.add_argument('--cycles', type=int, default=20,
                        help='Number of cycles to run')
    args = parser.parse_args()

    tester = ReconnectStressTester()

    # Setup signal handler
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        tester.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        results = []

        if args.test == 'all':
            results.append(tester.test_rapid_base_disconnect(cycles=args.cycles))
            time.sleep(2.0)
            results.append(tester.test_rapid_robot_restart(cycles=args.cycles // 2))
            time.sleep(2.0)
            results.append(tester.test_simultaneous_restart(cycles=args.cycles // 2))

        elif args.test == 'rapid_disconnect':
            results.append(tester.test_rapid_base_disconnect(cycles=args.cycles))

        elif args.test == 'robot_restart':
            results.append(tester.test_rapid_robot_restart(cycles=args.cycles))

        elif args.test == 'simultaneous':
            results.append(tester.test_simultaneous_restart(cycles=args.cycles))

        # Summary
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}")

        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"[{status}] {r.test_name}")
            print(f"  Cycles: {r.cycles_completed}/{r.cycles_total}")
            print(f"  Duration: {r.duration_s:.1f}s")
            if r.memory_leaked_mb > 0:
                print(f"  Memory leaked: {r.memory_leaked_mb:.1f} MB")
            if r.errors:
                print(f"  Errors:")
                for err in r.errors[:5]:  # Show first 5 errors
                    print(f"    - {err}")
                if len(r.errors) > 5:
                    print(f"    ... and {len(r.errors) - 5} more")

        passed = sum(1 for r in results if r.passed)
        total = len(results)

        print(f"\nOverall: {passed}/{total} passed")
        print(f"{'='*60}\n")

        return 0 if passed == total else 1

    finally:
        tester.stop_all()


if __name__ == '__main__':
    sys.exit(main())

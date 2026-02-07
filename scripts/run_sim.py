#!/usr/bin/env python3
"""
Run Pi HaLow Bridge in simulation mode.

Starts both Robot Pi and Base Pi bridges on localhost for testing.
All hardware is mocked - works on Windows without hardware.

Usage:
    python scripts/run_sim.py              # Start both bridges
    python scripts/run_sim.py --robot-only # Start only robot bridge
    python scripts/run_sim.py --base-only  # Start only base bridge

The system will:
1. Start Robot Pi bridge (control server, telemetry+video client)
2. Start Base Pi bridge (control client, telemetry+video server)
3. Both use mock hardware in SIM_MODE

Press Ctrl+C to stop.
"""

import os
import sys
import time
import signal
import subprocess
import argparse
import secrets
from pathlib import Path

# Ensure we're in the right directory
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
os.chdir(PROJECT_ROOT)

# Configuration
SIM_CONFIG = {
    'SIM_MODE': 'true',
    'SERPENT_PSK_HEX': secrets.token_hex(32),
    'LOG_LEVEL': 'DEBUG',
    # Use localhost for simulation
    'BASE_PI_IP': '127.0.0.1',
    'ROBOT_PI_IP': '127.0.0.1',
    'BACKEND_SOCKETIO_URL': 'http://127.0.0.1:5000',
}

# Port configuration
PORTS = {
    'CONTROL_PORT': '15001',
    'VIDEO_PORT': '15002',
    'TELEMETRY_PORT': '15003',
}


class SimRunner:
    """Runs Robot and Base bridges in simulation mode"""

    def __init__(self):
        self.processes = []
        self.running = True

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        print("\nShutdown signal received...")
        self.running = False
        self.stop_all()

    def _make_env(self, extra=None):
        """Create environment with simulation config"""
        env = os.environ.copy()
        env.update(SIM_CONFIG)
        env.update(PORTS)
        if extra:
            env.update(extra)
        return env

    def start_robot(self):
        """Start Robot Pi bridge"""
        print("Starting Robot Pi bridge...")
        env = self._make_env()

        proc = subprocess.Popen(
            [sys.executable, '-m', 'robot_pi.core.bridge_coordinator'],
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        self.processes.append(('Robot', proc))
        print(f"  PID: {proc.pid}")
        return proc

    def start_base(self):
        """Start Base Pi bridge"""
        print("Starting Base Pi bridge...")
        env = self._make_env()

        proc = subprocess.Popen(
            [sys.executable, '-m', 'base_pi.core.bridge_coordinator'],
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        self.processes.append(('Base', proc))
        print(f"  PID: {proc.pid}")
        return proc

    def stop_all(self):
        """Stop all processes"""
        for name, proc in self.processes:
            if proc.poll() is None:
                print(f"Stopping {name} bridge (PID {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"  Force killing {name}...")
                    proc.kill()

    def wait(self):
        """Wait for processes and monitor health"""
        print("\n" + "=" * 60)
        print("Simulation running. Press Ctrl+C to stop.")
        print("=" * 60)
        print()

        while self.running:
            # Check process health
            for name, proc in self.processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"WARNING: {name} bridge exited with code {ret}")

            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description='Run Pi HaLow Bridge in simulation mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--robot-only', action='store_true',
                        help='Start only Robot Pi bridge')
    parser.add_argument('--base-only', action='store_true',
                        help='Start only Base Pi bridge')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    if args.verbose:
        SIM_CONFIG['LOG_LEVEL'] = 'DEBUG'

    print("=" * 60)
    print("Pi HaLow Bridge Simulator")
    print("=" * 60)
    print()
    print("Configuration:")
    print(f"  SIM_MODE: {SIM_CONFIG['SIM_MODE']}")
    print(f"  PSK: {SIM_CONFIG['SERPENT_PSK_HEX'][:16]}...")
    print(f"  Control Port: {PORTS['CONTROL_PORT']}")
    print(f"  Video Port: {PORTS['VIDEO_PORT']}")
    print(f"  Telemetry Port: {PORTS['TELEMETRY_PORT']}")
    print()

    runner = SimRunner()

    try:
        if args.robot_only:
            runner.start_robot()
        elif args.base_only:
            runner.start_base()
        else:
            # Architecture:
            # - Robot Pi: Control SERVER, Telemetry CLIENT, Video CLIENT
            # - Base Pi: Control CLIENT, Telemetry SERVER, Video SERVER
            #
            # Start Robot first (control server), then Base.
            # Both have reconnect logic so order doesn't strictly matter,
            # but this minimizes initial connection failures.
            runner.start_robot()
            time.sleep(1)  # Give robot time to start control server
            runner.start_base()

        runner.wait()

    except KeyboardInterrupt:
        pass
    finally:
        runner.stop_all()

    print("\nSimulation stopped.")
    return 0


if __name__ == '__main__':
    sys.exit(main())

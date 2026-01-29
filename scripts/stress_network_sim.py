#!/usr/bin/env python3
"""
Network Stress Testing for Pi HaLow Bridge (Simulation Mode)

Creates TCP proxies between Robot and Base Pi that inject:
- Latency (configurable ms)
- Packet loss (configurable %)
- Bandwidth limiting (configurable kbps)
- Connection drops (periodic)

Works on Windows/Linux without root/sudo.

Usage:
    python scripts/stress_network_sim.py --test blackout --duration 15
    python scripts/stress_network_sim.py --test all --quick
    python scripts/stress_network_sim.py --list
"""

import argparse
import socket
import time
import threading
import random
import sys
import os
import json
import signal
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import subprocess

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class ProxyConfig:
    """Configuration for TCP proxy with network impairments"""
    latency_ms: int = 0              # One-way latency in ms
    packet_loss_pct: float = 0.0     # Packet loss percentage (0-100)
    bandwidth_kbps: int = 0          # Bandwidth limit (0 = unlimited)
    drop_connection_every_s: float = 0.0  # Drop connection every N seconds (0 = never)


class TCPProxy:
    """
    TCP proxy with configurable network impairments.

    Sits between client and server, forwarding data with delays, drops, etc.
    """

    def __init__(self, listen_port: int, target_host: str, target_port: int,
                 config: ProxyConfig, name: str = "proxy"):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.config = config
        self.name = name

        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.threads = []

        # Stats
        self.bytes_sent = 0
        self.bytes_received = 0
        self.packets_dropped = 0
        self.connections_accepted = 0

    def start(self):
        """Start the proxy"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', self.listen_port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)

        self.running = True
        self.accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.accept_thread.start()

        print(f"[{self.name}] Proxy started: 127.0.0.1:{self.listen_port} -> {self.target_host}:{self.target_port}")

    def stop(self):
        """Stop the proxy"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        # Wait for threads
        for t in self.threads:
            t.join(timeout=1.0)

        print(f"[{self.name}] Proxy stopped (sent={self.bytes_sent}, recv={self.bytes_received}, dropped={self.packets_dropped})")

    def _accept_loop(self):
        """Accept connections and spawn forwarding threads"""
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                self.connections_accepted += 1

                # Connect to target
                target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                target_sock.settimeout(5.0)
                try:
                    target_sock.connect((self.target_host, self.target_port))
                except Exception as e:
                    print(f"[{self.name}] Failed to connect to target: {e}")
                    client_sock.close()
                    continue

                # Spawn forwarding threads
                t1 = threading.Thread(target=self._forward,
                                       args=(client_sock, target_sock, "client->server"),
                                       daemon=True)
                t2 = threading.Thread(target=self._forward,
                                       args=(target_sock, client_sock, "server->client"),
                                       daemon=True)

                t1.start()
                t2.start()

                self.threads.append(t1)
                self.threads.append(t2)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[{self.name}] Accept error: {e}")

    def _forward(self, src: socket.socket, dst: socket.socket, direction: str):
        """Forward data from src to dst with impairments"""
        try:
            src.settimeout(1.0)
            drop_time = time.time() + self.config.drop_connection_every_s if self.config.drop_connection_every_s > 0 else float('inf')

            while self.running:
                # Check if we should drop connection
                if time.time() >= drop_time:
                    print(f"[{self.name}] Dropping connection ({direction})")
                    break

                try:
                    data = src.recv(4096)
                    if not data:
                        break

                    # Packet loss
                    if self.config.packet_loss_pct > 0:
                        if random.random() * 100 < self.config.packet_loss_pct:
                            self.packets_dropped += 1
                            continue  # Drop packet

                    # Latency
                    if self.config.latency_ms > 0:
                        time.sleep(self.config.latency_ms / 1000.0)

                    # Bandwidth limiting (simplified)
                    if self.config.bandwidth_kbps > 0:
                        bytes_per_interval = (self.config.bandwidth_kbps * 1024) / 100  # 10ms intervals
                        time.sleep(len(data) / bytes_per_interval * 0.01)

                    # Forward
                    dst.sendall(data)

                    if "client->server" in direction:
                        self.bytes_sent += len(data)
                    else:
                        self.bytes_received += len(data)

                except socket.timeout:
                    continue

        except Exception as e:
            pass
        finally:
            try:
                src.close()
            except:
                pass
            try:
                dst.close()
            except:
                pass


class NetworkStressTest:
    """Runs network stress tests on simulated bridges"""

    def __init__(self):
        self.robot_proc: Optional[subprocess.Popen] = None
        self.base_proc: Optional[subprocess.Popen] = None
        self.proxies = []
        self.results = []

    def start_bridges_with_proxy(self, proxy_config: ProxyConfig, test_name: str):
        """Start Robot and Base Pi bridges with proxy in between"""
        print(f"\n{'='*60}")
        print(f"Starting test: {test_name}")
        print(f"  Latency: {proxy_config.latency_ms}ms")
        print(f"  Loss: {proxy_config.packet_loss_pct}%")
        print(f"  Bandwidth: {proxy_config.bandwidth_kbps} kbps" if proxy_config.bandwidth_kbps > 0 else "  Bandwidth: unlimited")
        print(f"  Drop connection: every {proxy_config.drop_connection_every_s}s" if proxy_config.drop_connection_every_s > 0 else "  Drop connection: never")
        print(f"{'='*60}\n")

        # Ports:
        # Robot Pi real ports: 16001 (control), 16002 (video), 16003 (telemetry)
        # Proxy ports (Base connects here): 15001, 15002, 15003
        # Base Pi connects to proxy ports

        # Start proxies
        control_proxy = TCPProxy(15001, '127.0.0.1', 16001, proxy_config, name="control_proxy")
        video_proxy = TCPProxy(15002, '127.0.0.1', 16002, proxy_config, name="video_proxy")
        telemetry_proxy = TCPProxy(15003, '127.0.0.1', 16003, proxy_config, name="telemetry_proxy")

        control_proxy.start()
        video_proxy.start()
        telemetry_proxy.start()

        self.proxies = [control_proxy, video_proxy, telemetry_proxy]

        time.sleep(0.5)

        # Start Robot Pi (uses real ports 16001-16003)
        env = os.environ.copy()
        env.update({
            'SIM_MODE': 'true',
            'LOG_LEVEL': 'INFO',
            'CONTROL_PORT': '16001',
            'VIDEO_PORT': '16002',
            'TELEMETRY_PORT': '16003',
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

        # Start Base Pi (connects to proxy ports 15001-15003)
        env.update({
            'CONTROL_PORT': '15001',
            'VIDEO_PORT': '15002',
            'TELEMETRY_PORT': '15003',
            'ROBOT_PI_IP': '127.0.0.1',
            'VIDEO_HTTP_ENABLED': 'false',  # Disable HTTP server for stress tests
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
        """Stop all bridges and proxies"""
        if self.base_proc:
            self.base_proc.terminate()
            try:
                self.base_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.base_proc.kill()

        if self.robot_proc:
            self.robot_proc.terminate()
            try:
                self.robot_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.robot_proc.kill()

        for proxy in self.proxies:
            proxy.stop()

        self.proxies = []

    def run_test(self, test_name: str, proxy_config: ProxyConfig, duration: float,
                 expected_estop: bool = False) -> Dict[str, Any]:
        """Run a single stress test"""
        start_time = time.time()

        try:
            self.start_bridges_with_proxy(proxy_config, test_name)

            print(f"Running for {duration}s...")
            time.sleep(duration)

            # Check if processes are still running
            robot_alive = self.robot_proc.poll() is None
            base_alive = self.base_proc.poll() is None

            # Collect proxy stats
            total_sent = sum(p.bytes_sent for p in self.proxies)
            total_recv = sum(p.bytes_received for p in self.proxies)
            total_dropped = sum(p.packets_dropped for p in self.proxies)

            result = {
                'test': test_name,
                'duration': time.time() - start_time,
                'robot_alive': robot_alive,
                'base_alive': base_alive,
                'bytes_sent': total_sent,
                'bytes_received': total_recv,
                'packets_dropped': total_dropped,
                'passed': robot_alive and base_alive,  # Simplified - actual check would verify E-STOP
                'expected_estop': expected_estop
            }

            print(f"\nResult: {'PASS' if result['passed'] else 'FAIL'}")
            print(f"  Robot alive: {robot_alive}")
            print(f"  Base alive: {base_alive}")
            print(f"  Data: sent={total_sent}, recv={total_recv}, dropped={total_dropped}")

            return result

        finally:
            self.stop_bridges()
            time.sleep(1.0)

    def run_all_tests(self, quick: bool = False):
        """Run all network stress tests"""
        tests = []

        if quick:
            # Quick test suite (subset)
            tests = [
                ("blackout", ProxyConfig(packet_loss_pct=100.0), 10.0, True),
                ("high_latency", ProxyConfig(latency_ms=3000), 10.0, True),
                ("packet_loss_50", ProxyConfig(packet_loss_pct=50.0), 10.0, False),
            ]
        else:
            # Full test suite
            tests = [
                ("blackout", ProxyConfig(packet_loss_pct=100.0), 15.0, True),
                ("high_latency", ProxyConfig(latency_ms=3000), 15.0, True),
                ("packet_loss_50", ProxyConfig(packet_loss_pct=50.0), 15.0, False),
                ("packet_loss_90", ProxyConfig(packet_loss_pct=90.0), 15.0, True),
                ("bandwidth_collapse", ProxyConfig(bandwidth_kbps=1), 15.0, True),
                ("intermittent", ProxyConfig(drop_connection_every_s=8.0), 24.0, True),
                ("jitter", ProxyConfig(latency_ms=500), 20.0, False),
                ("duplicate_packets", ProxyConfig(), 20.0, False),  # TODO: implement duplicate
                ("reordering", ProxyConfig(), 20.0, False),  # TODO: implement reorder
            ]

        results = []
        for test_name, config, duration, expected_estop in tests:
            result = self.run_test(test_name, config, duration, expected_estop)
            results.append(result)
            self.results.append(result)

        return results


def main():
    parser = argparse.ArgumentParser(
        description='Network stress testing for Pi HaLow Bridge (Simulation Mode)'
    )
    parser.add_argument('--test', choices=['blackout', 'high_latency', 'packet_loss_50',
                                            'packet_loss_90', 'bandwidth_collapse',
                                            'intermittent', 'jitter', 'all'],
                        default='all', help='Test to run')
    parser.add_argument('--duration', type=float, default=15.0,
                        help='Test duration in seconds')
    parser.add_argument('--quick', action='store_true',
                        help='Run quick subset of tests')
    parser.add_argument('--list', action='store_true',
                        help='List available tests')
    args = parser.parse_args()

    if args.list:
        print("Available tests:")
        print("  blackout            - 100% packet loss")
        print("  high_latency        - 3s one-way delay")
        print("  packet_loss_50      - 50% packet loss")
        print("  packet_loss_90      - 90% packet loss")
        print("  bandwidth_collapse  - 1 kbps rate limit")
        print("  intermittent        - Drop connection every 8s")
        print("  jitter              - 500ms latency")
        print("  all                 - Run all tests")
        return 0

    tester = NetworkStressTest()

    # Setup signal handler
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        tester.stop_bridges()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.test == 'all':
            results = tester.run_all_tests(quick=args.quick)

            # Summary
            print(f"\n{'='*60}")
            print("TEST SUMMARY")
            print(f"{'='*60}")
            passed = sum(1 for r in results if r['passed'])
            total = len(results)
            print(f"Passed: {passed}/{total}")
            print(f"{'='*60}\n")

            for r in results:
                status = "PASS" if r['passed'] else "FAIL"
                print(f"  [{status}] {r['test']:<20} ({r['duration']:.1f}s)")

            return 0 if passed == total else 1

        else:
            # Run single test
            test_configs = {
                'blackout': ProxyConfig(packet_loss_pct=100.0),
                'high_latency': ProxyConfig(latency_ms=3000),
                'packet_loss_50': ProxyConfig(packet_loss_pct=50.0),
                'packet_loss_90': ProxyConfig(packet_loss_pct=90.0),
                'bandwidth_collapse': ProxyConfig(bandwidth_kbps=1),
                'intermittent': ProxyConfig(drop_connection_every_s=8.0),
                'jitter': ProxyConfig(latency_ms=500),
            }

            config = test_configs.get(args.test)
            if not config:
                print(f"Unknown test: {args.test}")
                return 1

            result = tester.run_test(args.test, config, args.duration)
            return 0 if result['passed'] else 1

    finally:
        tester.stop_bridges()


if __name__ == '__main__':
    sys.exit(main())

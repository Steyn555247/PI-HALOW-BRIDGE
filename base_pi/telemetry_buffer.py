"""
Telemetry Buffer Module

Circular buffer for recent telemetry history (last 60 seconds at 10 Hz).
Thread-safe access with locks for concurrent reads/writes.
"""

import threading
import time
from typing import Dict, List, Optional, Any
from collections import deque


class TelemetryBuffer:
    """
    Fixed-size circular buffer for telemetry data.

    Stores the last N samples efficiently using numpy arrays for numeric data
    and a deque for full telemetry dictionaries.
    """

    def __init__(self, max_samples: int = 600):
        """
        Initialize buffer.

        Args:
            max_samples: Maximum number of samples to store (default 600 = 60s at 10Hz)
        """
        self.max_samples = max_samples
        self.lock = threading.Lock()

        # Full telemetry history (for reconstruction)
        self.telemetry_history = deque(maxlen=max_samples)

        # Latest telemetry snapshot
        self.latest_telemetry: Optional[Dict[str, Any]] = None

        # Sample count
        self.sample_count = 0

    def add_sample(self, telemetry: Dict[str, Any]):
        """
        Add a new telemetry sample to the buffer.

        Args:
            telemetry: Telemetry dictionary from Robot Pi
        """
        with self.lock:
            self.telemetry_history.append(telemetry.copy())
            self.latest_telemetry = telemetry.copy()
            self.sample_count += 1

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent telemetry sample.

        Returns:
            Latest telemetry dict or None if no data
        """
        with self.lock:
            return self.latest_telemetry.copy() if self.latest_telemetry else None

    def get_history(self, seconds: int = 60) -> List[Dict[str, Any]]:
        """
        Get telemetry history for the last N seconds.

        Args:
            seconds: Number of seconds of history to retrieve (default 60)

        Returns:
            List of telemetry dicts, oldest first
        """
        with self.lock:
            if not self.telemetry_history:
                return []

            # Assume 10 Hz sampling
            max_samples = min(seconds * 10, len(self.telemetry_history))

            # Get last N samples
            history = list(self.telemetry_history)[-max_samples:]
            return [t.copy() for t in history]

    def get_stats(self) -> Dict[str, Any]:
        """
        Compute statistics (min/max/avg) for key metrics.

        Returns:
            Dictionary of stats for each metric
        """
        with self.lock:
            if not self.telemetry_history:
                return {}

            history = list(self.telemetry_history)

            stats = {
                'sample_count': len(history),
                'time_span_s': 0.0
            }

            # Compute time span
            if len(history) >= 2:
                first_ts = history[0].get('timestamp', 0)
                last_ts = history[-1].get('timestamp', 0)
                stats['time_span_s'] = last_ts - first_ts

            # Voltage stats
            voltages = [t.get('voltage', 0) for t in history if 'voltage' in t]
            if voltages:
                stats['voltage'] = {
                    'min': min(voltages),
                    'max': max(voltages),
                    'avg': sum(voltages) / len(voltages)
                }

            # RTT stats
            rtts = [t.get('rtt_ms', 0) for t in history if 'rtt_ms' in t]
            if rtts:
                stats['rtt_ms'] = {
                    'min': min(rtts),
                    'max': max(rtts),
                    'avg': sum(rtts) / len(rtts)
                }

            # Motor current stats (total and per-motor)
            motor_currents_list = [t.get('motor_currents', []) for t in history if 'motor_currents' in t]
            if motor_currents_list and motor_currents_list[0]:
                num_motors = len(motor_currents_list[0])

                # Total current
                totals = [sum(currents) for currents in motor_currents_list]
                stats['total_motor_current'] = {
                    'min': min(totals),
                    'max': max(totals),
                    'avg': sum(totals) / len(totals)
                }

                # Per-motor stats
                stats['motor_currents'] = []
                for motor_idx in range(num_motors):
                    motor_vals = [currents[motor_idx] for currents in motor_currents_list if motor_idx < len(currents)]
                    if motor_vals:
                        stats['motor_currents'].append({
                            'min': min(motor_vals),
                            'max': max(motor_vals),
                            'avg': sum(motor_vals) / len(motor_vals)
                        })

            # Barometer altitude stats
            altitudes = [t.get('barometer', {}).get('altitude', 0) for t in history
                        if 'barometer' in t and 'altitude' in t.get('barometer', {})]
            if altitudes:
                stats['altitude'] = {
                    'min': min(altitudes),
                    'max': max(altitudes),
                    'avg': sum(altitudes) / len(altitudes)
                }

            # Control age stats
            control_ages = [t.get('control_age_ms', 0) for t in history if 'control_age_ms' in t]
            if control_ages:
                stats['control_age_ms'] = {
                    'min': min(control_ages),
                    'max': max(control_ages),
                    'avg': sum(control_ages) / len(control_ages)
                }

            return stats

    def clear(self):
        """Clear all buffered data."""
        with self.lock:
            self.telemetry_history.clear()
            self.latest_telemetry = None
            self.sample_count = 0

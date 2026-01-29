#!/usr/bin/env python3
"""
Unified Stress Test Suite Runner for Pi HaLow Bridge

Runs all stress tests and generates a comprehensive report.

Usage:
    python scripts/run_stress_suite.py --phase all
    python scripts/run_stress_suite.py --phase 2 --phase 6  # Fault injection + E-STOP
    python scripts/run_stress_suite.py --quick
    python scripts/run_stress_suite.py --report-json results.json
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import os


@dataclass
class PhaseResult:
    """Result of running a test phase"""
    phase: int
    name: str
    tests_run: int
    tests_passed: int
    tests_failed: int
    duration_s: float
    errors: List[str]


class StressSuiteRunner:
    """Runs the complete stress test suite"""

    def __init__(self, quick: bool = False, duration: int = 60):
        self.quick = quick
        self.duration = duration
        self.results: List[PhaseResult] = []
        self.project_root = Path(__file__).parent.parent

    def run_phase_2_fault_injection(self) -> PhaseResult:
        """Run Phase 2: Fault Injection Tests"""
        print("\n" + "="*60)
        print("PHASE 2: FAULT INJECTION TESTS")
        print("="*60)

        start_time = time.time()
        errors = []

        try:
            # Run pytest on fault injection tests
            result = subprocess.run(
                [sys.executable, '-m', 'pytest', 'tests/test_fault_injection.py', '-v', '--tb=short'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120
            )

            # Parse pytest output for pass/fail counts
            output = result.stdout + result.stderr
            tests_run = output.count("PASSED") + output.count("FAILED") + output.count("SKIPPED")
            tests_passed = output.count("PASSED")
            tests_failed = output.count("FAILED")

            if result.returncode != 0 and tests_failed == 0:
                # No tests ran or pytest error
                errors.append("Pytest failed to run or no tests executed")
                tests_run = 1
                tests_failed = 1

        except subprocess.TimeoutExpired:
            errors.append("Phase 2 timed out")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0
        except Exception as e:
            errors.append(f"Phase 2 error: {str(e)}")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0

        duration = time.time() - start_time

        return PhaseResult(2, "Fault Injection", tests_run, tests_passed, tests_failed, duration, errors)

    def run_phase_6_estop_verification(self) -> PhaseResult:
        """Run Phase 6: E-STOP Verification Tests"""
        print("\n" + "="*60)
        print("PHASE 6: E-STOP VERIFICATION TESTS")
        print("="*60)

        start_time = time.time()
        errors = []

        try:
            # Run pytest on E-STOP tests
            result = subprocess.run(
                [sys.executable, '-m', 'pytest', 'tests/test_estop_triggers.py', '-v', '--tb=short'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            output = result.stdout + result.stderr
            tests_run = output.count("PASSED") + output.count("FAILED") + output.count("SKIPPED")
            tests_passed = output.count("PASSED")
            tests_failed = output.count("FAILED")

            if result.returncode != 0 and tests_failed == 0:
                errors.append("Pytest failed to run or no tests executed")
                tests_run = 1
                tests_failed = 1

        except subprocess.TimeoutExpired:
            errors.append("Phase 6 timed out")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0
        except Exception as e:
            errors.append(f"Phase 6 error: {str(e)}")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0

        duration = time.time() - start_time

        return PhaseResult(6, "E-STOP Verification", tests_run, tests_passed, tests_failed, duration, errors)

    def run_phase_1_2_network_stress_sim(self) -> PhaseResult:
        """Run Phase 1.2: Network Stress (Simulation)"""
        print("\n" + "="*60)
        print("PHASE 1.2: NETWORK STRESS TESTS (SIMULATION)")
        print("="*60)

        start_time = time.time()
        errors = []

        try:
            # Run network stress tests
            args = ['--quick'] if self.quick else []

            result = subprocess.run(
                [sys.executable, 'scripts/stress_network_sim.py', '--test', 'all'] + args,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600
            )

            output = result.stdout + result.stderr
            print(output)  # Show output

            # Parse results
            if 'Passed:' in output:
                # Extract pass/fail counts
                import re
                match = re.search(r'Passed: (\d+)/(\d+)', output)
                if match:
                    tests_passed = int(match.group(1))
                    tests_run = int(match.group(2))
                    tests_failed = tests_run - tests_passed
                else:
                    tests_run = 1
                    tests_passed = 0 if result.returncode != 0 else 1
                    tests_failed = 1 if result.returncode != 0 else 0
            else:
                tests_run = 1
                tests_passed = 0 if result.returncode != 0 else 1
                tests_failed = 1 if result.returncode != 0 else 0

            if result.returncode != 0:
                errors.append("Network stress tests failed")

        except subprocess.TimeoutExpired:
            errors.append("Phase 1.2 timed out")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0
        except Exception as e:
            errors.append(f"Phase 1.2 error: {str(e)}")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0

        duration = time.time() - start_time

        return PhaseResult(1, "Network Stress (Sim)", tests_run, tests_passed, tests_failed, duration, errors)

    def run_phase_4_reconnect_stress(self) -> PhaseResult:
        """Run Phase 4: Reconnect Stress Tests"""
        print("\n" + "="*60)
        print("PHASE 4: RECONNECT STRESS TESTS")
        print("="*60)

        start_time = time.time()
        errors = []

        try:
            # Run reconnect stress tests
            cycles = 10 if self.quick else 20

            result = subprocess.run(
                [sys.executable, 'scripts/stress_reconnect.py', '--test', 'all', '--cycles', str(cycles)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600
            )

            output = result.stdout + result.stderr
            print(output)

            # Parse results
            if 'passed' in output.lower():
                import re
                match = re.search(r'(\d+)/(\d+) passed', output)
                if match:
                    tests_passed = int(match.group(1))
                    tests_run = int(match.group(2))
                    tests_failed = tests_run - tests_passed
                else:
                    tests_run = 1
                    tests_passed = 0 if result.returncode != 0 else 1
                    tests_failed = 1 if result.returncode != 0 else 0
            else:
                tests_run = 1
                tests_passed = 0 if result.returncode != 0 else 1
                tests_failed = 1 if result.returncode != 0 else 0

            if result.returncode != 0:
                errors.append("Reconnect stress tests failed")

        except subprocess.TimeoutExpired:
            errors.append("Phase 4 timed out")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0
        except Exception as e:
            errors.append(f"Phase 4 error: {str(e)}")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0

        duration = time.time() - start_time

        return PhaseResult(4, "Reconnect Stress", tests_run, tests_passed, tests_failed, duration, errors)

    def run_phase_3_load_stress(self) -> PhaseResult:
        """Run Phase 3: Load & Throughput Stress Tests"""
        print("\n" + "="*60)
        print("PHASE 3: LOAD & THROUGHPUT STRESS TESTS")
        print("="*60)

        start_time = time.time()
        errors = []

        try:
            # Run load stress tests
            duration = 30 if self.quick else self.duration

            result = subprocess.run(
                [sys.executable, 'scripts/stress_load.py', '--test', 'all', '--duration', str(duration)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=duration * 3 + 60
            )

            output = result.stdout + result.stderr
            print(output)

            # Parse results
            if 'passed' in output.lower():
                import re
                match = re.search(r'(\d+)/(\d+) passed', output)
                if match:
                    tests_passed = int(match.group(1))
                    tests_run = int(match.group(2))
                    tests_failed = tests_run - tests_passed
                else:
                    tests_run = 1
                    tests_passed = 0 if result.returncode != 0 else 1
                    tests_failed = 1 if result.returncode != 0 else 0
            else:
                tests_run = 1
                tests_passed = 0 if result.returncode != 0 else 1
                tests_failed = 1 if result.returncode != 0 else 0

            if result.returncode != 0:
                errors.append("Load stress tests failed")

        except subprocess.TimeoutExpired:
            errors.append("Phase 3 timed out")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0
        except Exception as e:
            errors.append(f"Phase 3 error: {str(e)}")
            tests_run = 1
            tests_failed = 1
            tests_passed = 0

        test_duration = time.time() - start_time

        return PhaseResult(3, "Load & Throughput", tests_run, tests_passed, tests_failed, test_duration, errors)

    def run_phases(self, phases: List[int]):
        """Run selected test phases"""
        phase_runners = {
            1: self.run_phase_1_2_network_stress_sim,
            2: self.run_phase_2_fault_injection,
            3: self.run_phase_3_load_stress,
            4: self.run_phase_4_reconnect_stress,
            6: self.run_phase_6_estop_verification,
        }

        for phase in phases:
            if phase in phase_runners:
                result = phase_runners[phase]()
                self.results.append(result)
            else:
                print(f"WARNING: Phase {phase} not implemented or not runnable")

    def generate_report(self, json_file: str = None):
        """Generate test report"""
        print("\n" + "="*80)
        print("STRESS TEST SUITE - FINAL REPORT")
        print("="*80)

        total_tests = sum(r.tests_run for r in self.results)
        total_passed = sum(r.tests_passed for r in self.results)
        total_failed = sum(r.tests_failed for r in self.results)
        total_duration = sum(r.duration_s for r in self.results)

        for result in self.results:
            status = "✓ PASS" if result.tests_failed == 0 else "✗ FAIL"
            print(f"\n[{status}] Phase {result.phase}: {result.name}")
            print(f"  Tests run: {result.tests_run}")
            print(f"  Passed: {result.tests_passed}")
            print(f"  Failed: {result.tests_failed}")
            print(f"  Duration: {result.duration_s:.1f}s")
            if result.errors:
                print(f"  Errors:")
                for err in result.errors:
                    print(f"    - {err}")

        print("\n" + "="*80)
        print(f"OVERALL: {total_passed}/{total_tests} tests passed")
        print(f"Total duration: {total_duration:.1f}s ({total_duration / 60:.1f} min)")
        print("="*80 + "\n")

        # JSON report
        if json_file:
            report = {
                'timestamp': time.time(),
                'quick_mode': self.quick,
                'duration_requested': self.duration,
                'total_tests': total_tests,
                'total_passed': total_passed,
                'total_failed': total_failed,
                'total_duration_s': total_duration,
                'phases': [asdict(r) for r in self.results]
            }

            with open(json_file, 'w') as f:
                json.dump(report, f, indent=2)

            print(f"JSON report written to: {json_file}\n")

        return total_failed == 0


def main():
    parser = argparse.ArgumentParser(
        description='Unified stress test suite for Pi HaLow Bridge',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Run all tests (quick mode):
    python run_stress_suite.py --quick

  Run specific phases:
    python run_stress_suite.py --phase 2 --phase 6

  Run full suite with custom duration:
    python run_stress_suite.py --phase all --duration 120

  Generate JSON report:
    python run_stress_suite.py --quick --report-json results.json
        """
    )

    parser.add_argument('--phase', action='append', type=int,
                        help='Phase to run (can specify multiple). Available: 1, 2, 3, 4, 6')
    parser.add_argument('--quick', action='store_true',
                        help='Run quick subset of tests')
    parser.add_argument('--duration', type=int, default=60,
                        help='Duration for load tests (seconds)')
    parser.add_argument('--report-json', type=str,
                        help='Output JSON report to file')

    args = parser.parse_args()

    # Determine which phases to run
    if not args.phase:
        # Default: run all implemented phases
        phases = [2, 6, 1, 4, 3]  # Ordered by implementation priority
    elif 'all' in [str(p) for p in args.phase]:
        phases = [2, 6, 1, 4, 3]
    else:
        phases = args.phase

    # Run test suite
    runner = StressSuiteRunner(quick=args.quick, duration=args.duration)

    print("="*80)
    print("PI HALOW BRIDGE - STRESS TEST SUITE")
    print("="*80)
    print(f"Mode: {'QUICK' if args.quick else 'FULL'}")
    print(f"Phases: {', '.join(map(str, phases))}")
    print(f"Duration (load tests): {args.duration}s")
    print("="*80)

    runner.run_phases(phases)
    success = runner.generate_report(json_file=args.report_json)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Run all tests for Pi HaLow Bridge.

Usage:
    python scripts/test_all.py           # Run all tests
    python scripts/test_all.py -v        # Verbose output
    python scripts/test_all.py framing   # Run only framing tests
"""

import os
import sys
import unittest
import argparse

# Ensure we're in the right directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
os.chdir(PROJECT_ROOT)

# Add project root to path
sys.path.insert(0, PROJECT_ROOT)

# Force SIM_MODE for all tests
os.environ['SIM_MODE'] = 'true'

# Generate a test PSK
os.environ['SERPENT_PSK_HEX'] = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'


def main():
    parser = argparse.ArgumentParser(description='Run Pi HaLow Bridge tests')
    parser.add_argument('pattern', nargs='?', default='test_*.py',
                        help='Test file pattern (default: test_*.py)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    args = parser.parse_args()

    # Build test pattern
    if not args.pattern.startswith('test_'):
        args.pattern = f'test_{args.pattern}'
    if not args.pattern.endswith('.py'):
        args.pattern = f'{args.pattern}*.py'

    print("=" * 60)
    print("Pi HaLow Bridge Test Suite")
    print("=" * 60)
    print(f"SIM_MODE: {os.environ.get('SIM_MODE', 'not set')}")
    print(f"PSK configured: {'Yes' if os.environ.get('SERPENT_PSK_HEX') else 'No'}")
    print(f"Test pattern: {args.pattern}")
    print("=" * 60)
    print()

    # Discover and run tests
    loader = unittest.TestLoader()
    suite = loader.discover('tests', pattern=args.pattern)

    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    if result.failures:
        print("\nFailed tests:")
        for test, _ in result.failures:
            print(f"  - {test}")

    if result.errors:
        print("\nTests with errors:")
        for test, _ in result.errors:
            print(f"  - {test}")

    # Return exit code
    if result.wasSuccessful():
        print("\nAll tests PASSED!")
        return 0
    else:
        print("\nSome tests FAILED!")
        return 1


if __name__ == '__main__':
    sys.exit(main())

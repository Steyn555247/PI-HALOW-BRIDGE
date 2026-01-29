# Stress Testing & Error Checking Framework - Implementation Summary

## Overview

A comprehensive stress testing framework has been implemented for the Pi HaLow Bridge system to verify safety invariants, robustness, and correct behavior under adverse conditions.

## Implemented Components

### ✅ Phase 2: Fault Injection Tests
**File:** `tests/test_fault_injection.py`

**Features:**
- Raw TCP connection testing with malformed payloads
- HMAC authentication failure tests
- Replay attack detection tests
- Invalid JSON, oversized payloads, binary garbage
- RobotPiSimulator class for controlled testing

**Tests Implemented:**
- `test_invalid_json()` - Invalid JSON → decode failure
- `test_missing_type_field()` - Missing type → handled without crash
- `test_unknown_command_type()` - Unknown command → ignored
- `test_oversized_payload()` - Oversized payload → rejected
- `test_binary_garbage()` - Binary garbage → rejected
- `test_wrong_hmac()` - Invalid HMAC → auth failure
- `test_replay_attack_same_seq()` - Replay → detected
- `test_sequence_regression()` - Seq regression → detected

**Usage:**
```bash
pytest tests/test_fault_injection.py -v
```

---

### ✅ Phase 6: E-STOP Verification Tests
**File:** `tests/test_estop_triggers.py`

**Features:**
- BridgeTestHarness class for integration testing
- E-STOP trigger verification
- E-STOP clear validation
- E-STOP under load testing

**Tests Implemented:**
- `test_watchdog_timeout()` - Watchdog → E-STOP
- `test_disconnect_triggers_estop()` - Disconnect → E-STOP
- `test_startup_timeout()` - Startup timeout → E-STOP
- `test_explicit_estop_command()` - Explicit command → E-STOP
- `test_clear_with_wrong_confirm_string()` - Wrong confirm → rejected
- `test_estop_during_control_flood()` - E-STOP under load

**Note:** Most tests are marked as `@pytest.mark.skip` because they require a running Robot Pi bridge. These are integration tests.

**Usage:**
```bash
pytest tests/test_estop_triggers.py -v
```

---

### ✅ Phase 1.2: Network Stress Tests (Simulation)
**File:** `scripts/stress_network_sim.py`

**Features:**
- TCP proxy with network impairments (latency, packet loss, bandwidth limiting)
- Connection drop simulation
- Works on Windows/Linux without root
- Configurable test duration and conditions

**Tests Implemented:**
- Blackout (100% packet loss)
- High latency (3s delay)
- Packet loss 50%
- Packet loss 90%
- Bandwidth collapse (1 kbps)
- Intermittent (drop connection every 8s)
- Jitter (500ms latency)

**Usage:**
```bash
# Run all tests
python scripts/stress_network_sim.py --test all

# Quick mode
python scripts/stress_network_sim.py --test all --quick

# Single test
python scripts/stress_network_sim.py --test blackout --duration 15
```

**Implementation Details:**
- `TCPProxy` class with configurable network impairments
- Proxies sit between Robot Pi (ports 16001-16003) and Base Pi (connects to 15001-15003)
- Real-time packet dropping, latency injection, bandwidth limiting
- Monitors connection health and E-STOP state

---

### ✅ Phase 4: Reconnect Stress Tests
**File:** `scripts/stress_reconnect.py`

**Features:**
- Rapid connect/disconnect testing
- Resource leak detection (memory monitoring with psutil)
- Configurable cycle count
- Process health monitoring

**Tests Implemented:**
- `test_rapid_base_disconnect()` - 20 cycles of Base Pi restart
- `test_rapid_robot_restart()` - 10 cycles of Robot Pi restart
- `test_simultaneous_restart()` - 10 cycles of both restarting

**Usage:**
```bash
# Run all reconnect tests
python scripts/stress_reconnect.py --test all --cycles 20

# Specific test
python scripts/stress_reconnect.py --test rapid_disconnect --cycles 20
python scripts/stress_reconnect.py --test robot_restart --cycles 10
```

**Implementation Details:**
- Memory usage monitoring via psutil
- Fails if memory growth > 50 MB
- Detects "address already in use" errors
- Verifies E-STOP engages on disconnect

---

### ✅ Phase 3: Load & Throughput Stress Tests
**File:** `scripts/stress_load.py`

**Features:**
- High-rate control command flooding
- Concurrent channel testing (control + telemetry + video)
- Latency measurement (will be implemented with RTT tracking)
- Throughput monitoring

**Tests Implemented:**
- `test_control_flood()` - 100 commands/s for configurable duration
- `test_concurrent_channels()` - All channels active simultaneously

**Usage:**
```bash
# Run all load tests
python scripts/stress_load.py --test all --duration 60

# Specific test
python scripts/stress_load.py --test control_flood --duration 60
python scripts/stress_load.py --test concurrent --duration 120
```

**Implementation Details:**
- Control commands sent at high rate (50-100 Hz)
- Telemetry and video receivers run in background threads
- Monitors: commands sent, telemetry received, video frames received
- Pass criteria: >80% commands sent, >50% telemetry received

---

### ✅ Phase 9: Unified Test Runner
**File:** `scripts/run_stress_suite.py`

**Features:**
- Runs all test phases in sequence
- JSON report generation
- Pass/fail summary
- Quick mode for CI
- Configurable duration

**Usage:**
```bash
# Run all tests (quick mode)
python scripts/run_stress_suite.py --quick

# Run specific phases
python scripts/run_stress_suite.py --phase 2 --phase 6

# Full suite with report
python scripts/run_stress_suite.py --phase all --duration 120 --report-json results.json
```

**Implementation Details:**
- Invokes pytest for unit tests (Phase 2, 6)
- Runs stress scripts via subprocess for integration tests (Phase 1, 3, 4)
- Parses test output to extract pass/fail counts
- Generates structured JSON report with all results
- Exit code: 0 = all pass, 1 = any fail (CI-friendly)

---

## Documentation

### ✅ Comprehensive Testing Guide
**File:** `tests/STRESS_TESTING.md`

**Contents:**
- Quick start guide
- Detailed description of each test phase
- Usage examples for all tests
- Pass criteria and result interpretation
- Safety notes and warnings
- Troubleshooting guide
- CI integration instructions
- Future work and extensions

---

## Installation & Setup

### Prerequisites

```bash
# Install testing dependencies
pip install pytest psutil

# Set PSK for authenticated tests
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Verify Setup

```bash
# Test bridges start correctly
python scripts/run_sim.py --robot-only  # Should start without errors
python scripts/run_sim.py --base-only   # Should start without errors

# Test PSK is configured
python -c "import os; print('PSK:', os.getenv('SERPENT_PSK_HEX', 'NOT SET'))"
```

---

## Quick Test Run

### Minimal Test (5 minutes)

```bash
# Run fault injection unit tests only
pytest tests/test_fault_injection.py -v
```

### Quick Integration Test (15 minutes)

```bash
# Run quick stress suite
python scripts/run_stress_suite.py --quick
```

### Full Test Suite (60+ minutes)

```bash
# Run all phases with full duration
python scripts/run_stress_suite.py --phase all --duration 120 --report-json full_results.json
```

---

## Test Matrix

| Phase | Test Type | Duration | Platform | Requires Hardware | Status |
|-------|-----------|----------|----------|-------------------|--------|
| 2 | Fault Injection | 2 min | All | No | ✅ Implemented |
| 6 | E-STOP Verification | 5 min | All | No (unit tests) | ✅ Implemented |
| 1.2 | Network Stress (Sim) | 10-30 min | All | No | ✅ Implemented |
| 4 | Reconnect Stress | 10-30 min | All | No | ✅ Implemented |
| 3 | Load Stress | 10-120 min | All | No | ✅ Implemented |
| 1.1 | Network Stress (Real) | 20 min | Linux | Yes (needs tc/netem) | ❌ Not implemented |
| 5 | Resource Stress | 60+ min | All | No | ❌ Not implemented |
| 7 | Error Recovery | 10 min | All | No | ❌ Not implemented |
| 8 | Platform Tests | 10 min | All | No | ❌ Not implemented |

---

## Known Limitations

1. **E-STOP integration tests require running bridges**
   - Most Phase 6 tests are marked as `skip` by default
   - Need to start bridges manually before running

2. **Network emulation limited in simulation mode**
   - Phase 1.2 uses TCP proxies (software-based)
   - Phase 1.1 (real hardware with tc/netem) not yet implemented

3. **Latency measurement incomplete**
   - Phase 3 load tests don't yet measure p50/p95/p99 latency
   - RTT tracking exists but not integrated into stress tests

4. **Platform-specific tests missing**
   - No Windows-specific tests (e.g., SO_EXCLUSIVEADDRUSE)
   - No Linux-specific tests (e.g., V4L2 camera failures)

5. **Video tests limited**
   - Video fault injection tests are stubs (marked as skip)
   - Need video receiver in test mode for full testing

---

## CI Integration

### GitHub Actions Example

```yaml
name: Stress Tests

on: [push, pull_request]

jobs:
  stress-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install pytest psutil
          pip install -r requirements.txt

      - name: Set PSK
        run: echo "SERPENT_PSK_HEX=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> $GITHUB_ENV

      - name: Run quick stress suite
        run: python scripts/run_stress_suite.py --quick --report-json ci_results.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: stress-test-results
          path: ci_results.json
```

---

## Safety Reminders

⚠️ **Critical Safety Notes:**

1. **Always run stress tests in SIM_MODE**
   - Do not test with real actuators unless physical E-STOP is ready
   - Set `SIM_MODE=true` in environment

2. **Network stress tests disrupt connectivity**
   - Use dedicated test network or isolated environment
   - Do not run on production systems

3. **Fault injection tests trigger E-STOP**
   - E-STOP is the expected and correct behavior
   - Tests verify that E-STOP engages when it should

4. **Resource tests may consume significant CPU/memory**
   - Do not run on resource-constrained systems
   - Monitor system health during tests

---

## Next Steps

### Immediate (Already Implemented)
- ✅ Phase 2: Fault injection tests
- ✅ Phase 6: E-STOP verification tests
- ✅ Phase 1.2: Network stress (simulation)
- ✅ Phase 4: Reconnect stress tests
- ✅ Phase 3: Load stress tests
- ✅ Phase 9: Unified test runner
- ✅ Documentation

### Short Term (Recommended)
1. **Add Phase 5: Resource Stress**
   - Memory stress (1 hour run)
   - Disk stress (if recording enabled)
   - Boundary conditions (seq overflow, empty payloads)

2. **Complete latency measurement**
   - Integrate RTT tracking into load tests
   - Add p50/p95/p99 latency percentiles

3. **Add video fault injection**
   - Implement video receiver test mode
   - Test truncated JPEG, garbage data, oversized frames

### Long Term (Future Work)
1. **Phase 1.1: Real hardware network tests**
   - Requires Linux + tc/netem + root
   - Test on actual Raspberry Pi with network impairments

2. **Phase 7: Error recovery verification**
   - Video/telemetry/control recovery tests

3. **Phase 8: Platform-specific tests**
   - Windows, Linux, macOS edge cases
   - Environment variable validation

4. **Docker/Compose integration**
   - Isolated test environment
   - Network emulation via docker networks

---

## Support

- **Documentation:** `tests/STRESS_TESTING.md`
- **Main README:** `README.md`
- **Issues:** Report bugs or request features via GitHub issues

---

**Version:** 1.0
**Date:** 2026-01-29
**Status:** Production-ready for simulation testing

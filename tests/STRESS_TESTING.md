# Pi HaLow Bridge - Stress Testing & Error Checking Framework

Comprehensive stress testing framework to verify safety invariants, robustness, and correct behavior under adverse conditions.

## Quick Start

```bash
# Run quick stress test suite (all phases, reduced duration)
python scripts/run_stress_suite.py --quick

# Run specific test phases
python scripts/run_stress_suite.py --phase 2 --phase 6

# Run full suite with custom duration
python scripts/run_stress_suite.py --phase all --duration 120

# Generate JSON report
python scripts/run_stress_suite.py --quick --report-json results.json
```

## Test Phases

### Phase 1: Network Stress Tests (Simulation)

Tests network impairments using TCP proxies (works on Windows/Linux without root).

**Tests:**
- **Blackout** - 100% packet loss (15s) → Expect E-STOP
- **High Latency** - 3s one-way delay (15s) → Expect E-STOP
- **Packet Loss 50%** - 50% loss (15s) → System survives
- **Packet Loss 90%** - 90% loss (15s) → Expect E-STOP
- **Bandwidth Collapse** - 1 kbps rate limit (15s) → Expect E-STOP
- **Intermittent** - 8s on / 3s off cycles (24s) → Expect E-STOP
- **Jitter** - 500ms ± 200ms delay (20s) → System survives

**Usage:**
```bash
# Run all network tests
python scripts/stress_network_sim.py --test all

# Run specific test
python scripts/stress_network_sim.py --test blackout --duration 15

# Quick mode (subset of tests)
python scripts/stress_network_sim.py --test all --quick
```

**Implementation:**
- Creates TCP proxies between Robot and Base Pi
- Proxies inject latency, packet loss, bandwidth limits, connection drops
- Verifies E-STOP behavior and system recovery

---

### Phase 2: Fault Injection Tests

Unit tests for malformed payloads and authentication failures.

**Control Tests:**
- Invalid JSON in control frame → Auth/decode failure → E-STOP
- Missing `type` field → Logged and ignored
- Unknown command type → Logged, no actuation
- Oversized payload (> 16 KB) → Rejected → E-STOP
- Binary garbage → Decode/auth failure → E-STOP
- Replay attack (same seq twice) → ReplayError → E-STOP
- Wrong HMAC → Auth failure → E-STOP
- Sequence regression (N then N-1) → ReplayError → E-STOP

**Telemetry Tests:**
- Invalid JSON → Base logs error, no crash
- Oversized frame → Rejected or truncated
- Wrong HMAC → Base rejects, no crash

**Video Tests:**
- Truncated JPEG → Base buffers, resync on next frame
- Garbage between frames → Base skips to next SOI
- Oversized frame (> MAX_VIDEO_BUFFER) → Buffer overflow handling
- Rapid tiny frames → No OOM, bounded buffer

**Usage:**
```bash
# Run all fault injection tests
pytest tests/test_fault_injection.py -v

# Run specific test
pytest tests/test_fault_injection.py::TestControlFaultInjection::test_invalid_json -v
```

**Implementation:**
- Uses raw TCP connections to send malformed frames
- Manually builds frames with invalid HMAC, wrong seq, etc.
- Verifies E-STOP engages or connection closes as expected

---

### Phase 3: Load & Throughput Stress Tests

High-rate commands, telemetry floods, video throughput, concurrent channels.

**Tests:**
- **Control Flood** - 100 commands/s for 60s
  - Verify: no crash, no E-STOP from overload, latency bounded (p95 < 500ms)
- **Concurrent Channels** - Control flood + telemetry + video simultaneously for 120s
  - Verify: control has priority, all channels function, no deadlock

**Usage:**
```bash
# Run all load tests
python scripts/stress_load.py --test all --duration 60

# Run specific test
python scripts/stress_load.py --test control_flood --duration 60
python scripts/stress_load.py --test concurrent --duration 120
```

**Implementation:**
- Connects control, telemetry, and video channels
- Floods control commands at configurable rate
- Monitors telemetry and video throughput
- Measures latency percentiles (p50, p95, p99)

---

### Phase 4: Reconnect Stress Tests

Rapid connect/disconnect, restart under load, resource leak detection.

**Tests:**
- **Rapid Base Disconnect** - 20 cycles of: connect → wait 2s → disconnect → wait 1s
  - Verify: Robot engages E-STOP on disconnect, accepts reconnect, no leak
- **Rapid Robot Restart** - 10 cycles of: start → wait 5s → kill → wait 2s → restart
  - Verify: Base detects disconnect, reconnects when Robot is back, no leak
- **Simultaneous Restart** - 10 cycles of: start both → wait 3s → kill both → restart
  - Verify: Both recover cleanly, no resource leak

**Usage:**
```bash
# Run all reconnect tests
python scripts/stress_reconnect.py --test all --cycles 20

# Run specific test
python scripts/stress_reconnect.py --test rapid_disconnect --cycles 20
python scripts/stress_reconnect.py --test robot_restart --cycles 10
```

**Implementation:**
- Starts/stops Robot and Base Pi bridges programmatically
- Monitors process memory usage (RSS)
- Detects memory leaks (> 50 MB growth = fail)
- Verifies no "address already in use" errors

---

### Phase 6: E-STOP Behavior Verification

Verifies all E-STOP triggers and clear validation.

**E-STOP Trigger Tests:**
- **Watchdog** - Stop sending control for > 5s → E-STOP with watchdog reason
- **Disconnect** - Close control socket → E-STOP within ~5s
- **Auth Failure** - Send bad HMAC → E-STOP immediately
- **Replay** - Resend old seq → E-STOP immediately
- **Buffer Overflow** - Send oversized frame → E-STOP or disconnect
- **Startup Timeout** - Never send control for > 30s → E-STOP after grace
- **Explicit Command** - Send `emergency_stop` engage → E-STOP immediately

**E-STOP Clear Validation Tests:**
- **Wrong Confirm String** - E-STOP clear rejected
- **Stale Control** - Control age > 1.5s → Clear rejected
- **Disconnected** - Can't send clear when disconnected
- **Correct Confirm** - E-STOP clears with correct string

**E-STOP Under Load:**
- Control flood at 100 Hz → Disconnect → Verify E-STOP within 1s

**Usage:**
```bash
# Run all E-STOP tests (requires Robot Pi running)
pytest tests/test_estop_triggers.py -v

# Run specific test
pytest tests/test_estop_triggers.py::TestEStopTriggers::test_watchdog_timeout -v
```

**Note:** Most E-STOP tests are marked as `skip` because they require a running Robot Pi bridge in test mode. These are integration tests, not unit tests.

---

## Test Requirements

### Software Requirements

- Python 3.8+
- pytest (`pip install pytest`)
- psutil (`pip install psutil`)
- All Pi HaLow Bridge dependencies

### Hardware Requirements

**Unit Tests (Phase 2, 6):**
- No special hardware
- Can run on Windows/Linux/Mac

**Simulation Tests (Phase 1.2, 3, 4):**
- No special hardware
- Runs in SIM_MODE with mock hardware
- Can run on Windows/Linux/Mac

**Real Hardware Tests (Phase 1.1 - pi_torture.sh):**
- Linux with `tc` (traffic control) and netem
- Requires root/sudo for network emulation
- Raspberry Pi recommended

### Environment Setup

```bash
# Install dependencies
pip install pytest psutil

# Set PSK for authenticated tests
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Verify setup
python scripts/run_sim.py --base-only  # Test Base Pi starts
python scripts/run_sim.py --robot-only # Test Robot Pi starts
```

---

## Safety Notes

⚠️ **IMPORTANT SAFETY REMINDERS:**

1. **Do not run stress tests with real actuators without E-STOP ready**
   - Use SIM_MODE for stress testing
   - Ensure physical E-STOP button is accessible if testing real hardware

2. **Network stress tests will disrupt connectivity**
   - Use a dedicated test network if possible
   - Do not run on production systems

3. **Fault injection tests are safe**
   - They send malformed data to trigger E-STOP
   - E-STOP is the expected and correct behavior

4. **Document any test that requires physical safety measures**
   - If adding new tests, update safety notes
   - Consider adding `--dry-run` mode for new tests

---

## Continuous Integration

### Quick Test (CI-friendly)

Runs a subset of tests suitable for CI:

```bash
# Quick mode (reduced duration and cycles)
python scripts/run_stress_suite.py --quick --report-json ci_results.json

# Exit code: 0 = all pass, 1 = any fail
echo $?
```

**Duration:** ~10-15 minutes

**Tests Run:**
- Phase 2: Fault injection (unit tests)
- Phase 6: E-STOP verification (skipped tests noted)
- Phase 1: Network stress (quick mode, 3 tests)
- Phase 4: Reconnect stress (10 cycles)
- Phase 3: Load stress (30s duration)

### Full Test Suite

Runs all tests with full duration:

```bash
python scripts/run_stress_suite.py --phase all --duration 120 --report-json full_results.json
```

**Duration:** ~30-60 minutes

---

## Interpreting Results

### Pass Criteria

**Phase 1 (Network Stress):**
- Processes don't crash
- E-STOP engages when expected (blackout, high latency, etc.)
- System recovers when network is restored

**Phase 2 (Fault Injection):**
- Malformed payloads trigger E-STOP or are rejected
- No crashes from invalid input
- Authentication failures handled correctly

**Phase 3 (Load Stress):**
- Commands sent at target rate (>80% of requested)
- Telemetry continues (>50% of expected rate)
- Latency bounded (p95 < 500ms for control flood)
- All channels function under concurrent load

**Phase 4 (Reconnect Stress):**
- All cycles complete successfully
- No resource leaks (memory growth < 50 MB)
- No "address already in use" errors

**Phase 6 (E-STOP Verification):**
- All E-STOP triggers engage E-STOP as expected
- E-STOP clear validation works correctly
- E-STOP engages within 1s even under load

### Common Failures

**"Address already in use" errors:**
- Solution: Kill orphan processes before running tests
- Windows: `powershell -Command "Stop-Process -Name python -Force"`
- Linux: `pkill -9 python`

**Memory leak detected:**
- Investigate: Check for socket/thread cleanup in bridge code
- Debug: Run single reconnect cycle with logging enabled

**E-STOP doesn't engage:**
- Investigate: Check watchdog timeout, control age, connection state
- Debug: Enable DEBUG logging and review watchdog loop

**Tests timeout:**
- Investigate: Deadlock in bridge code, infinite loop, or blocking I/O
- Debug: Attach debugger or add detailed logging

---

## Extending the Framework

### Adding New Tests

1. **Create test file:**
   ```bash
   touch tests/test_my_new_feature.py
   ```

2. **Follow pytest conventions:**
   ```python
   import pytest

   class TestMyFeature:
       def test_something(self):
           assert True
   ```

3. **Add to run_stress_suite.py:**
   ```python
   def run_phase_X_my_new_tests(self) -> PhaseResult:
       # Run your tests
       pass
   ```

4. **Document in this README:**
   - Add phase description
   - List tests and expected behavior
   - Provide usage examples

### Adding New Stress Scripts

1. **Create script:**
   ```bash
   touch scripts/stress_my_test.py
   ```

2. **Follow naming convention:**
   - `stress_*.py` for stress tests
   - `test_*.py` for unit tests

3. **Provide CLI interface:**
   - Use argparse
   - Support `--test`, `--duration`, `--quick` flags
   - Exit with 0 on success, 1 on failure

4. **Integrate with run_stress_suite.py**

---

## Known Limitations

1. **E-STOP tests require running bridges**
   - Most Phase 6 tests are integration tests
   - Cannot run as pure unit tests
   - Consider using docker-compose for isolated test environment

2. **Network emulation requires root on Linux**
   - Phase 1.1 (pi_torture.sh) needs sudo
   - Phase 1.2 (simulation proxy) works without root

3. **Platform-specific behaviors**
   - Windows: SO_EXCLUSIVEADDRUSE vs SO_REUSEADDR
   - Linux: V4L2 camera backend
   - Test on target platform for accurate results

4. **Video tests are limited**
   - Difficult to test MJPEG parsing without full integration
   - Consider adding mock video receiver for unit tests

---

## Troubleshooting

### Pytest can't find modules

```bash
# Ensure parent directory is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/test_fault_injection.py -v
```

### PSK not configured

```bash
# Set PSK for tests
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Ports already in use

```bash
# Kill orphan processes (Windows)
powershell -Command "Stop-Process -Name python -Force"

# Kill orphan processes (Linux)
pkill -9 python

# Check ports (Windows)
powershell -Command "Get-NetTCPConnection -LocalPort 15001,15002,15003"

# Check ports (Linux)
sudo netstat -tulpn | grep 1500
```

### Bridges won't start

```bash
# Check logs
python robot_pi/halow_bridge.py  # Should show startup logs
python base_pi/halow_bridge.py   # Should show startup logs

# Check config
echo $SIM_MODE
echo $SERPENT_PSK_HEX
```

---

## Future Work

1. **Phase 1.1: Extend pi_torture.sh**
   - Add network emulation tests for real hardware
   - Requires Linux + tc + netem + root

2. **Phase 5: Resource & Boundary Stress**
   - Memory stress (1 hour run)
   - Disk stress (recording enabled)
   - Boundary conditions (seq overflow, empty payload, etc.)

3. **Phase 7: Error Recovery Verification**
   - Video recovery after camera failure
   - Telemetry recovery after disconnect
   - Control recovery after reconnect

4. **Phase 8: Platform & Environment Tests**
   - Cross-platform testing (Windows, Linux, macOS)
   - Environment variable edge cases
   - PSK validation tests

5. **Docker/Compose Integration**
   - Run bridges in isolated containers
   - Network emulation via docker networks
   - Easier CI integration

6. **Automated Latency Measurement**
   - Ping/pong timestamping
   - Latency histograms
   - P50, P95, P99 tracking

---

## References

- [Pi HaLow Bridge Architecture](../README.md)
- [Safety Invariants](../common/constants.py)
- [Secure Framing](../common/framing.py)
- [E-STOP Documentation](../docs/ESTOP.md) *(if exists)*

---

**Last Updated:** 2026-01-29

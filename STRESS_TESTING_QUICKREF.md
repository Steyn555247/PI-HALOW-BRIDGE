# Stress Testing Quick Reference

## Setup

```bash
# Install dependencies
pip install pytest psutil

# Set PSK
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Kill orphan processes (Windows)
powershell -Command "Stop-Process -Name python -Force"

# Kill orphan processes (Linux)
pkill -9 python
```

---

## Quick Commands

### Run All Tests (Quick Mode)
```bash
python scripts/run_stress_suite.py --quick
```

### Run All Tests (Full Suite)
```bash
python scripts/run_stress_suite.py --phase all --duration 120
```

### Run Specific Phase
```bash
# Phase 2: Fault injection
pytest tests/test_fault_injection.py -v

# Phase 6: E-STOP verification
pytest tests/test_estop_triggers.py -v

# Phase 1.2: Network stress
python scripts/stress_network_sim.py --test all --quick

# Phase 4: Reconnect stress
python scripts/stress_reconnect.py --test all --cycles 20

# Phase 3: Load stress
python scripts/stress_load.py --test all --duration 60
```

---

## Individual Tests

### Fault Injection
```bash
# All fault injection tests
pytest tests/test_fault_injection.py -v

# Single test
pytest tests/test_fault_injection.py::TestControlFaultInjection::test_invalid_json -v
```

### Network Stress
```bash
# Blackout test (100% packet loss)
python scripts/stress_network_sim.py --test blackout --duration 15

# High latency test (3s delay)
python scripts/stress_network_sim.py --test high_latency --duration 15

# Quick mode (3 tests)
python scripts/stress_network_sim.py --test all --quick

# Full mode (9 tests)
python scripts/stress_network_sim.py --test all
```

### Reconnect Stress
```bash
# Rapid Base Pi disconnect (20 cycles)
python scripts/stress_reconnect.py --test rapid_disconnect --cycles 20

# Rapid Robot Pi restart (10 cycles)
python scripts/stress_reconnect.py --test robot_restart --cycles 10

# Simultaneous restart (10 cycles)
python scripts/stress_reconnect.py --test simultaneous --cycles 10

# All reconnect tests
python scripts/stress_reconnect.py --test all --cycles 20
```

### Load Stress
```bash
# Control flood (100 cmd/s for 60s)
python scripts/stress_load.py --test control_flood --duration 60

# Concurrent channels (control + telemetry + video for 120s)
python scripts/stress_load.py --test concurrent --duration 120

# All load tests
python scripts/stress_load.py --test all --duration 60
```

---

## Generate Reports

```bash
# Quick test with JSON report
python scripts/run_stress_suite.py --quick --report-json results.json

# Full test with JSON report
python scripts/run_stress_suite.py --phase all --duration 120 --report-json full_results.json

# View JSON report
cat results.json | python -m json.tool
```

---

## Debugging

### Check PSK
```bash
python -c "import os; print('PSK:', os.getenv('SERPENT_PSK_HEX', 'NOT SET'))"
```

### Check Ports (Windows)
```bash
powershell -Command "Get-NetTCPConnection -LocalPort 15001,15002,15003"
```

### Check Ports (Linux)
```bash
sudo netstat -tulpn | grep 1500
```

### Test Bridge Startup
```bash
# Robot Pi only
python scripts/run_sim.py --robot-only

# Base Pi only
python scripts/run_sim.py --base-only

# Both (normal sim)
python scripts/run_sim.py
```

### Enable Debug Logging
```bash
export LOG_LEVEL=DEBUG
python robot_pi/halow_bridge.py
```

---

## CI/CD Integration

### Minimal Test (5 min)
```bash
pytest tests/test_fault_injection.py -v
```

### Quick Integration (15 min)
```bash
python scripts/run_stress_suite.py --quick --report-json ci_results.json
```

### Full Suite (60+ min)
```bash
python scripts/run_stress_suite.py --phase all --duration 120 --report-json full_results.json
```

---

## Common Issues

### "Address already in use"
```bash
# Kill all python processes
powershell -Command "Stop-Process -Name python -Force"  # Windows
pkill -9 python  # Linux
```

### "No module named pytest"
```bash
pip install pytest psutil
```

### "PSK not configured"
```bash
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Bridges won't start
```bash
# Check config
echo $SIM_MODE
echo $SERPENT_PSK_HEX
echo $LOG_LEVEL

# Try manual start with debug
export LOG_LEVEL=DEBUG
python robot_pi/halow_bridge.py
```

---

## Test Duration Reference

| Test | Quick Mode | Full Mode |
|------|------------|-----------|
| Fault Injection | 2 min | 2 min |
| E-STOP Verification | 3 min | 5 min |
| Network Stress | 5 min | 20 min |
| Reconnect Stress | 10 min | 30 min |
| Load Stress | 5 min | 60 min |
| **Total** | **~15 min** | **~2 hours** |

---

## Pass Criteria Quick Check

✅ **Fault Injection:** All malformed payloads rejected or trigger E-STOP
✅ **E-STOP:** All triggers engage E-STOP, clear validation works
✅ **Network:** E-STOP on blackout/high latency, survives packet loss
✅ **Reconnect:** All cycles complete, memory growth < 50 MB
✅ **Load:** Commands sent (>80%), telemetry received (>50%), no crash

---

**Quick Start:**
```bash
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")
python scripts/run_stress_suite.py --quick
```

# Pi HaLow Bridge - Quick Reference

## 🚀 Quick Commands

### Setup & Run Simulation

```bash
# Set PSK (required)
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Run simulation (both bridges)
python scripts/run_sim.py

# Run only Robot Pi
python scripts/run_sim.py --robot-only

# Run only Base Pi
python scripts/run_sim.py --base-only
```

### Test Video HTTP Endpoint

```bash
# Health check
curl http://localhost:5004/health

# Single frame
curl http://localhost:5004/frame > test_frame.jpg

# MJPEG stream (use Ctrl+C to stop)
curl http://localhost:5004/video > stream.mjpeg
```

### Run Tests

```bash
# Unit tests
python scripts/test_all.py
python scripts/test_all.py framing
python scripts/test_all.py estop

# Quick stress test (15 min)
pip install pytest psutil
python scripts/run_stress_suite.py --quick

# Full stress test (2+ hours)
python scripts/run_stress_suite.py --phase all --duration 120
```

---

## 📡 Architecture Overview

### Control Channel (Base → Robot, TCP:5001)
- **Robot Pi is SERVER** (accepts connections from Base Pi)
- **Base Pi is CLIENT** (connects to Robot Pi)
- HMAC-SHA256 authenticated, replay protection
- Highest priority

### Telemetry Channel (Robot → Base, TCP:5003)
- Robot Pi is CLIENT (connects to Base Pi)
- Base Pi is SERVER (receives from Robot Pi)
- HMAC-SHA256 authenticated
- 10 Hz (100ms interval)
- Includes RTT from ping/pong

### Video Channel (Robot → Base, TCP:5002)
- Robot Pi is CLIENT (connects to Base Pi)
- Base Pi is SERVER (receives from Robot Pi)
- Unauthenticated MJPEG stream
- 640×480 @ 10 FPS
- Backpressure: frames dropped if socket blocked

### Video HTTP (Base Pi, HTTP:5004)
- MJPEG streaming to browser/clients
- Endpoints: `/video`, `/frame`, `/health`
- Serves frames from Video Receiver

---

## 🔐 PSK Management

### Generate PSK

```bash
python generate_psk.py
# OR
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Deploy to Raspberry Pis

```bash
# Both Pis
sudo mkdir -p /etc/serpent
sudo chmod 700 /etc/serpent
echo "YOUR_64_CHAR_PSK" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk

# Verify
cat /etc/serpent/psk | wc -c  # Should output 64
```

---

## 🚢 Deployment

### Robot Pi

```bash
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE
sudo ./scripts/pi_install.sh --robot
sudo ./scripts/pi_enable_services.sh --robot
sudo systemctl status serpent-robot-bridge
```

### Base Pi

```bash
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE
sudo ./scripts/pi_install.sh --base
sudo ./scripts/pi_enable_services.sh --base
sudo systemctl status serpent-base-bridge

# Test video endpoint
curl http://localhost:5004/health
```

---

## 🛡️ Safety Invariants (Critical)

1. **E-STOP Boot Latched** - Robot boots with E-STOP ENGAGED
2. **Watchdog Timeout** - 5 seconds without control → E-STOP
3. **E-STOP SET Semantics** - Never toggle, always explicit engage/clear
4. **HMAC Authentication** - All control/telemetry authenticated
5. **Control Priority** - Video never starves control
6. **Fail-Safe** - Any error → E-STOP

---

## 🔧 Troubleshooting

### Kill Orphan Processes

```bash
# Windows
powershell -Command "Stop-Process -Name python -Force"

# Linux
sudo pkill -9 -f halow_bridge
```

### Check Service Status

```bash
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge
sudo journalctl -u serpent-robot-bridge -f
sudo journalctl -u serpent-base-bridge -f
```

### Check Connections

```bash
# Check ports
ss -tlnp | grep 500

# Check PSK
cat /etc/serpent/psk | wc -c

# Ping test
ping 192.168.100.2  # Base → Robot
ping 192.168.100.1  # Robot → Base
```

### E-STOP Won't Clear

```bash
# Check logs for rejection reason
sudo journalctl -u serpent-robot-bridge | grep "REJECTED"
sudo journalctl -u serpent-robot-bridge | grep "CLEAR"

# Verify PSK
cat /etc/serpent/psk | wc -c  # Must be 64
```

### No Telemetry

```bash
# Check Robot Pi sending
sudo journalctl -u serpent-robot-bridge | grep "telemetry"

# Check Base Pi receiving
sudo journalctl -u serpent-base-bridge | grep "telemetry_received"

# Check HMAC failures
sudo journalctl -u serpent-base-bridge | grep "HMAC"
```

### No Video

```bash
# Check cameras (Robot Pi)
ls -la /dev/video*
v4l2-ctl --list-devices

# Check video stats
sudo journalctl -u serpent-robot-bridge | grep "frames_sent\|frames_dropped"

# Test HTTP endpoint (Base Pi)
curl http://localhost:5004/health
curl http://localhost:5004/frame > test.jpg
```

---

## 📊 Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SERPENT_PSK_HEX` | - | **Yes** | 64-char hex PSK |
| `SIM_MODE` | `false` | No | Enable simulation mode |
| `ROBOT_PI_IP` | `192.168.100.2` | No | Robot Pi IP |
| `BASE_PI_IP` | `192.168.100.1` | No | Base Pi IP |
| `CONTROL_PORT` | `5001` | No | Control channel port |
| `VIDEO_PORT` | `5002` | No | Video channel port |
| `TELEMETRY_PORT` | `5003` | No | Telemetry channel port |
| `VIDEO_HTTP_PORT` | `5004` | No | Video HTTP port (Base Pi) |
| `LOG_LEVEL` | `INFO` | No | Logging level |

---

## 🧪 Stress Testing

### Quick Test (15 min)

```bash
pip install pytest psutil
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")
python scripts/run_stress_suite.py --quick
```

### Individual Phases

```bash
# Fault injection
pytest tests/test_fault_injection.py -v

# E-STOP verification
pytest tests/test_estop_triggers.py -v

# Network stress
python scripts/stress_network_sim.py --test all --quick

# Reconnect stress
python scripts/stress_reconnect.py --test all --cycles 20

# Load stress
python scripts/stress_load.py --test all --duration 60
```

---

## 📡 Protocol Messages

### Control (Base → Robot)

```json
{"type": "emergency_stop", "data": {"engage": true, "reason": "operator"}}
{"type": "emergency_stop", "data": {"engage": false, "confirm_clear": "ESTOP_CLEAR_CONFIRM"}}
{"type": "ping", "data": {"ts": 1234567890.123, "seq": 1}}
{"type": "clamp_close", "data": {}}
{"type": "clamp_open", "data": {}}
{"type": "start_camera", "data": {"camera_id": 0}}
```

### Telemetry (Robot → Base)

```json
{
  "voltage": 12.6,
  "height": 45.0,
  "estop": {"engaged": false},
  "pong": {"ping_ts": 1234567890.123, "ping_seq": 1},
  "control_age_ms": 50,
  "rtt_ms": 25,
  "timestamp": 1234567890.123
}
```

---

## 🔒 Safety Constants (Immutable)

| Constant | Value | Cannot Override |
|----------|-------|-----------------|
| `WATCHDOG_TIMEOUT_S` | `5.0` | ✅ Immutable |
| `STARTUP_GRACE_S` | `30.0` | ✅ Immutable |
| `ESTOP_CLEAR_MAX_AGE_S` | `1.5` | ✅ Immutable |
| `ESTOP_CLEAR_CONFIRM` | `"ESTOP_CLEAR_CONFIRM"` | ✅ Immutable |
| `HEARTBEAT_INTERVAL_S` | `1.0` | ✅ Immutable |

---

## 📂 Important Files

| File | Description |
|------|-------------|
| `robot_pi/halow_bridge.py` | Robot Pi main (control SERVER) |
| `base_pi/halow_bridge.py` | Base Pi main (control CLIENT, Video HTTP) |
| `common/framing.py` | HMAC-SHA256 framing |
| `common/constants.py` | Safety constants |
| `tests/STRESS_TESTING.md` | Comprehensive stress testing guide |
| `STRESS_TESTING_QUICKREF.md` | Stress testing quick reference |

---

## 🎯 Key Changes in v1.1

1. **Control Channel Architecture** - Robot Pi is now SERVER (not client)
2. **Video HTTP Endpoint** - MJPEG at `http://localhost:5004/video`
3. **RTT Measurement** - Ping/pong heartbeat with timestamp tracking
4. **Camera Health** - Exponential backoff recovery for failed cameras
5. **E-STOP Debounce** - 300ms debounce for emergency_status events
6. **Stress Testing** - 26+ tests across 5 phases

---

## 📞 Quick Links

- **Main README:** [README.md](README.md)
- **Stress Testing:** [tests/STRESS_TESTING.md](tests/STRESS_TESTING.md)
- **Project Summary:** [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- **Integration Guide:** [INTEGRATION.md](INTEGRATION.md)
- **Safety Hardening:** [SAFETY_HARDENING.md](SAFETY_HARDENING.md)
- **GitHub:** https://github.com/Steyn555247/PI-HALOW-BRIDGE

---

**Version:** 1.1
**Last Updated:** 2026-01-29

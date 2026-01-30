# Pi HaLow Bridge - Project Summary

## 🎉 Project Status: Production Ready (v1.1)

A comprehensive, HMAC-authenticated communication bridge for long-range wireless robot control over HaLow (802.11ah). Designed for Serpent Robotics rope-climbing robots with fail-safe E-STOP system and extensive stress testing.

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production deployment ready with comprehensive stress testing

---

## 📁 Project Structure

```
pi_halow_bridge/
│
├── README.md                         # Main project documentation
├── QUICK_REFERENCE.md                # Command & troubleshooting quick reference
├── PROJECT_SUMMARY.md                # This file
├── SAFETY_HARDENING.md               # Safety architecture documentation
├── .gitignore                        # Git ignore patterns
├── generate_psk.py                   # PSK generation utility
│
├── common/                           # Shared components
│   ├── __init__.py
│   ├── constants.py                  # Safety constants (immutable)
│   └── framing.py                    # HMAC-SHA256 secure framing
│
├── base_pi/                          # Base Pi (Operator Station)
│   ├── __init__.py
│   ├── config.py                     # Configuration management
│   ├── halow_bridge.py               # Main coordinator (control CLIENT)
│   ├── control_sender.py             # Sends control to Robot Pi (TCP client)
│   ├── telemetry_receiver.py         # Receives telemetry (TCP server)
│   ├── video_receiver.py             # Receives MJPEG stream (TCP server)
│   ├── video_http.py                 # Video HTTP server (port 5004)
│   ├── requirements.txt              # Python dependencies
│   ├── .env.example                  # Configuration template
│   ├── serpent-base-bridge.service   # Systemd service file
│   └── README.md                     # Base Pi documentation
│
├── robot_pi/                         # Robot Pi (On Robot)
│   ├── __init__.py
│   ├── config.py                     # Configuration management
│   ├── halow_bridge.py               # Main coordinator (control SERVER)
│   ├── control_receiver.py           # Receives control (TCP server)
│   ├── telemetry_sender.py           # Sends telemetry (TCP client)
│   ├── video_sender.py               # Sends MJPEG stream (TCP client)
│   ├── actuator_controller.py        # E-STOP + motor/servo control
│   ├── sensor_reader.py              # BNO085 IMU + BMP388 barometer
│   ├── video_capture.py              # 3× USB camera capture + health monitoring
│   ├── requirements.txt              # Python dependencies
│   ├── .env.example                  # Configuration template
│   ├── serpent-robot-bridge.service  # Systemd service file
│   └── README.md                     # Robot Pi documentation
│
├── scripts/                          # Testing and utilities
│   ├── run_sim.py                    # Simulation mode runner
│   ├── test_all.py                   # Unit test runner
│   ├── stress_network_sim.py         # Network stress tests (Phase 1.2)
│   ├── stress_reconnect.py           # Reconnect stress tests (Phase 4)
│   ├── stress_load.py                # Load stress tests (Phase 3)
│   └── run_stress_suite.py           # Unified stress test runner (Phase 9)
│
└── tests/                            # Test suite
    ├── STRESS_TESTING.md             # Comprehensive stress testing guide
    ├── test_fault_injection.py       # Fault injection tests (Phase 2)
    ├── test_estop_triggers.py        # E-STOP verification tests (Phase 6)
    └── __init__.py
```

**Total Files**: 40+ files across codebase, tests, scripts, and documentation

---

## ✨ Key Features (v1.1)

### Communication Architecture
✅ **HMAC-SHA256 Authentication** - All control/telemetry authenticated with PSK
✅ **Replay Protection** - Monotonic sequence numbers prevent replay attacks
✅ **Control Channel Server** - Robot Pi is SERVER (v1.1 architecture fix)
✅ **Bidirectional Channels** - Control (Base→Robot), Telemetry (Robot→Base), Video (Robot→Base)
✅ **Video HTTP Endpoint** - MJPEG streaming at `http://localhost:5004/video`
✅ **Heartbeat RTT Measurement** - Ping/pong with timestamp tracking

### Safety Features
✅ **E-STOP Boot Latched** - Robot boots with E-STOP ENGAGED
✅ **Watchdog Timeout** - 5 seconds without control → E-STOP
✅ **E-STOP SET Semantics** - Never toggle, always explicit engage/clear
✅ **Clear Validation** - Requires confirmation string + fresh control connection
✅ **Control Priority** - Video never blocks control channel
✅ **Fail-Safe** - Any error → E-STOP (disconnect, auth failure, decode error)

### Robot Pi Components
✅ **Video Capture** - 3× ELP USB cameras, MJPEG encoding, switchable
✅ **Camera Health Monitoring** - Exponential backoff recovery (2s → 30s max)
✅ **Sensor Reader** - BNO085 IMU (quaternion, accel, gyro) + BMP388 (pressure, altitude)
✅ **Actuator Controller** - 4× Pololu Motoron (7 motors) + 1 PWM servo
✅ **E-STOP Debounce** - 300ms debounce window for emergency_status events
✅ **Telemetry Sender** - 10 Hz JSON telemetry with RTT tracking
✅ **Mock Mode** - Runs without hardware for testing

### Base Pi Components
✅ **Control Sender** - HMAC-authenticated TCP client to Robot Pi
✅ **Telemetry Receiver** - TCP server, receives authenticated telemetry @ 10 Hz
✅ **Video Receiver** - TCP server, receives unauthenticated MJPEG stream
✅ **Video HTTP Server** - Endpoints: `/video`, `/frame`, `/health` on port 5004
✅ **Auto-reconnect** - Resilient reconnection with configurable delays
✅ **Status Monitoring** - Comprehensive health checks

### Stress Testing Framework
✅ **26+ Tests** across 5 phases (Phases 2, 6, 1.2, 4, 3, 9)
✅ **Fault Injection** - 8 tests for malformed payloads, HMAC failures, replay attacks
✅ **E-STOP Verification** - 6 tests for watchdog, disconnect, clear validation
✅ **Network Stress** - 7 tests for packet loss, latency, blackout, jitter
✅ **Reconnect Stress** - 3 tests for rapid disconnect, memory leak detection
✅ **Load Stress** - 2 tests for control flood, concurrent channels
✅ **Unified Runner** - JSON report generation for CI/CD
✅ **Quick Mode** - 15-minute test suite for rapid validation

### Production Ready
✅ **Systemd Services** - Auto-start on boot, restart on failure
✅ **Hardened Services** - NoNewPrivileges, ProtectSystem, MemoryMax, etc.
✅ **Environment Configuration** - PSK, ports, timeouts via environment variables
✅ **Comprehensive Logging** - Structured logging with configurable levels
✅ **Error Handling** - Graceful degradation and recovery
✅ **Documentation** - Complete READMEs, integration guide, quick reference

---

## 🔌 Hardware Support

### Sensors (I2C)
- **Adafruit BNO085** - 9-DOF IMU (0x4A)
  - Quaternion orientation
  - Linear acceleration
  - Angular velocity
  - 100ms read rate

- **Adafruit BMP388** - Precision barometer (0x77)
  - Atmospheric pressure
  - Altitude estimation
  - Temperature
  - 100ms read rate

### Actuators
- **4× Pololu Motoron M2H18v20** - Motor controllers (0x10-0x13)
  - 8 motor channels (7 active)
  - I2C control @ 400 kHz
  - Current sensing
  - Speed range: -800 to +800

- **1× Servo** - PWM control
  - GPIO 12 (hardware PWM)
  - 50 Hz, 2.5-12.5% duty cycle
  - Position: 0.0 (closed) to 1.0 (open)

### Cameras
- **3× ELP USB Camera** - Sony IMX323, 1080P
  - Devices: /dev/video0, /dev/video2, /dev/video4
  - Stream: 640×480 @ 10fps, JPEG quality 60
  - Switchable active camera
  - MJPEG encoding
  - Exponential backoff health monitoring

### Network
- **ALFA HaLow-R** (or compatible) - 802.11ah wireless bridge
  - 902-928 MHz ISM band
  - Range: ~1 km line-of-sight
  - Bandwidth: 150 kbps - 15 Mbps
  - Ethernet interface (100 Mbps)

---

## 📡 Communication Protocol

### Control Channel (Base → Robot, TCP:5001)
**Architecture:** Robot Pi is SERVER, Base Pi is CLIENT
**Format:** HMAC-SHA256 authenticated framing
**Frame:** `length(2B) + seq(8B) + hmac(32B) + payload`
**Priority:** Highest
**Events:** emergency_stop, clamp_close, clamp_open, start_camera, ping, height_update, force_update, input_event

### Telemetry Channel (Robot → Base, TCP:5003)
**Architecture:** Base Pi is SERVER, Robot Pi is CLIENT
**Format:** HMAC-SHA256 authenticated framing
**Rate:** 10 Hz (100ms interval)
**Data:** voltage, height, IMU, barometer, motor currents, E-STOP state, RTT, control age

### Video Channel (Robot → Base, TCP:5002)
**Architecture:** Base Pi is SERVER, Robot Pi is CLIENT
**Format:** Unauthenticated MJPEG stream
**Resolution:** 640×480 @ 10 FPS
**Quality:** JPEG 60
**Backpressure:** Frames dropped if socket blocked

### Video HTTP (Base Pi, HTTP:5004)
**Server:** Base Pi
**Format:** MJPEG stream
**Endpoints:**
- `GET /video` - MJPEG stream (multipart/x-mixed-replace)
- `GET /frame` - Single JPEG frame
- `GET /health` - Health check JSON

---

## 🚀 Deployment Steps

### Prerequisites

1. **Generate PSK (once per deployment)**
   ```bash
   python generate_psk.py
   # OR
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Deploy PSK to both Pis**
   ```bash
   # Both Pis
   sudo mkdir -p /etc/serpent
   sudo chmod 700 /etc/serpent
   echo "YOUR_64_CHAR_PSK" | sudo tee /etc/serpent/psk
   sudo chmod 600 /etc/serpent/psk

   # Verify (should output 64)
   cat /etc/serpent/psk | wc -c
   ```

### Robot Pi Installation

```bash
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE
sudo ./scripts/pi_install.sh --robot
sudo ./scripts/pi_enable_services.sh --robot
sudo systemctl status serpent-robot-bridge
```

### Base Pi Installation

```bash
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE
sudo ./scripts/pi_install.sh --base
sudo ./scripts/pi_enable_services.sh --base
sudo systemctl status serpent-base-bridge

# Test video endpoint
curl http://localhost:5004/health
```

### Verification

```bash
# Check services
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge

# Check logs
sudo journalctl -u serpent-robot-bridge -f
sudo journalctl -u serpent-base-bridge -f

# Test video HTTP
curl http://localhost:5004/health
curl http://localhost:5004/frame > test_frame.jpg

# Check connections
ss -tlnp | grep 500
```

---

## 📊 Bandwidth Analysis

Typical usage over HaLow link:

| Component | Bandwidth | Priority | Notes |
|-----------|-----------|----------|-------|
| Control | ~1 kbps | Critical | HMAC-authenticated, low latency |
| Telemetry | ~10 kbps | High | 10 Hz, HMAC-authenticated |
| Video | 200-500 kbps | Medium | Single camera, 640×480, unauthenticated |
| **Total** | **~500 kbps** | - | Well within HaLow capacity |

HaLow link capacity: 150 kbps - 15 Mbps
**Headroom**: 14+ Mbps available for expansion

---

## 🔧 Configuration Highlights

### Environment Variables (Both Pis)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SERPENT_PSK_HEX` | - | **Yes** | 64-char hex PSK for HMAC |
| `SIM_MODE` | `false` | No | Enable simulation mode |
| `ROBOT_PI_IP` | `192.168.100.2` | No | Robot Pi IP address |
| `BASE_PI_IP` | `192.168.100.1` | No | Base Pi IP address |
| `CONTROL_PORT` | `5001` | No | Control channel port |
| `VIDEO_PORT` | `5002` | No | Video channel port |
| `TELEMETRY_PORT` | `5003` | No | Telemetry channel port |
| `VIDEO_HTTP_PORT` | `5004` | No | Video HTTP port (Base Pi only) |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity |

### Robot Pi Key Settings
```bash
CAMERA_WIDTH=640                   # Video resolution
CAMERA_HEIGHT=480
CAMERA_FPS=10                      # Frame rate
CAMERA_QUALITY=60                  # JPEG quality
I2C_BUS=1                          # I2C bus number
SENSOR_READ_INTERVAL=0.1           # 100ms
TELEMETRY_INTERVAL=0.1             # 100ms (10 Hz)
WATCHDOG_TIMEOUT=5.0               # E-STOP timeout
STARTUP_GRACE_PERIOD=30.0          # Boot grace period
CAMERA_RETRY_INITIAL_DELAY=2.0     # Camera health monitoring
CAMERA_RETRY_MAX_DELAY=30.0        # Max backoff delay
```

---

## 🧪 Stress Testing

### Test Coverage

| Phase | Test Type | Tests | Duration | Status |
|-------|-----------|-------|----------|--------|
| 2 | Fault Injection | 8 | 2 min | ✅ Implemented |
| 6 | E-STOP Verification | 6 | 3-5 min | ✅ Implemented |
| 1.2 | Network Stress (Sim) | 7 | 5-20 min | ✅ Implemented |
| 4 | Reconnect Stress | 3 | 10-30 min | ✅ Implemented |
| 3 | Load Stress | 2 | 5-60 min | ✅ Implemented |
| 9 | Unified Runner | 1 | 15+ min | ✅ Implemented |
| **Total** | **All Phases** | **26+** | **15-120 min** | **✅ Production Ready** |

### Quick Test

```bash
# Set PSK
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Run quick stress suite (15 min)
pip install pytest psutil
python scripts/run_stress_suite.py --quick

# Run full stress suite (2+ hours)
python scripts/run_stress_suite.py --phase all --duration 120
```

### Pass Criteria

✅ **Fault Injection:** All malformed payloads rejected or trigger E-STOP
✅ **E-STOP:** All triggers engage E-STOP, clear validation works
✅ **Network:** E-STOP on blackout/high latency, survives packet loss
✅ **Reconnect:** All cycles complete, memory growth < 50 MB
✅ **Load:** Commands sent (>80%), telemetry received (>50%), no crash

---

## 📈 Performance Expectations

| Metric | Target | Typical | Notes |
|--------|--------|---------|-------|
| Control Latency | < 50ms | 15-30ms | Base → Robot command time |
| Telemetry Rate | 10 Hz | 10 Hz | 100ms interval |
| Video Frame Rate | 10 fps | 8-10 fps | May vary with link quality |
| Link RTT | < 100ms | 15-50ms | HaLow round-trip time |
| Video Bandwidth | 200-500 kbps | 300-400 kbps | 640×480, JPEG 60 |
| CPU Usage (Robot) | < 50% | 25-35% | Pi 4 with 3 cameras |
| CPU Usage (Base) | < 25% | 10-15% | Video receive + HTTP serve |

---

## 🛡️ Safety Invariants (Immutable)

| Constant | Value | Cannot Override |
|----------|-------|-----------------|
| `WATCHDOG_TIMEOUT_S` | `5.0` | ✅ Immutable |
| `STARTUP_GRACE_S` | `30.0` | ✅ Immutable |
| `ESTOP_CLEAR_MAX_AGE_S` | `1.5` | ✅ Immutable |
| `ESTOP_CLEAR_CONFIRM` | `"ESTOP_CLEAR_CONFIRM"` | ✅ Immutable |
| `HEARTBEAT_INTERVAL_S` | `1.0` | ✅ Immutable |

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main project overview, architecture, deployment |
| `QUICK_REFERENCE.md` | Commands, troubleshooting, quick reference |
| `PROJECT_SUMMARY.md` | This file - project summary |
| `SAFETY_HARDENING.md` | Safety architecture and hardening |
| `STRESS_TESTING_SUMMARY.md` | Stress testing implementation summary |
| `STRESS_TESTING_QUICKREF.md` | Stress testing quick reference |
| `tests/STRESS_TESTING.md` | Comprehensive stress testing guide |
| `base_pi/README.md` | Base Pi component documentation |
| `robot_pi/README.md` | Robot Pi component documentation |

---

## 🎯 Key Changes in v1.1

1. **Control Channel Architecture** - Robot Pi is now SERVER (not client)
2. **Video HTTP Endpoint** - MJPEG streaming at `http://localhost:5004/video`
3. **RTT Measurement** - Ping/pong heartbeat with timestamp tracking
4. **Camera Health** - Exponential backoff recovery for failed cameras (2s → 30s max)
5. **E-STOP Debounce** - 300ms debounce window for emergency_status events
6. **Stress Testing** - 26+ tests across 5 phases with CI/CD integration

---

## 🏆 Project Achievements

✅ Complete HMAC-authenticated communication system over HaLow
✅ Real-time video streaming with switchable cameras and health monitoring
✅ High-frequency telemetry (10 Hz) with RTT tracking
✅ Robust safety system with dual watchdogs and E-STOP boot latch
✅ Production-ready with systemd services and hardening
✅ Comprehensive stress testing framework with 26+ tests
✅ Video HTTP endpoint for browser/client streaming
✅ Camera health monitoring with exponential backoff
✅ E-STOP debounce for reliable emergency handling
✅ Configurable via environment variables
✅ Auto-reconnect and graceful degradation
✅ Mock mode for testing without hardware
✅ CI/CD integration with JSON report generation

---

## 🤖 System Architecture Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                        Operator Station                        │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │             Base Pi HaLow Bridge (v1.1)                  │ │
│  │                                                          │ │
│  │  • Control Sender (TCP CLIENT → Robot Pi:5001)          │ │
│  │  • Telemetry Receiver (TCP SERVER :5003)                │ │
│  │  • Video Receiver (TCP SERVER :5002)                    │ │
│  │  • Video HTTP Server (HTTP SERVER :5004)                │ │
│  │  • HMAC-SHA256 framing with PSK                         │ │
│  │  • Heartbeat ping/pong with RTT tracking                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            │                                   │
│                            │ TCP (5001, 5002, 5003)            │
└────────────────────────────┼───────────────────────────────────┘
                             │
                             │
                   ┌─────────▼──────────┐
                   │  HaLow Router A    │  Access Point Bridge
                   │  192.168.100.1     │  902-928 MHz
                   └─────────┬──────────┘
                             │
                             │ ~~~~ 802.11ah Wireless ~~~~
                             │ Range: ~1 km
                             │ Bandwidth: 150 kbps - 15 Mbps
                             │
                   ┌─────────▼──────────┐
                   │  HaLow Router B    │  Station Bridge
                   │  192.168.100.2     │  902-928 MHz
                   └─────────┬──────────┘
                             │
                             │ TCP (5001, 5002, 5003)
                             │
┌────────────────────────────▼───────────────────────────────────┐
│                          Robot                                 │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │             Robot Pi HaLow Bridge (v1.1)                 │ │
│  │                                                          │ │
│  │  • Control Receiver (TCP SERVER :5001) ← NEW IN v1.1    │ │
│  │  • Telemetry Sender (TCP CLIENT → Base Pi:5003)         │ │
│  │  • Video Sender (TCP CLIENT → Base Pi:5002)             │ │
│  │  • Video Capture (3× cameras, health monitoring)        │ │
│  │  • Sensor Reader (BNO085 IMU, BMP388 barometer)         │ │
│  │  • Actuator Controller (4× Motoron, 1× servo)           │ │
│  │  • E-STOP System (boot latched, watchdog, debounce)     │ │
│  │  • HMAC-SHA256 framing with PSK                         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            │                                   │
│         ┌──────────────────┼────────────────────┐             │
│         │                  │                    │             │
│    ┌────▼───┐         ┌───▼────┐          ┌────▼────┐        │
│    │ 3× USB │         │ I2C    │          │ I2C     │        │
│    │ Cameras│         │ BNO085 │          │ BMP388  │        │
│    │        │         │ IMU    │          │ Baro    │        │
│    └────────┘         └────────┘          └─────────┘        │
│                                                                │
│              ┌──────────────────────────────────┐             │
│              │  4× Motoron M2H18v20 (I2C)      │             │
│              │  • 7 motors (0x10-0x13)         │             │
│              │  • 1 servo (GPIO 12)            │             │
│              └──────────────────────────────────┘             │
└───────────────────────────────────────────────────────────────┘
```

---

## 🎓 Learning Resources

- **Pololu Motoron Library**: https://github.com/pololu/motoron-python
- **Adafruit BNO08x**: https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085
- **Adafruit BMP3XX**: https://learn.adafruit.com/adafruit-bmp388-bmp390-bmp3xx
- **OpenCV Python**: https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html
- **HMAC Authentication**: https://en.wikipedia.org/wiki/HMAC
- **802.11ah (HaLow)**: https://en.wikipedia.org/wiki/IEEE_802.11ah

---

## 🎉 Conclusion

The Pi HaLow Bridge v1.1 is a complete, production-ready, stress-tested communication system for long-range wireless robot control. It provides:

- **HMAC-authenticated control** with replay protection
- **Real-time telemetry** at 10 Hz with RTT tracking
- **Live video streaming** from 3 switchable cameras with health monitoring
- **Fail-safe E-STOP system** with boot latch, watchdog, and debounce
- **Long-range wireless** via HaLow (~1 km range)
- **Video HTTP endpoint** for browser/client streaming
- **Comprehensive stress testing** with 26+ tests across 5 phases
- **Production deployment** with systemd services and hardening
- **CI/CD integration** with JSON report generation

**Ready to deploy!** 🚀🤖

For setup instructions, see **README.md**.
For quick reference, see **QUICK_REFERENCE.md**.
For stress testing, see **tests/STRESS_TESTING.md**.
For troubleshooting, check component READMEs.

---

**GitHub Repository**: https://github.com/Steyn555247/PI-HALOW-BRIDGE
**Version**: 1.1
**Last Updated**: 2026-01-29
**Status**: Production Ready

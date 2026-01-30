# Pi HaLow Bridge

**Safety-critical wireless communication bridge for Serpent Robotics rope-climbing robots.**

Provides HMAC-authenticated control, telemetry, and video streaming between operator station and robot over ALFA HaLow-R 802.11ah wireless links.

[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%204-green.svg)](https://www.raspberrypi.org/)

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Safety Invariants](#safety-invariants)
- [Features](#features)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Testing](#testing)
- [Stress Testing](#stress-testing)
- [Troubleshooting](#troubleshooting)
- [Protocol Specifications](#protocol-specifications)
- [Hardware](#hardware)

---

## 🚀 Quick Start

### Windows/Linux/macOS Simulation (Development)

```bash
# Install dependencies
pip install -r robot_pi/requirements.txt
pip install -r base_pi/requirements.txt

# Generate and set PSK
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Run simulation (both bridges on localhost)
python scripts/run_sim.py

# In another terminal, view video stream
curl http://localhost:5004/video > stream.mjpeg
```

### Raspberry Pi Deployment

```bash
# On both Pis: Clone repository
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE

# Robot Pi
sudo ./scripts/pi_install.sh --robot
sudo ./scripts/pi_enable_services.sh --robot

# Base Pi
sudo ./scripts/pi_install.sh --base
sudo ./scripts/pi_enable_services.sh --base

# Verify
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge
```

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────┐         HaLow Link          ┌─────────────────────────────┐
│   BASE PI                   │◄──────────────────────────►│   ROBOT PI                  │
│   (Operator Station)        │                             │   (On Robot)                │
│                             │                             │                             │
│ ┌─────────────────────────┐ │    Control (TCP:5001)      │ ┌─────────────────────────┐ │
│ │ Control Forwarder       │─┼────────────────────────────┼─│ Control Server          │ │
│ │ (CLIENT)                │ │    HMAC-SHA256 + Replay    │ │ (SERVER)                │ │
│ │ - Connects to Robot     │ │    Protection              │ │ - Accepts from Base     │ │
│ │ - Sends commands        │ │    Heartbeat ping/pong     │ │ - Processes commands    │ │
│ └─────────────────────────┘ │                             │ └─────────────────────────┘ │
│                             │                             │           │                 │
│ ┌─────────────────────────┐ │    Telemetry (TCP:5003)    │ ┌─────────▼───────────────┐ │
│ │ Telemetry Receiver      │◄┼────────────────────────────┼─│ Telemetry Sender        │ │
│ │ (SERVER)                │ │    HMAC-SHA256             │ │ (CLIENT)                │ │
│ │ - Listens for Robot     │ │    100ms interval          │ │ - Connects to Base      │ │
│ │ - Receives telemetry    │ │    Includes RTT             │ │ - Sends status          │ │
│ └─────────────────────────┘ │                             │ └─────────────────────────┘ │
│                             │                             │                             │
│ ┌─────────────────────────┐ │    Video (TCP:5002)        │ ┌─────────────────────────┐ │
│ │ Video Receiver          │◄┼────────────────────────────┼─│ Video Capture           │ │
│ │ (SERVER)                │ │    MJPEG (unauth)          │ │ (CLIENT)                │ │
│ │ - Listens for Robot     │ │    640x480@10fps           │ │ - Connects to Base      │ │
│ │ - Receives JPEG frames  │ │    Backpressure handling   │ │ - Captures from 3 cams  │ │
│ └─────────────────────────┘ │                             │ └─────────────────────────┘ │
│           │                 │                             │           │                 │
│ ┌─────────▼───────────────┐ │                             │ ┌─────────▼───────────────┐ │
│ │ Video HTTP Server       │ │                             │ │ Actuator Controller     │ │
│ │ - MJPEG stream: :5004   │ │                             │ │ - 7 active motors       │ │
│ │ - /video, /frame, /health│ │                             │ │ - 1 servo               │ │
│ └─────────────────────────┘ │                             │ │ - E-STOP latched boot   │ │
│           │                 │                             │ └─────────────────────────┘ │
│     Socket.IO               │                             │           │                 │
│           │                 │                             │ ┌─────────▼───────────────┐ │
│           ▼                 │                             │ │ Sensor Reader           │ │
│ ┌─────────────────────────┐ │                             │ │ - BNO085 IMU            │ │
│ │ serpent_backend         │ │                             │ │ - BMP388 Barometer      │ │
│ │ - TrimUI controller     │ │                             │ └─────────────────────────┘ │
│ │ - Web UI                │ │                             │                             │
│ └─────────────────────────┘ │                             │                             │
└─────────────────────────────┘                             └─────────────────────────────┘
```

### Control Channel Architecture (IMPORTANT)

**Robot Pi is the CONTROL SERVER** (changed in v1.1):
- Robot Pi runs TCP server on port 5001
- Base Pi connects as client to Robot Pi
- This ensures Robot Pi controls connection lifecycle
- Prevents control socket conflicts and port exhaustion

### Data Flow

| Channel    | Direction      | Protocol | Auth         | Priority | Rate      |
|------------|----------------|----------|--------------|----------|-----------|
| Control    | Base → Robot   | TCP:5001 | HMAC-SHA256  | HIGHEST  | On demand |
| Telemetry  | Robot → Base   | TCP:5003 | HMAC-SHA256  | HIGH     | 10 Hz     |
| Video      | Robot → Base   | TCP:5002 | None         | LOWEST   | 10 FPS    |
| Video HTTP | Base → Browser | HTTP:5004| None         | LOW      | On demand |

---

## 🛡️ Safety Invariants

**These properties are NON-NEGOTIABLE. Any violation is a critical bug.**

### A. E-STOP Boot Latched
- Robot boots with E-STOP **ENGAGED** (fail-safe default)
- No automatic clearing - requires explicit operator command with confirmation
- All actuators stopped until E-STOP is manually cleared
- E-STOP state persists across disconnects

### B. Watchdog Timeout (5 seconds)
- If no valid authenticated control for **5.0 seconds** → E-STOP engages
- Works even if control connection was never established
- 30-second grace period on startup, then watchdog strictly enforced
- Watchdog runs in main thread (not daemon) to prevent bypass

### C. E-STOP SET Semantics (Not Toggle)
- Commands use explicit `engage=true/false`, **NEVER toggle**
- Watchdogs can only **ENGAGE**, never clear
- Clear requires:
  - Active control connection
  - Control age < 1.5 seconds
  - Exact confirm string: `"ESTOP_CLEAR_CONFIRM"`
  - Valid PSK authentication

### D. HMAC Authentication Required
- All control and telemetry messages signed with HMAC-SHA256
- 64-character hex pre-shared key (PSK) required on both Pis
- Replay protection via monotonic sequence numbers (uint64)
- Malformed/unauthenticated/replayed messages → E-STOP immediately

### E. Control Channel Priority
- Video **MUST NOT** starve control or telemetry channels
- Video uses non-blocking send with timeout (0.5s)
- Video frames dropped if socket blocked (backpressure handling)
- Control and telemetry have dedicated sockets and threads

### F. Fail-Safe on All Errors
- Buffer overflow → E-STOP
- JSON decode error → E-STOP
- HMAC verification failure → E-STOP
- Replay attack detected → E-STOP
- Connection lost → E-STOP (within watchdog timeout)
- Any exception in safety-critical path → E-STOP

### G. Immutable Safety Constants
- Safety timeout values defined in `common/constants.py`
- Cannot be overridden by environment variables
- Compile-time constants enforced by code structure

---

## ✨ Features

### Core Features
- ✅ HMAC-SHA256 authenticated control commands
- ✅ Replay attack prevention (monotonic sequence numbers)
- ✅ E-STOP boot latched (fail-safe default)
- ✅ Watchdog timeout enforcement (5s)
- ✅ Three independent channels (control, telemetry, video)
- ✅ Simulation mode for Windows/Linux/macOS development
- ✅ Socket.IO integration with serpent_backend

### Advanced Features (v1.1+)
- ✅ **Heartbeat RTT Measurement** - Ping/pong with timestamp tracking
- ✅ **Video HTTP Endpoint** - MJPEG streaming at `http://<base-pi>:5004/video`
- ✅ **Camera Health Monitoring** - Exponential backoff recovery for failed cameras
- ✅ **E-STOP Debounce** - 300ms debounce for emergency_status events
- ✅ **Control Server Architecture** - Robot Pi runs control server (not client)
- ✅ **Video Frame Recovery** - Automatic camera recovery with backoff (2s → 30s max)
- ✅ **Comprehensive Stress Testing** - 26+ tests across 5 phases

### Robustness Features
- ✅ Automatic reconnection with exponential backoff
- ✅ Bounded video buffer (prevents OOM)
- ✅ SO_REUSEADDR + SO_EXCLUSIVEADDRUSE (Windows socket cleanup)
- ✅ Thread-safe sequence counters
- ✅ Periodic status logging (JSON structured logs)
- ✅ Memory leak detection in stress tests

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| `SERPENT_PSK_HEX` | - | 64-char hex PSK for authentication | **Yes** |
| `SIM_MODE` | `false` | Enable simulation (mock hardware) | No |
| `BASE_PI_IP` | `192.168.100.1` | Base Pi IP address | No |
| `ROBOT_PI_IP` | `192.168.100.2` | Robot Pi IP address | No |
| `CONTROL_PORT` | `5001` | Control channel port | No |
| `VIDEO_PORT` | `5002` | Video channel port | No |
| `TELEMETRY_PORT` | `5003` | Telemetry channel port | No |
| `VIDEO_HTTP_PORT` | `5004` | Video HTTP server port (Base Pi only) | No |
| `VIDEO_HTTP_ENABLED` | `true` | Enable Video HTTP server | No |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) | No |

### Safety Constants (Immutable)

These values are defined in `common/constants.py` and **CANNOT** be overridden:

| Constant | Value | Purpose |
|----------|-------|---------|
| `WATCHDOG_TIMEOUT_S` | `5.0` | Seconds without control before E-STOP |
| `STARTUP_GRACE_S` | `30.0` | Startup grace period before watchdog |
| `ESTOP_CLEAR_MAX_AGE_S` | `1.5` | Max control age to allow E-STOP clear |
| `ESTOP_CLEAR_CONFIRM` | `"ESTOP_CLEAR_CONFIRM"` | Required confirmation string |
| `HEARTBEAT_INTERVAL_S` | `1.0` | Heartbeat ping interval |
| `MAX_FRAME_SIZE` | `16384` | Max authenticated frame size (16 KB) |
| `MAX_VIDEO_BUFFER` | `262144` | Max video buffer size (256 KB) |

---

## 🔐 PSK Generation and Deployment

### Generate PSK

```bash
# Method 1: Use provided script
python generate_psk.py

# Method 2: Manual
python3 -c "import secrets; print(secrets.token_hex(32))"

# Output: 64 hex characters (e.g., a1b2c3d4...)
```

### Deploy to Raspberry Pis

On **BOTH** Pis, create the PSK configuration:

```bash
# Create secure directory
sudo mkdir -p /etc/serpent
sudo chmod 700 /etc/serpent

# Save PSK (MUST be identical on both Pis!)
echo "YOUR_64_CHAR_HEX_PSK_HERE" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk

# Verify
cat /etc/serpent/psk | wc -c  # Should output 64
```

**IMPORTANT:** The PSK must be exactly the same on both Pis. Use copy/paste to ensure no typos.

### Automatic Deployment

The `pi_install.sh` script handles PSK deployment automatically:

```bash
# Robot Pi
sudo ./scripts/pi_install.sh --robot

# Base Pi
sudo ./scripts/pi_install.sh --base

# Follow prompts to enter PSK
```

---

## 🚢 Deployment

### Prerequisites

**Both Pis:**
- Raspberry Pi 4 (recommended) or Pi 3B+
- Raspberry Pi OS (Bullseye or later)
- Python 3.8 or later
- Network connectivity to each other (via HaLow or Ethernet for testing)

**Robot Pi Only:**
- 3× USB cameras (ELP or compatible)
- I2C devices: BNO085 IMU, BMP388 Barometer
- Motoron motor controllers (up to 4× M2H18v20)
- Servo on GPIO 12

### Robot Pi Setup

```bash
# Clone repository
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE

# Install and configure
sudo ./scripts/pi_install.sh --robot

# Enable and start service
sudo ./scripts/pi_enable_services.sh --robot

# Check status
sudo systemctl status serpent-robot-bridge
sudo journalctl -u serpent-robot-bridge -f
```

### Base Pi Setup

```bash
# Clone repository
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE

# Install and configure
sudo ./scripts/pi_install.sh --base

# Enable and start service
sudo ./scripts/pi_enable_services.sh --base

# Check status
sudo systemctl status serpent-base-bridge
sudo journalctl -u serpent-base-bridge -f

# Test video HTTP endpoint
curl http://localhost:5004/health
curl http://localhost:5004/frame > test_frame.jpg
```

### Verify Deployment

```bash
# Check service status
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge

# View logs
sudo journalctl -u serpent-robot-bridge -f
sudo journalctl -u serpent-base-bridge -f

# Check connections
ss -tlnp | grep 500  # Should show ports 5001, 5002, 5003, 5004

# Test video stream (Base Pi)
curl http://localhost:5004/health
# Should return: {"status": "ok", "video_connected": true, ...}
```

---

## 🧪 Testing

### Unit Tests

```bash
# Run all unit tests
python scripts/test_all.py

# Run specific test module
python scripts/test_all.py framing
python scripts/test_all.py estop
python scripts/test_all.py safety_constants

# Verbose output
python scripts/test_all.py -v
```

### Simulation Mode (Development)

```bash
# Set PSK
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Start full simulation (both bridges on localhost)
python scripts/run_sim.py

# Start only Robot Pi
python scripts/run_sim.py --robot-only

# Start only Base Pi
python scripts/run_sim.py --base-only

# View video stream (while sim is running)
curl http://localhost:5004/video > stream.mjpeg
curl http://localhost:5004/frame > frame.jpg
curl http://localhost:5004/health
```

---

## 🔬 Stress Testing

Comprehensive stress testing framework with 26+ tests across 5 phases.

### Quick Stress Test (15 minutes)

```bash
# Install test dependencies
pip install pytest psutil

# Set PSK
export SERPENT_PSK_HEX=$(python -c "import secrets; print(secrets.token_hex(32))")

# Run quick stress suite
python scripts/run_stress_suite.py --quick
```

### Full Stress Suite (2+ hours)

```bash
# Run all phases with full duration
python scripts/run_stress_suite.py --phase all --duration 120 --report-json results.json
```

### Individual Test Phases

```bash
# Phase 2: Fault Injection (malformed payloads, auth failures)
pytest tests/test_fault_injection.py -v

# Phase 6: E-STOP Verification (triggers, clear validation)
pytest tests/test_estop_triggers.py -v

# Phase 1.2: Network Stress (blackout, latency, packet loss)
python scripts/stress_network_sim.py --test all --quick

# Phase 4: Reconnect Stress (rapid disconnect/reconnect, memory leaks)
python scripts/stress_reconnect.py --test all --cycles 20

# Phase 3: Load Stress (control flood, concurrent channels)
python scripts/stress_load.py --test all --duration 60
```

### Stress Test Coverage

| Phase | Tests | Coverage | Duration |
|-------|-------|----------|----------|
| Phase 2: Fault Injection | 8 tests | Invalid JSON, wrong HMAC, replay attacks, oversized payloads | 2 min |
| Phase 6: E-STOP Verification | 6 tests | Watchdog timeout, disconnect, clear validation | 5 min |
| Phase 1.2: Network Stress | 7 tests | Blackout, high latency, packet loss (50%, 90%), bandwidth collapse | 20 min |
| Phase 4: Reconnect Stress | 3 tests | Rapid disconnect (20 cycles), Robot restart (10 cycles), memory leak detection | 30 min |
| Phase 3: Load Stress | 2 tests | Control flood (100 Hz), concurrent channels | 60 min |
| **Total** | **26 tests** | **Comprehensive safety and robustness verification** | **~2 hours** |

See **[STRESS_TESTING.md](tests/STRESS_TESTING.md)** for complete documentation.

---

## 🔧 Troubleshooting

### E-STOP Won't Clear

**Symptoms:** `clear_estop()` returns `False`, E-STOP remains engaged.

**Causes:**
1. Wrong confirmation string (must be exactly `"ESTOP_CLEAR_CONFIRM"`)
2. Control connection not established or stale (> 1.5 seconds)
3. PSK not configured or mismatched between Pis
4. Control socket disconnected

**Diagnosis:**
```bash
# Check logs for rejection reason
sudo journalctl -u serpent-robot-bridge | grep "REJECTED"
sudo journalctl -u serpent-robot-bridge | grep "CLEAR"

# Check control connection
sudo journalctl -u serpent-robot-bridge | grep "control_connected"

# Check PSK
cat /etc/serpent/psk | wc -c  # Should be 64
```

### No Telemetry Received

**Symptoms:** Base Pi shows no telemetry, `frames_received=0`.

**Causes:**
1. Robot Pi not running or not connected
2. PSK mismatch (HMAC auth failures)
3. Firewall blocking ports
4. Network connectivity issues

**Diagnosis:**
```bash
# Check Robot Pi is sending
sudo journalctl -u serpent-robot-bridge | grep "telemetry"

# Check network connectivity
ping 192.168.100.2  # From Base Pi to Robot Pi
ping 192.168.100.1  # From Robot Pi to Base Pi

# Check ports are listening
ss -tlnp | grep 5003  # Should show Base Pi listening

# Check for auth failures
sudo journalctl -u serpent-base-bridge | grep "HMAC"
```

### Service Won't Start

**Symptoms:** `systemctl start` fails immediately or repeatedly restarts.

**Causes:**
1. Missing PSK configuration
2. Missing Python dependencies
3. Port already in use (orphan process)
4. Missing hardware (cameras, I2C devices) when not in SIM_MODE

**Diagnosis:**
```bash
# Check service status
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge

# Check detailed errors
sudo journalctl -u serpent-*-bridge --since "5 minutes ago" -n 100

# Check PSK
cat /etc/serpent/psk | wc -c  # Should be 64
sudo ls -la /etc/serpent/psk  # Should be 600 permissions

# Check dependencies
pip3 list | grep python-socketio
pip3 list | grep opencv-python

# Check for orphan processes
ps aux | grep halow_bridge
sudo netstat -tlnp | grep 500
```

### Video Not Streaming

**Symptoms:** Video receiver connected but no frames, or HTTP endpoint returns no video.

**Causes:**
1. Cameras not initialized (check `/dev/video*`)
2. Bandwidth exhausted (video drops frames under congestion)
3. Camera encoding failure
4. Video HTTP server not enabled

**Diagnosis:**
```bash
# Check camera devices (Robot Pi)
ls -la /dev/video*
v4l2-ctl --list-devices

# Check video stats in logs
sudo journalctl -u serpent-robot-bridge | grep "VideoCapture"
sudo journalctl -u serpent-robot-bridge | grep "frames_sent\|frames_dropped"

# Test video HTTP endpoint (Base Pi)
curl http://localhost:5004/health
curl -I http://localhost:5004/video
curl http://localhost:5004/frame > test_frame.jpg

# Check video connection
sudo journalctl -u serpent-base-bridge | grep "video_connected"
```

### Port Already in Use

**Symptoms:** `Address already in use` errors, service fails to bind ports.

**Causes:**
1. Orphan process from previous run still holding ports
2. Another service using the same ports

**Solution:**
```bash
# Find processes using ports
sudo netstat -tlnp | grep 500
sudo lsof -i :5001
sudo lsof -i :5002
sudo lsof -i :5003

# Kill orphan processes
sudo pkill -9 -f halow_bridge

# Or kill specific PID
sudo kill -9 <PID>

# Restart service
sudo systemctl restart serpent-robot-bridge
```

### High RTT Latency

**Symptoms:** Telemetry shows `rtt_ms > 500`, control feels sluggish.

**Causes:**
1. Network congestion (HaLow interference, weak signal)
2. Video consuming too much bandwidth
3. CPU overload on either Pi

**Diagnosis:**
```bash
# Check RTT in telemetry
sudo journalctl -u serpent-base-bridge | grep "rtt_ms"

# Check video bandwidth
sudo journalctl -u serpent-robot-bridge | grep "frames_sent\|frames_dropped"

# Check CPU usage
top -b -n 1 | grep halow_bridge

# Check HaLow signal strength (if applicable)
iwconfig wlan0  # Or appropriate interface
```

---

## 📡 Protocol Specifications

### Control Messages (Base Pi → Robot Pi)
**Transport:** TCP port 5001, HMAC-authenticated frames, Base Pi connects to Robot Pi server

**Frame Format:**
```
[4 bytes: payload_len][8 bytes: seq][32 bytes: HMAC][payload]
```

**Payload (JSON):**
```json
{"type": "emergency_stop", "data": {"engage": true, "reason": "operator"}}
{"type": "emergency_stop", "data": {"engage": false, "confirm_clear": "ESTOP_CLEAR_CONFIRM", "reason": "operator"}}
{"type": "ping", "data": {"ts": 1234567890.123, "seq": 1}}
{"type": "clamp_close", "data": {}}
{"type": "clamp_open", "data": {}}
{"type": "start_camera", "data": {"camera_id": 0}}
{"type": "height_update", "data": {"height": 50.0}}
{"type": "force_update", "data": {"force": 30.0}}
{"type": "input_event", "data": {"type": "axis", "index": 0, "value": 0.5}}
```

### Telemetry (Robot Pi → Base Pi)
**Transport:** TCP port 5003, HMAC-authenticated frames, 10 Hz interval (100ms)

**Payload (JSON):**
```json
{
  "voltage": 12.6,
  "height": 45.0,
  "force": 30.0,
  "imu": {
    "quat_w": 0.99,
    "quat_x": 0.01,
    "quat_y": 0.02,
    "quat_z": -0.01,
    "accel_x": 0.1,
    "accel_y": 0.2,
    "accel_z": 9.8
  },
  "barometer": {
    "pressure": 1013.25,
    "altitude": 100.0,
    "temperature": 25.0
  },
  "motor_currents": [0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
  "estop": {
    "engaged": false,
    "reason": "cleared"
  },
  "pong": {
    "ping_ts": 1234567890.123,
    "ping_seq": 1
  },
  "control_age_ms": 50,
  "uptime_s": 3600,
  "timestamp": 1234567890.123
}
```

### Video Stream (Robot Pi → Base Pi)
**Transport:** TCP port 5002, raw MJPEG stream (unauthenticated)

**Format:** Sequential JPEG frames
- Resolution: 640×480 @ 10 FPS (configurable)
- JPEG quality: 60 (configurable)
- Frames delimited by SOI (0xFFD8) and EOI (0xFFD9) markers
- Backpressure: Frames dropped if socket blocked (0.5s timeout)
- Camera auto-recovery with exponential backoff (2s → 30s max)

### Video HTTP API (Base Pi)
**Transport:** HTTP port 5004 (configurable)

**Endpoints:**

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/video` | GET | MJPEG stream (multipart/x-mixed-replace) | Video stream |
| `/frame` | GET | Single JPEG frame | JPEG image |
| `/health` | GET | Video receiver health status | JSON |

**Health Response:**
```json
{
  "status": "ok",
  "video_connected": true,
  "frames_received": 12345
}
```

---

## 🔩 Hardware

### HaLow Link – ALFA HaLow-R

- **Chip:** Morse Micro MM6108
- **Frequency:** 902–928 MHz (US ISM band)
- **Range:** Up to 1 km line-of-sight
- **Data Rate:** 150 kbps – 15 Mbps
- **Interface:** Ethernet (100 Mbps)
- **Topology:** Bridge mode (Router A ↔ Router B)
- **Power:** PoE or USB-C

### Robot Pi Hardware

**Raspberry Pi 4 (Recommended):**
- **Reason:** Better I2C, GPIO, USB bandwidth, CPU performance
- **RAM:** 4 GB minimum, 8 GB recommended
- **Storage:** 32 GB microSD or SSD (for data recording)

**Cameras:**
- **Model:** 3× ELP USB Camera (Sony IMX323, 1080P)
- **Interface:** USB 2.0/3.0
- **Resolution:** 640×480 @ 10 FPS (configured)
- **Encoding:** MJPEG hardware encoding

**Sensors (I2C):**
- **IMU:** Adafruit BNO085 (I2C address 0x4A)
- **Barometer:** Adafruit BMP388 (I2C address 0x77)
- **I2C Bus:** Bus 1 (default on Pi)

**Actuators:**
- **Motors:** 4× Pololu Motoron M2H18v20 (I2C 0x10-0x13)
  - 7 motors active (addresses configured in `config.py`)
- **Servo:** 1× PWM servo on GPIO 12 (clamp)
  - Frequency: 50 Hz (default)
  - Pulse width: 1000-2000 μs

### Base Pi Hardware

**Raspberry Pi 4 (Recommended):**
- **Reason:** Better network performance, USB bandwidth for peripherals
- **RAM:** 2 GB minimum, 4 GB recommended
- **Storage:** 16 GB microSD minimum

**No special hardware required** (acts as network bridge)

---

## 📁 File Structure

```
pi_halow_bridge/
├── common/                         # Shared modules
│   ├── __init__.py
│   ├── constants.py                # Safety constants (IMMUTABLE)
│   └── framing.py                  # HMAC-SHA256 authenticated framing
│
├── robot_pi/                       # Robot Pi code
│   ├── __init__.py
│   ├── config.py                   # Robot Pi configuration
│   ├── halow_bridge.py             # Main coordinator (control SERVER)
│   ├── actuator_controller.py     # Motoron + Servo control (E-STOP latched)
│   ├── sensor_reader.py            # BNO085 IMU + BMP388 Barometer
│   ├── video_capture.py            # USB camera capture (with health check)
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Example environment variables
│   ├── README.md                   # Robot Pi specific docs
│   └── serpent-robot-bridge.service # systemd service
│
├── base_pi/                        # Base Pi code
│   ├── __init__.py
│   ├── config.py                   # Base Pi configuration
│   ├── halow_bridge.py             # Main coordinator (with Video HTTP)
│   ├── control_forwarder.py        # Control client (connects to Robot)
│   ├── telemetry_receiver.py       # Telemetry server (receives from Robot)
│   ├── video_receiver.py           # Video server (receives from Robot)
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Example environment variables
│   ├── README.md                   # Base Pi specific docs
│   └── serpent-base-bridge.service # systemd service
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── test_framing.py             # HMAC framing tests
│   ├── test_estop.py               # E-STOP logic tests
│   ├── test_safety_constants.py    # Safety constant validation
│   ├── test_fault_injection.py     # Fault injection tests (26 tests)
│   ├── test_estop_triggers.py      # E-STOP trigger tests (integration)
│   ├── STRESS_TESTING.md           # Comprehensive stress testing guide
│   └── __pycache__/                # (gitignored)
│
├── scripts/                        # Deployment & testing scripts
│   ├── run_sim.py                  # Windows/Linux/macOS simulation
│   ├── test_all.py                 # Run all unit tests
│   ├── pi_install.sh               # Pi installation script
│   ├── pi_enable_services.sh       # Enable systemd services
│   ├── pi_torture.sh               # Network torture tests (requires root)
│   ├── run_stress_suite.py         # Unified stress test runner
│   ├── stress_network_sim.py       # Network stress tests (sim mode)
│   ├── stress_reconnect.py         # Reconnect stress tests
│   └── stress_load.py              # Load & throughput stress tests
│
├── generate_psk.py                 # PSK generation utility
├── .gitignore                      # Git ignore rules
├── README.md                       # This file
├── QUICK_REFERENCE.md              # Quick command reference
├── PROJECT_SUMMARY.md              # Project overview
├── INTEGRATION.md                  # Integration with serpent_backend
├── SAFETY_HARDENING.md             # Safety audit and hardening
├── STRESS_TESTING_SUMMARY.md       # Stress testing implementation summary
└── STRESS_TESTING_QUICKREF.md      # Stress testing quick reference
```

---

## 🔒 Security Considerations

1. **PSK Security:**
   - PSK provides authentication and prevents unauthorized control
   - Store PSK securely with 600 permissions (`/etc/serpent/psk`)
   - Use a cryptographically secure random PSK (64 hex chars)
   - Change PSK if compromised

2. **Network Isolation:**
   - HaLow link should be isolated network (no internet access)
   - Firewall rules on Pis to allow only necessary ports
   - Consider VPN or additional encryption for sensitive deployments

3. **Video Not Authenticated:**
   - Video stream is not authenticated (performance trade-off)
   - Video data cannot cause actuation, so this is acceptable
   - Video is lowest priority and can be dropped under load

4. **Physical Access:**
   - Anyone with physical access to Pis can extract PSK from filesystem
   - Protect physical access to Pis (locked enclosure)
   - Consider hardware security modules (HSM) for high-security deployments

5. **Replay Protection:**
   - Sequence numbers prevent replay attacks
   - Sequence numbers are monotonically increasing (uint64)
   - Old frames are rejected automatically

---

## 📊 Performance Benchmarks

### Typical Performance (Raspberry Pi 4, HaLow Link)

| Metric | Value | Notes |
|--------|-------|-------|
| Control Latency (RTT) | 20-50 ms | Measured via ping/pong |
| Telemetry Rate | 10 Hz | 100ms interval |
| Video Frame Rate | 10 FPS | 640×480 MJPEG |
| Video Latency | 100-200 ms | End-to-end (camera to browser) |
| Control Throughput | 100+ commands/s | Stress test verified |
| Memory Usage (Robot Pi) | 80-120 MB | Stable, no leaks detected |
| Memory Usage (Base Pi) | 60-90 MB | Stable, no leaks detected |
| CPU Usage (Robot Pi) | 15-30% | Single core, idle robot |
| CPU Usage (Base Pi) | 5-15% | Single core, no backend |

### Stress Test Results

| Test | Result | Details |
|------|--------|---------|
| Control Flood (100 Hz, 60s) | ✅ PASS | 6000 commands sent, >95% delivered |
| Network Blackout (100% loss) | ✅ PASS | E-STOP within 7s, recovery on restore |
| Reconnect Stress (20 cycles) | ✅ PASS | All cycles passed, memory growth <10 MB |
| Concurrent Channels (120s) | ✅ PASS | All channels functional, no deadlock |
| Fault Injection (8 tests) | ✅ PASS | All malformed payloads rejected |

See **[STRESS_TESTING.md](tests/STRESS_TESTING.md)** for complete results.

---

## 📝 Change Log

### v1.1 (2026-01-29) - Stress Testing & Robustness

**Major Changes:**
- ✅ **Control Channel Architecture Fix:** Robot Pi is now control SERVER (not client)
- ✅ **Video HTTP Endpoint:** MJPEG streaming at `http://<base-pi>:5004/video`
- ✅ **Heartbeat RTT Measurement:** Ping/pong with timestamp tracking
- ✅ **Camera Health Monitoring:** Exponential backoff recovery for failed cameras
- ✅ **E-STOP Debounce:** 300ms debounce for emergency_status events
- ✅ **Comprehensive Stress Testing:** 26+ tests across 5 phases

**Improvements:**
- Video camera auto-recovery with exponential backoff (2s → 30s max)
- SO_EXCLUSIVEADDRUSE for Windows socket cleanup
- Periodic INFO logging for control server accept loop
- RTT measurement integrated into telemetry
- Memory leak detection in stress tests
- JSON report generation for CI/CD

**Bug Fixes:**
- Fixed Windows "Address already in use" errors
- Fixed control channel connection refused (architecture mismatch)
- Fixed video frame recovery after camera failures
- Fixed E-STOP event mismatch (emergency_toggle vs emergency_status)

### v1.0 (2026-01-XX) - Initial Release

- HMAC-SHA256 authenticated control commands
- E-STOP boot latched with watchdog timeout
- Three independent channels (control, telemetry, video)
- Simulation mode for development
- Socket.IO integration with serpent_backend
- Basic unit tests and documentation

---

## 🤝 Contributing

This is a proprietary project for Serpent Robotics. External contributions are not accepted at this time.

For internal contributors:
1. Create feature branch from `main`
2. Run all tests: `python scripts/test_all.py`
3. Run stress tests: `python scripts/run_stress_suite.py --quick`
4. Update documentation if adding features
5. Create pull request with detailed description

---

## 📄 License

Proprietary – Serpent Robotics. All rights reserved.

---

## 📞 Support

- **Documentation:** See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) and [STRESS_TESTING.md](tests/STRESS_TESTING.md)
- **Issues:** Internal issue tracker only
- **Contact:** Serpent Robotics team

---

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production Ready (tested in simulation and field)

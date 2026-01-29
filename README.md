# Pi HaLow Bridge

**Safety-critical communication layer for Serpent Robotics rope-climbing robots.**

Bridges control commands from the operator station (via `serpent_backend`) to the
robot over ALFA HaLow-R 802.11ah wireless links, and returns video/telemetry.

---

## Quick Start

### Windows Simulation (Development)

```bash
# Run all tests
python scripts/test_all.py

# Start simulated system (both bridges on localhost)
python scripts/run_sim.py
```

### Raspberry Pi Deployment

```bash
# On each Pi:
./scripts/pi_install.sh           # Install deps, configure PSK
./scripts/pi_enable_services.sh   # Enable and start service
```

---

## Architecture

```
┌─────────────────┐         HaLow Link          ┌─────────────────┐
│   BASE PI       │◄──────────────────────────►│   ROBOT PI      │
│                 │                             │                 │
│ ┌─────────────┐ │    Control (TCP:5001)      │ ┌─────────────┐ │
│ │ Control     │─┼────────────────────────────┼─│ Control     │ │
│ │ Forwarder   │ │    HMAC-SHA256 auth        │ │ Receiver    │ │
│ └─────────────┘ │                             │ └─────────────┘ │
│                 │                             │                 │
│ ┌─────────────┐ │    Telemetry (TCP:5003)    │ ┌─────────────┐ │
│ │ Telemetry   │◄┼────────────────────────────┼─│ Telemetry   │ │
│ │ Receiver    │ │    HMAC-SHA256 auth        │ │ Sender      │ │
│ └─────────────┘ │                             │ └─────────────┘ │
│                 │                             │                 │
│ ┌─────────────┐ │    Video (TCP:5002)        │ ┌─────────────┐ │
│ │ Video       │◄┼────────────────────────────┼─│ Video       │ │
│ │ Receiver    │ │    MJPEG (unauth)          │ │ Capture     │ │
│ └─────────────┘ │                             │ └─────────────┘ │
│                 │                             │                 │
│        ▲        │                             │ ┌─────────────┐ │
│        │        │                             │ │ Actuator    │ │
│  Socket.IO      │                             │ │ Controller  │ │
│        │        │                             │ └─────────────┘ │
│        ▼        │                             │        │        │
│ ┌─────────────┐ │                             │ ┌──────▼──────┐ │
│ │ serpent_    │ │                             │ │ Motoron x4  │ │
│ │ backend     │ │                             │ │ Servo       │ │
│ └─────────────┘ │                             │ │ IMU/Baro    │ │
└─────────────────┘                             └─────────────────┘
```

### Data Flow

| Channel    | Direction      | Protocol | Auth | Priority |
|------------|----------------|----------|------|----------|
| Control    | Base → Robot   | TCP      | HMAC | HIGHEST  |
| Telemetry  | Robot → Base   | TCP      | HMAC | HIGH     |
| Video      | Robot → Base   | TCP      | None | LOWEST   |

---

## Safety Invariants

**These are NON-NEGOTIABLE. The robot must NEVER violate these properties.**

### A. E-STOP Boot Latched
- Robot boots with E-STOP **ENGAGED** (fail-safe default)
- No automatic clearing - requires explicit operator command
- All actuators stopped until E-STOP is cleared

### B. Watchdog Timeout
- If no valid authenticated control for **5 seconds** → E-STOP engages
- Works even if control connection was never established
- 30-second grace period on startup, then watchdog enforced

### C. E-STOP SET Semantics
- Commands use explicit `engage=true/false`, never toggle
- Watchdogs can only **ENGAGE**, never clear
- Clear requires: fresh connection + exact confirm string

### D. Authentication Required
- All control messages signed with HMAC-SHA256
- Pre-shared key (PSK) required on both Pis
- Replay protection via monotonic sequence numbers
- Malformed/unauthenticated messages → E-STOP

### E. Control Priority
- Video **MUST NOT** starve control channel
- Video frames dropped if socket blocked (backpressure)
- Control and telemetry have dedicated channels

### F. Fail-Safe on Errors
- Buffer overflow → E-STOP
- Decode error → E-STOP
- Auth failure → E-STOP
- Disconnect → E-STOP
- Any exception in safety path → E-STOP

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SERPENT_PSK_HEX` | (required) | 64-char hex PSK for authentication |
| `SIM_MODE` | `false` | Enable simulation (mock hardware) |
| `BASE_PI_IP` | `192.168.100.1` | Base Pi IP address |
| `ROBOT_PI_IP` | `192.168.100.2` | Robot Pi IP address |
| `CONTROL_PORT` | `5001` | Control channel port |
| `VIDEO_PORT` | `5002` | Video channel port |
| `TELEMETRY_PORT` | `5003` | Telemetry channel port |
| `LOG_LEVEL` | `INFO` | Logging level |

### Safety Constants (Immutable)

These values are defined in `common/constants.py` and **cannot** be overridden:

| Constant | Value | Purpose |
|----------|-------|---------|
| `WATCHDOG_TIMEOUT_S` | 5.0 | Seconds without control before E-STOP |
| `STARTUP_GRACE_S` | 30.0 | Startup grace period |
| `ESTOP_CLEAR_MAX_AGE_S` | 1.5 | Max control age to allow E-STOP clear |
| `ESTOP_CLEAR_CONFIRM` | `"CLEAR_ESTOP"` | Required confirmation string |

---

## PSK Generation and Deployment

### Generate PSK

```bash
# Method 1: Use provided script
python generate_psk.py

# Method 2: Manual
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Deploy to Pis

On **both** Pis, create the PSK configuration:

```bash
# Create secure directory
sudo mkdir -p /etc/serpent
sudo chmod 700 /etc/serpent

# Save PSK (same value on both Pis!)
echo "YOUR_64_CHAR_HEX_PSK" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk
```

The `pi_install.sh` and `pi_enable_services.sh` scripts handle this automatically.

---

## Deployment

### Robot Pi Setup

```bash
cd pi_halow_bridge
./scripts/pi_install.sh --robot
./scripts/pi_enable_services.sh --robot
```

### Base Pi Setup

```bash
cd pi_halow_bridge
./scripts/pi_install.sh --base
./scripts/pi_enable_services.sh --base
```

### Verify Deployment

```bash
# Check service status
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge

# View logs
sudo journalctl -u serpent-robot-bridge -f
sudo journalctl -u serpent-base-bridge -f
```

---

## Testing

### Unit Tests

```bash
# Run all tests
python scripts/test_all.py

# Run specific test module
python scripts/test_all.py framing
python scripts/test_all.py estop

# Verbose output
python scripts/test_all.py -v
```

### Simulation Mode

```bash
# Start full simulation on localhost
python scripts/run_sim.py

# Start only one side
python scripts/run_sim.py --robot-only
python scripts/run_sim.py --base-only
```

### Torture Tests (Pi only)

```bash
# Requires root and running services
sudo ./scripts/pi_torture.sh

# Quick smoke test
sudo ./scripts/pi_torture.sh --quick
```

---

## Troubleshooting

### E-STOP Won't Clear

**Symptoms:** `clear_estop()` returns `False`, E-STOP remains engaged.

**Causes:**
1. Wrong confirmation string (must be exactly `"CLEAR_ESTOP"`)
2. Control connection not established or stale (> 1.5 seconds)
3. PSK not configured or mismatched

**Diagnosis:**
```bash
# Check logs for rejection reason
sudo journalctl -u serpent-robot-bridge | grep "REJECTED"
```

### No Telemetry Received

**Symptoms:** Base Pi shows no telemetry, `frames_received=0`.

**Causes:**
1. Robot Pi not running or not connected
2. PSK mismatch (auth failures)
3. Firewall blocking ports

**Diagnosis:**
```bash
# Check Robot Pi is sending
sudo journalctl -u serpent-robot-bridge | grep "telemetry"

# Check network connectivity
ping 192.168.100.2  # From Base Pi

# Check ports
ss -tlnp | grep 500
```

### Service Won't Start

**Symptoms:** `systemctl start` fails immediately.

**Causes:**
1. Missing PSK configuration
2. Missing dependencies
3. Port already in use

**Diagnosis:**
```bash
# Check service status
sudo systemctl status serpent-*-bridge

# Check for errors
sudo journalctl -u serpent-*-bridge --since "5 minutes ago"

# Check PSK
cat /etc/serpent/psk | wc -c  # Should be 64 characters
```

### Video Not Streaming

**Symptoms:** Video receiver connected but no frames.

**Causes:**
1. Camera not initialized (check `/dev/video*`)
2. Bandwidth exhausted (video drops under congestion)
3. Encoding failure

**Diagnosis:**
```bash
# Check camera devices on Robot Pi
ls -la /dev/video*

# Check video stats in logs
sudo journalctl -u serpent-robot-bridge | grep "VideoCapture"
```

---

## Log Locations

| Location | Description |
|----------|-------------|
| `/var/log/serpent/robot_pi_bridge.log` | Robot Pi application log |
| `/var/log/serpent/base_pi_bridge.log` | Base Pi application log |
| `journalctl -u serpent-*-bridge` | Systemd journal |

### Healthy Log Patterns

```
# Robot Pi - Healthy
{"event": "status", "control_connected": true, "control_established": true, ...}
{"event": "ESTOP", "action": "CLEARED", ...}

# Base Pi - Healthy
{"event": "status", "backend": "connected", "control": "connected", ...}
```

### Unhealthy Log Patterns

```
# Authentication failure
HMAC verification FAILED for seq=...

# Watchdog triggered
Control timeout (6.2s), engaging E-STOP

# Buffer overflow
Video buffer overflow (300000 > 262144), resetting
```

---

## Hardware

### HaLow Link – ALFA HaLow-R
- **Chip**: Morse Micro MM6108
- **Frequency**: 902–928 MHz (US ISM band)
- **Range**: Up to 1 km line-of-sight
- **Data Rate**: 150 kbps – 15 Mbps
- **Interface**: Ethernet (100 Mbps)
- **Topology**: Bridge mode (Router A ↔ Router B)

### Robot Pi Hardware
- Raspberry Pi 4 (recommended for I2C, GPIO, USB bandwidth)
- **Cameras**: 3× ELP USB Camera (Sony IMX323, 1080P)
- **IMU**: Adafruit BNO085 (I2C 0x4A)
- **Barometer**: Adafruit BMP388 (I2C 0x77)
- **Motors**: 4× Pololu Motoron M2H18v20 (I2C 0x10-0x13, 7 motors active)
- **Servo**: 1× PWM servo (GPIO 12)

---

## File Structure

```
pi_halow_bridge/
├── common/                 # Shared modules
│   ├── __init__.py
│   ├── constants.py        # Safety constants (immutable)
│   └── framing.py          # HMAC-authenticated framing
├── robot_pi/               # Robot Pi code
│   ├── config.py
│   ├── halow_bridge.py     # Main coordinator
│   ├── actuator_controller.py  # Motor/servo control
│   ├── sensor_reader.py    # IMU/barometer
│   ├── video_capture.py    # Camera capture
│   └── serpent-robot-bridge.service
├── base_pi/                # Base Pi code
│   ├── config.py
│   ├── halow_bridge.py     # Main coordinator
│   ├── control_forwarder.py
│   ├── telemetry_receiver.py
│   ├── video_receiver.py
│   └── serpent-base-bridge.service
├── tests/                  # Test suite
│   ├── test_framing.py
│   ├── test_estop.py
│   └── test_safety_constants.py
├── scripts/                # Deployment scripts
│   ├── run_sim.py          # Windows simulation
│   ├── test_all.py         # Run all tests
│   ├── pi_install.sh       # Pi installation
│   ├── pi_enable_services.sh
│   └── pi_torture.sh       # Network torture tests
├── generate_psk.py         # PSK generation utility
├── PATCH_PLAN.md           # Audit findings and fixes
├── SAFETY_HARDENING.md     # Safety documentation
└── README.md               # This file
```

---

## Protocol Specifications

### Control Messages (Base Pi → Robot Pi)
**Transport**: TCP port 5001, authenticated frames

```json
{"type": "emergency_stop", "data": {"engage": true, "reason": "operator"}}
{"type": "emergency_stop", "data": {"engage": false, "confirm_clear": "CLEAR_ESTOP"}}
{"type": "clamp_close", "data": {}}
{"type": "clamp_open", "data": {}}
{"type": "start_camera", "data": {"camera_id": 0}}
{"type": "height_update", "data": {"height": 50.0}}
{"type": "force_update", "data": {"force": 30.0}}
{"type": "input_event", "data": {"type": "axis", "index": 0, "value": 0.5}}
```

### Telemetry (Robot Pi → Base Pi)
**Transport**: TCP port 5003, authenticated frames, 100ms interval

```json
{
  "voltage": 12.6,
  "height": 45.0,
  "force": 30.0,
  "imu": {"quat_w": 0.99, "quat_x": 0.01, ...},
  "barometer": {"pressure": 1013.25, "altitude": 100.0, "temperature": 25.0},
  "motor_currents": [0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
  "estop": {"engaged": false, "reason": "cleared"},
  "control_age_ms": 50,
  "timestamp": 1234567890.123
}
```

### Video Stream (Robot Pi → Base Pi)
**Transport**: TCP port 5002, raw MJPEG (unauthenticated)
- Resolution: 640×480 @ 10 fps
- Format: Sequential JPEG frames (SOI 0xFFD8, EOI 0xFFD9)
- Backpressure: Frames dropped if socket blocked

---

## Security Considerations

1. **PSK Security:** The PSK provides authentication. Keep it secret.
2. **Network Isolation:** HaLow link should be isolated network.
3. **Video Not Authenticated:** Video is not authenticated (performance).
   Video data cannot cause actuation, so this is acceptable.
4. **Physical Access:** Anyone with physical access to Pis can extract PSK.

---

## License

Proprietary – Serpent Robotics

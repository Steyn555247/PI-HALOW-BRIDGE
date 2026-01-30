# Robot Pi HaLow Bridge (v1.1)

Robot Pi component for long-range wireless robot control. Controls actuators (Motoron + servo), reads sensors (IMU + barometer), captures video from 3 USB cameras, and communicates with Base Pi over HaLow.

**Version:** 1.1
**Last Updated:** 2026-01-29

---

## Components

- **config.py** - Configuration and environment variables
- **halow_bridge.py** - Main coordinator (TCP SERVER for control in v1.1)
- **control_receiver.py** - Receives HMAC-authenticated control from Base Pi (TCP server)
- **telemetry_sender.py** - Sends HMAC-authenticated telemetry to Base Pi (TCP client)
- **video_sender.py** - Sends unauthenticated MJPEG stream to Base Pi (TCP client)
- **actuator_controller.py** - Controls 4× Motoron boards (7 motors) + 1 servo with E-STOP system
- **sensor_reader.py** - Reads BNO085 IMU and BMP388 barometer via I2C
- **video_capture.py** - Captures from 3 ELP USB cameras with health monitoring (v1.1)

---

## Architecture (v1.1)

```
Robot Pi (On Robot)
    │
    ├─ Control Receiver (TCP SERVER :5001) ←── Base Pi
    ├─ Telemetry Sender (TCP CLIENT) ──→ Base Pi :5003
    ├─ Video Sender (TCP CLIENT) ──→ Base Pi :5002
    ├─ Actuator Controller (E-STOP + motors + servo)
    ├─ Sensor Reader (I2C: BNO085 + BMP388)
    └─ Video Capture (3× USB cameras with health monitoring)
```

**Important:** In v1.1, Robot Pi is the control SERVER. Robot Pi accepts connections from Base Pi on port 5001.

---

## Hardware

### Actuators
- **4× Pololu Motoron M2H18v20** - I2C addresses 0x10, 0x11, 0x12, 0x13
  - 8 motor channels (2 per board), 7 active
  - I2C bus 1, up to 400 kHz
  - Current sensing
  - Speed range: -800 to +800

- **1× Servo** - GPIO 12 (hardware PWM)
  - 50 Hz PWM
  - Position: 0.0 (closed) to 1.0 (open)

### Sensors
- **Adafruit BNO085** - 9-DOF IMU (I2C address 0x4A)
  - Quaternion orientation
  - Linear acceleration
  - Angular velocity (gyroscope)
  - 100ms read interval

- **Adafruit BMP388** - Precision barometer (I2C address 0x77)
  - Atmospheric pressure
  - Temperature
  - Altitude estimation
  - 100ms read interval

### Cameras
- **3× ELP USB Camera** - Sony IMX323, 1080P
  - Devices: `/dev/video0`, `/dev/video2`, `/dev/video4`
  - Stream resolution: 640×480 @ 10fps
  - JPEG quality: 60
  - Switchable active camera
  - MJPEG encoding
  - **Health monitoring with exponential backoff (v1.1)**

---

## Installation

```bash
cd robot_pi
pip install -r requirements.txt
```

### Dependencies

```
python>=3.7
opencv-python
numpy
adafruit-circuitpython-bno08x
adafruit-circuitpython-bmp3xx
motoron
RPi.GPIO
```

### I2C Setup

Enable I2C on Raspberry Pi:
```bash
sudo raspi-config
# Interface Options -> I2C -> Enable
```

Verify devices:
```bash
sudo i2cdetect -y 1
```

Expected output:
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: 10 11 12 13 -- -- -- -- -- -- -- -- -- -- -- --
...
40: -- -- -- -- -- -- -- -- -- -- 4a -- -- -- -- --
...
70: -- -- -- -- -- -- -- 77
```

### Camera Setup

List available cameras:
```bash
v4l2-ctl --list-devices
```

Verify camera capture:
```bash
ffplay /dev/video0
```

---

## Configuration

Set environment variables or create a `.env` file:

```bash
# PSK (REQUIRED)
SERPENT_PSK_HEX=<64-char-hex-psk>

# Network
BASE_PI_IP=192.168.100.1
CONTROL_PORT=5001
VIDEO_PORT=5002
TELEMETRY_PORT=5003

# Cameras
NUM_CAMERAS=3
CAMERA_0=/dev/video0
CAMERA_1=/dev/video2
CAMERA_2=/dev/video4
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
CAMERA_FPS=10
CAMERA_QUALITY=60
CAMERA_RETRY_INITIAL_DELAY=2.0    # v1.1
CAMERA_RETRY_MAX_DELAY=30.0       # v1.1

# Sensors (I2C)
I2C_BUS=1
BNO085_ADDRESS=0x4A
BMP388_ADDRESS=0x77
SENSOR_READ_INTERVAL=0.1

# Motoron (I2C)
MOTORON_ADDR_0=0x10
MOTORON_ADDR_1=0x11
MOTORON_ADDR_2=0x12
MOTORON_ADDR_3=0x13

# Servo (GPIO PWM)
SERVO_GPIO_PIN=12
SERVO_FREQ=50

# Safety
WATCHDOG_TIMEOUT=5.0
STARTUP_GRACE_PERIOD=30.0
ESTOP_DEBOUNCE_WINDOW_MS=300      # v1.1

# Telemetry
TELEMETRY_INTERVAL=0.1

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/serpent/robot_pi_bridge.log
```

---

## Usage

### Standalone Mode

```bash
python halow_bridge.py
```

### Systemd Service

```bash
sudo cp serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-robot-bridge
sudo systemctl start serpent-robot-bridge
```

Check status:
```bash
sudo systemctl status serpent-robot-bridge
journalctl -u serpent-robot-bridge -f
```

---

## Features

### Control Receiver (v1.1)
- **TCP SERVER** on port 5001 (Robot Pi listens for Base Pi connections)
- HMAC-SHA256 authenticated framing
- Receives control commands from Base Pi
- Responds to heartbeat pings (v1.1)
- Auto-reconnect support

### Telemetry Sender
- **TCP CLIENT** to Base Pi port 5003
- HMAC-SHA256 authenticated framing
- Sends telemetry at 10 Hz (100ms interval)
- Includes E-STOP state, voltage, IMU, barometer, RTT, motor currents

### Video Sender
- **TCP CLIENT** to Base Pi port 5002
- Sends unauthenticated MJPEG stream
- 640×480 @ 10 FPS (configurable)
- Backpressure handling (frames dropped if socket blocked)
- **Camera health monitoring with exponential backoff (v1.1)**

### Actuator Controller
- E-STOP boot latched (fail-safe default)
- E-STOP SET semantics (explicit engage/clear)
- Watchdog timeout (5 seconds without control)
- Thread-safe motor/servo control
- Current sensing on all motors

### Sensor Reader
- BNO085 IMU: Quaternion, accel, gyro @ 100ms
- BMP388 Barometer: Pressure, altitude, temp @ 100ms
- Graceful fallback if sensors unavailable (mock mode)

### Video Capture (v1.1)
- 3 USB cameras, switchable active camera
- MJPEG encoding @ 640×480, 10 FPS
- **Exponential backoff health monitoring**:
  - Initial retry delay: 2 seconds
  - Max retry delay: 30 seconds
  - Backoff multiplier: 2×
  - Auto-recovery when camera restored

---

## Control Commands

Receive control commands from Base Pi via control receiver:

### Emergency Stop

```json
// Engage E-STOP
{
  "type": "emergency_stop",
  "data": {"engage": true, "reason": "operator"},
  "timestamp": 1234567890.123
}

// Clear E-STOP (requires confirmation)
{
  "type": "emergency_stop",
  "data": {
    "engage": false,
    "confirm_clear": "ESTOP_CLEAR_CONFIRM"
  },
  "timestamp": 1234567890.123
}
```

### Clamp Control

```json
{"type": "clamp_close", "data": {}, "timestamp": 1234567890.123}
{"type": "clamp_open", "data": {}, "timestamp": 1234567890.123}
```

### Camera Selection

```json
{"type": "start_camera", "data": {"camera_id": 0}, "timestamp": 1234567890.123}
```

### Height/Force Updates

```json
{"type": "height_update", "data": {"height": 50.0}, "timestamp": 1234567890.123}
{"type": "force_update", "data": {"force": 30.0}, "timestamp": 1234567890.123}
```

### Input Events

```json
{
  "type": "input_event",
  "data": {
    "type": "button",
    "index": 3,
    "value": 1.0
  },
  "timestamp": 1234567890.123
}
```

### Heartbeat Ping (v1.1)

```json
{"type": "ping", "data": {"ts": 1234567890.123, "seq": 1}, "timestamp": 1234567890.123}
```

---

## Telemetry Format

Send telemetry to Base Pi via telemetry sender every 100ms:

```json
{
  "voltage": 12.6,
  "height": 45.0,
  "estop": {"engaged": false, "reason": ""},
  "pong": {"ping_ts": 1234567890.123, "ping_seq": 1},  // v1.1
  "control_age_ms": 50,
  "rtt_ms": 25,  // v1.1
  "imu": {
    "quat_w": 0.99, "quat_x": 0.01, "quat_y": 0.02, "quat_z": 0.01,
    "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.8,
    "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0
  },
  "barometer": {
    "pressure": 1013.25,
    "altitude": 100.0,
    "temperature": 25.0
  },
  "motor_currents": [0.5, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
  "timestamp": 1234567890.123
}
```

---

## Motor Mapping

- **Motor 0-1**: Motoron board 0 (0x10), channels 1-2
- **Motor 2-3**: Motoron board 1 (0x11), channels 1-2
- **Motor 4-5**: Motoron board 2 (0x12), channels 1-2
- **Motor 6-7**: Motoron board 3 (0x13), channels 1-2

Only motors 0-6 are active (7 total).

Speed range: -800 to +800 (0 = stop)

---

## Safety Features

- **E-STOP Boot Latched**: Robot boots with E-STOP ENGAGED (fail-safe default)
- **Watchdog Timeout**: Triggers E-STOP if no control commands for 5 seconds
- **Startup Grace**: 30-second grace period on boot before watchdog activates
- **Connection Loss**: E-STOP on disconnect from Base Pi
- **Command Validation**: All commands validated before execution
- **HMAC Authentication**: Control and telemetry authenticated with PSK
- **E-STOP SET Semantics**: Explicit engage/clear only (never toggle)
- **E-STOP Debounce (v1.1)**: 300ms debounce window for emergency_status events

---

## Logging

Logs are written to:
- Console (stdout/stderr)
- `/var/log/serpent/robot_pi_bridge.log` (if configured)

Log levels: DEBUG, INFO, WARNING, ERROR

---

## Troubleshooting

### Cannot connect to Base Pi

```bash
# Check HaLow link status
ping 192.168.100.1

# Verify BASE_PI_IP is correct
echo $BASE_PI_IP

# Check firewall rules
sudo ufw allow 5001:5003/tcp

# Check Base Pi bridge is running
ssh pi@192.168.100.1
sudo systemctl status serpent-base-bridge
```

### I2C devices not detected

```bash
# Check I2C is enabled
ls /dev/i2c-*

# Scan I2C bus
sudo i2cdetect -y 1

# Check permissions
sudo usermod -a -G i2c $USER

# Reboot if needed
sudo reboot
```

### Cameras not working

```bash
# List devices
v4l2-ctl --list-devices

# Check permissions
sudo usermod -a -G video $USER

# Test camera
ffplay /dev/video0

# Check camera health (v1.1)
sudo journalctl -u serpent-robot-bridge | grep "camera_health"
```

### Motors not responding

```bash
# Verify Motoron boards detected on I2C
sudo i2cdetect -y 1  # Should see 0x10-0x13

# Check power supply to motors
# Verify voltage (should be ~12V)

# Ensure E-STOP is cleared
sudo journalctl -u serpent-robot-bridge | grep "E-STOP"

# Review motor current readings
sudo journalctl -u serpent-robot-bridge | grep "motor_currents"
```

### GPIO permissions

```bash
sudo usermod -a -G gpio $USER
sudo reboot
```

### E-STOP won't clear

```bash
# Check logs for rejection reason
sudo journalctl -u serpent-robot-bridge | grep "REJECTED"

# Verify control connection is active and fresh (< 1.5s old)
sudo journalctl -u serpent-robot-bridge | grep "control_age"

# Ensure confirmation string is correct
# Must be exactly: "ESTOP_CLEAR_CONFIRM"
```

### High E-STOP debounce (v1.1)

```bash
# Check E-STOP debounce window (should be 300ms)
sudo journalctl -u serpent-robot-bridge | grep "debounce"

# Verify E-STOP state changes
sudo journalctl -u serpent-robot-bridge | grep "emergency_status"
```

### Camera health issues (v1.1)

```bash
# Check exponential backoff status
sudo journalctl -u serpent-robot-bridge | grep "camera_retry"

# Verify USB camera connections
lsusb

# Check camera retry delays
sudo journalctl -u serpent-robot-bridge | grep "retry_delay"
```

---

## Mock Mode (for testing without hardware)

If hardware libraries are not available, the bridge runs in mock mode with simulated sensors and actuators.

```bash
# Run without hardware
# (Automatically detects missing hardware and enters mock mode)
python halow_bridge.py
```

Mock mode provides:
- Simulated IMU data
- Simulated barometer data
- Mock motor controller
- Mock servo controller
- Mock video capture

---

## Deployment Checklist

### Pre-Deployment

- [ ] PSK configured in `/etc/serpent/psk` (64 characters)
- [ ] PSK matches Base Pi PSK (`md5sum /etc/serpent/psk`)
- [ ] HaLow router configured (192.168.100.2)
- [ ] Base Pi reachable (`ping 192.168.100.1`)
- [ ] I2C enabled (`sudo raspi-config`)
- [ ] I2C devices detected (`sudo i2cdetect -y 1`)
- [ ] Cameras detected (`v4l2-ctl --list-devices`)
- [ ] User in i2c, gpio, video groups
- [ ] Firewall rules allow ports 5001-5003
- [ ] Log directory exists (`sudo mkdir -p /var/log/serpent`)

### Installation

```bash
cd /path/to/pi_halow_bridge/robot_pi
sudo cp serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-robot-bridge
sudo systemctl start serpent-robot-bridge
```

### Verification

```bash
# Check service status
sudo systemctl status serpent-robot-bridge

# Check logs
sudo journalctl -u serpent-robot-bridge -f

# Verify connections
ss -tlnp | grep 5001

# Verify E-STOP boot latched
sudo journalctl -u serpent-robot-bridge | grep "E-STOP ENGAGED"

# Check I2C devices
sudo i2cdetect -y 1

# Check cameras
v4l2-ctl --list-devices

# Verify telemetry sending
sudo journalctl -u serpent-robot-bridge | grep "telemetry_sent"
```

---

## Key Changes in v1.1

1. **Control Channel Architecture** - Robot Pi is now SERVER (listens on port 5001 for Base Pi connections)
2. **Camera Health Monitoring** - Exponential backoff recovery for failed cameras (2s → 30s max)
3. **E-STOP Debounce** - 300ms debounce window for emergency_status events
4. **RTT Measurement** - Responds to heartbeat pings for round-trip time tracking

---

## Environment Variables Reference

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SERPENT_PSK_HEX` | - | **Yes** | 64-char hex PSK for HMAC |
| `BASE_PI_IP` | `192.168.100.1` | No | Base Pi IP address |
| `CONTROL_PORT` | `5001` | No | Control channel port |
| `VIDEO_PORT` | `5002` | No | Video channel port |
| `TELEMETRY_PORT` | `5003` | No | Telemetry channel port |
| `CAMERA_WIDTH` | `640` | No | Video resolution width |
| `CAMERA_HEIGHT` | `480` | No | Video resolution height |
| `CAMERA_FPS` | `10` | No | Video frame rate |
| `CAMERA_QUALITY` | `60` | No | JPEG quality |
| `CAMERA_RETRY_INITIAL_DELAY` | `2.0` | No | Camera retry initial delay (v1.1) |
| `CAMERA_RETRY_MAX_DELAY` | `30.0` | No | Camera retry max delay (v1.1) |
| `I2C_BUS` | `1` | No | I2C bus number |
| `SENSOR_READ_INTERVAL` | `0.1` | No | Sensor read interval (100ms) |
| `TELEMETRY_INTERVAL` | `0.1` | No | Telemetry send interval (100ms) |
| `WATCHDOG_TIMEOUT` | `5.0` | No | E-STOP timeout (seconds) |
| `STARTUP_GRACE_PERIOD` | `30.0` | No | Boot grace period (seconds) |
| `ESTOP_DEBOUNCE_WINDOW_MS` | `300` | No | E-STOP debounce (ms, v1.1) |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity |
| `LOG_FILE` | - | No | Log file path |

---

## Support

For deployment instructions, see **README.md** and **QUICK_REFERENCE.md**.
For integration examples, see **INTEGRATION.md**.
For troubleshooting, check logs: `sudo journalctl -u serpent-robot-bridge -f`

---

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production Ready

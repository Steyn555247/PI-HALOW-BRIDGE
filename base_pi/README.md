# Base Pi HaLow Bridge (v1.1)

Base Pi component for long-range wireless robot control. Sends control commands to Robot Pi over HaLow, receives telemetry and video, and provides HTTP video streaming endpoint.

**Version:** 1.1
**Last Updated:** 2026-01-29

---

## Components

- **config.py** - Configuration and environment variables
- **halow_bridge.py** - Main coordinator (TCP CLIENT for control)
- **control_sender.py** - Sends HMAC-authenticated control to Robot Pi (TCP client)
- **telemetry_receiver.py** - Receives HMAC-authenticated telemetry from Robot Pi (TCP server)
- **video_receiver.py** - Receives unauthenticated MJPEG video from Robot Pi (TCP server)
- **video_http.py** - HTTP server for video streaming on port 5004 (new in v1.1)

---

## Architecture (v1.1)

```
Base Pi (Operator Station)
    │
    ├─ Control Sender (TCP CLIENT) ──→ Robot Pi :5001
    ├─ Telemetry Receiver (TCP SERVER :5003) ←── Robot Pi
    ├─ Video Receiver (TCP SERVER :5002) ←── Robot Pi
    └─ Video HTTP Server (HTTP SERVER :5004)
```

**Important:** In v1.1, Robot Pi is the control SERVER. Base Pi connects as CLIENT to Robot Pi's control receiver on port 5001.

---

## Installation

```bash
cd base_pi
pip install -r requirements.txt
```

### Dependencies

```
python>=3.7
opencv-python
numpy
flask  # For video HTTP server
```

---

## Configuration

Set environment variables or create a `.env` file:

```bash
# PSK (REQUIRED)
SERPENT_PSK_HEX=<64-char-hex-psk>

# Network
ROBOT_PI_IP=192.168.100.2
CONTROL_PORT=5001
VIDEO_PORT=5002
TELEMETRY_PORT=5003
VIDEO_HTTP_PORT=5004    # New in v1.1

# Safety
WATCHDOG_TIMEOUT=5.0
RECONNECT_DELAY=2.0

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/serpent/base_pi_bridge.log
```

---

## Usage

### Standalone Mode

```bash
python halow_bridge.py
```

### Systemd Service

```bash
sudo cp serpent-base-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-base-bridge
sudo systemctl start serpent-base-bridge
```

Check status:
```bash
sudo systemctl status serpent-base-bridge
journalctl -u serpent-base-bridge -f
```

---

## Features

### Control Sender
- **TCP CLIENT** to Robot Pi port 5001 (v1.1 architecture)
- HMAC-SHA256 authenticated framing
- Sends control commands (emergency_stop, clamp, camera, etc.)
- Heartbeat ping/pong with RTT measurement (v1.1)
- Auto-reconnect on connection loss

### Telemetry Receiver
- **TCP SERVER** on port 5003
- HMAC-SHA256 authenticated framing
- Receives telemetry at 10 Hz from Robot Pi
- Includes E-STOP state, voltage, IMU, barometer, RTT

### Video Receiver
- **TCP SERVER** on port 5002
- Receives unauthenticated MJPEG stream from Robot Pi
- 640×480 @ 10 FPS (configurable on Robot Pi)
- Backpressure handling (frames dropped if socket blocked)

### Video HTTP Server (New in v1.1)
- **HTTP SERVER** on port 5004
- Serves video frames for browser/client access
- Endpoints:
  - `GET /video` - MJPEG stream (multipart/x-mixed-replace)
  - `GET /frame` - Single JPEG frame
  - `GET /health` - Health check JSON

---

## Video HTTP API (v1.1)

### Stream Video (MJPEG)

```bash
# Command line
curl http://localhost:5004/video > stream.mjpeg

# Browser
http://localhost:5004/video
```

### Get Single Frame

```bash
curl http://localhost:5004/frame > frame.jpg
```

### Health Check

```bash
curl http://localhost:5004/health
```

Response:
```json
{
  "backend_connected": true,
  "control_connected": true,
  "telemetry_connected": true,
  "video_connected": true,
  "estop_engaged": false,
  "telemetry_age_ms": 50,
  "rtt_ms": 25,
  "psk_valid": true
}
```

---

## Safety Features

- **Watchdog**: Triggers E-STOP if no telemetry received for 5 seconds
- **Auto-reconnect**: Automatically reconnects to Robot Pi on connection loss
- **HMAC Authentication**: All control and telemetry authenticated with PSK
- **Control Priority**: Video never blocks control channel

---

## Control Commands

Send control commands to Robot Pi via control sender:

### Emergency Stop

```python
# Engage E-STOP
{
  "type": "emergency_stop",
  "data": {"engage": True, "reason": "operator"},
  "timestamp": 1234567890.123
}

# Clear E-STOP (requires confirmation string)
{
  "type": "emergency_stop",
  "data": {
    "engage": False,
    "confirm_clear": "ESTOP_CLEAR_CONFIRM"
  },
  "timestamp": 1234567890.123
}
```

### Clamp Control

```python
{"type": "clamp_close", "data": {}, "timestamp": 1234567890.123}
{"type": "clamp_open", "data": {}, "timestamp": 1234567890.123}
```

### Camera Selection

```python
{"type": "start_camera", "data": {"camera_id": 0}, "timestamp": 1234567890.123}
```

### Heartbeat Ping (v1.1)

```python
{"type": "ping", "data": {"ts": 1234567890.123, "seq": 1}, "timestamp": 1234567890.123}
```

---

## Telemetry Data

Receive telemetry from Robot Pi via telemetry receiver:

```python
{
  "voltage": 12.6,
  "height": 45.0,
  "estop": {"engaged": False, "reason": ""},
  "pong": {"ping_ts": 1234567890.123, "ping_seq": 1},  # v1.1
  "control_age_ms": 50,
  "rtt_ms": 25,  # v1.1
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

## Logging

Logs are written to:
- Console (stdout/stderr)
- `/var/log/serpent/base_pi_bridge.log` (if configured)

Log levels: DEBUG, INFO, WARNING, ERROR

---

## Troubleshooting

### Cannot connect to Robot Pi

```bash
# Check HaLow link status
ping 192.168.100.2

# Verify ROBOT_PI_IP is correct
echo $ROBOT_PI_IP

# Check firewall rules
sudo ufw allow 5001:5004/tcp

# Check Robot Pi bridge is running
ssh pi@192.168.100.2
sudo systemctl status serpent-robot-bridge
```

### No telemetry received

```bash
# Check Robot Pi is sending
ssh pi@192.168.100.2
sudo journalctl -u serpent-robot-bridge | grep telemetry

# Check telemetry port is open
ss -tlnp | grep 5003

# Check PSK matches
md5sum /etc/serpent/psk  # Compare with Robot Pi
```

### Video not streaming

```bash
# Verify video port is open
ss -tlnp | grep 5002

# Check Robot Pi video sender
ssh pi@192.168.100.2
sudo journalctl -u serpent-robot-bridge | grep video

# Check video HTTP endpoint
curl http://localhost:5004/health
```

### HMAC authentication failures

```bash
# Verify PSK matches on both Pis
md5sum /etc/serpent/psk

# Check logs for HMAC errors
sudo journalctl -u serpent-base-bridge | grep HMAC

# Ensure PSK is 64 characters
cat /etc/serpent/psk | wc -c  # Should output 64
```

### Video HTTP not working (v1.1)

```bash
# Check video HTTP server is running
curl http://localhost:5004/health

# Check port is not in use
ss -tlnp | grep 5004

# Check video receiver has frames
sudo journalctl -u serpent-base-bridge | grep "frames_received"
```

### High latency (RTT > 100ms)

```bash
# Check HaLow link quality
ping 192.168.100.2

# Check telemetry for RTT
curl http://localhost:5004/health | grep rtt_ms

# Check for packet loss
sudo journalctl -u serpent-base-bridge | grep "packet_loss"
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] PSK configured in `/etc/serpent/psk` (64 characters)
- [ ] PSK matches Robot Pi PSK (`md5sum /etc/serpent/psk`)
- [ ] HaLow router configured (192.168.100.1)
- [ ] Robot Pi reachable (`ping 192.168.100.2`)
- [ ] Firewall rules allow ports 5001-5004
- [ ] Log directory exists (`sudo mkdir -p /var/log/serpent`)

### Installation

```bash
cd /path/to/pi_halow_bridge/base_pi
sudo cp serpent-base-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-base-bridge
sudo systemctl start serpent-base-bridge
```

### Verification

```bash
# Check service status
sudo systemctl status serpent-base-bridge

# Check logs
sudo journalctl -u serpent-base-bridge -f

# Verify connections
ss -tlnp | grep 500

# Test video HTTP
curl http://localhost:5004/health
curl http://localhost:5004/frame > test_frame.jpg

# Check RTT
curl http://localhost:5004/health | grep rtt_ms
```

---

## Key Changes in v1.1

1. **Control Channel Architecture** - Base Pi is now CLIENT (connects to Robot Pi SERVER on port 5001)
2. **Video HTTP Server** - New HTTP server on port 5004 for MJPEG streaming
3. **RTT Measurement** - Heartbeat ping/pong with timestamp tracking for latency monitoring
4. **Video HTTP Endpoints** - `/video`, `/frame`, `/health` for easy browser/client access

---

## Environment Variables Reference

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SERPENT_PSK_HEX` | - | **Yes** | 64-char hex PSK for HMAC |
| `ROBOT_PI_IP` | `192.168.100.2` | No | Robot Pi IP address |
| `CONTROL_PORT` | `5001` | No | Control channel port |
| `VIDEO_PORT` | `5002` | No | Video channel port |
| `TELEMETRY_PORT` | `5003` | No | Telemetry channel port |
| `VIDEO_HTTP_PORT` | `5004` | No | Video HTTP port (v1.1) |
| `WATCHDOG_TIMEOUT` | `5.0` | No | E-STOP timeout (seconds) |
| `RECONNECT_DELAY` | `2.0` | No | Reconnect delay (seconds) |
| `LOG_LEVEL` | `INFO` | No | Logging verbosity |
| `LOG_FILE` | - | No | Log file path |

---

## Integration Examples

### Python Client

```python
import socket
import json
from common.framing import SecureFramer

# Connect to control sender
framer = SecureFramer(role="base_pi_client")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.100.1", 5001))

# Send E-STOP engage
command = {
    "type": "emergency_stop",
    "data": {"engage": True, "reason": "test"},
    "timestamp": time.time()
}
frame = framer.send_frame(json.dumps(command).encode('utf-8'))
sock.sendall(frame)
sock.close()
```

### Web Dashboard

```html
<!DOCTYPE html>
<html>
<head>
    <title>Robot Control</title>
</head>
<body>
    <h1>Robot Video Feed</h1>
    <img src="http://192.168.100.1:5004/video" style="width: 100%;">

    <h2>Health Status</h2>
    <pre id="health"></pre>

    <script>
        setInterval(() => {
            fetch('http://192.168.100.1:5004/health')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('health').textContent = JSON.stringify(data, null, 2);
                });
        }, 1000);
    </script>
</body>
</html>
```

---

## Support

For integration examples, see **INTEGRATION.md**.
For deployment instructions, see **README.md** and **QUICK_REFERENCE.md**.
For troubleshooting, check logs: `sudo journalctl -u serpent-base-bridge -f`

---

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production Ready

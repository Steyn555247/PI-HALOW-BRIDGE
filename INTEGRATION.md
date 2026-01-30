# Integration Guide: Pi HaLow Bridge v1.1

## Overview

The Pi HaLow Bridge v1.1 is a standalone HMAC-authenticated communication system for long-range wireless robot control. This guide explains how to integrate the bridge with external systems and applications.

**Version:** 1.1
**Last Updated:** 2026-01-29

---

## Architecture Overview

```
┌──────────────────────────────────────────────────┐
│          External Application/System             │
│   (Web dashboard, Mobile app, Control system)    │
└──────────────┬───────────────────────────────────┘
               │
               │ HTTP/WebSocket/Custom Protocol
               │
┌──────────────▼───────────────────────────────────┐
│           Integration Layer                      │
│   • Read telemetry from Base Pi                  │
│   • Send control commands to Base Pi             │
│   • Stream video from Video HTTP endpoint        │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│           Base Pi HaLow Bridge                   │
│   • Control Sender (TCP CLIENT → Robot)          │
│   • Telemetry Receiver (TCP SERVER :5003)        │
│   • Video Receiver (TCP SERVER :5002)            │
│   • Video HTTP Server (HTTP SERVER :5004)        │
└──────────────┬───────────────────────────────────┘
               │
               │ HaLow Link (802.11ah)
               │
┌──────────────▼───────────────────────────────────┐
│           Robot Pi HaLow Bridge                  │
│   • Control Receiver (TCP SERVER :5001)          │
│   • Telemetry Sender (TCP CLIENT → Base)         │
│   • Video Sender (TCP CLIENT → Base)             │
│   • Actuator Controller (E-STOP + motors)        │
└──────────────────────────────────────────────────┘
```

---

## Integration Methods

### Method 1: Direct TCP Integration (Low-Level)

Directly integrate with the Base Pi's TCP ports for full control.

#### Send Control Commands (Base → Robot)

```python
import socket
import json
import time
from common.framing import SecureFramer  # Import from bridge

# Initialize secure framing
framer = SecureFramer(role="base_pi_client")

# Connect to Base Pi control sender
# (Base Pi then forwards to Robot Pi)
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.100.1", 5001))  # Base Pi IP and control port

# Send E-STOP engage
command = {
    "type": "emergency_stop",
    "data": {"engage": True, "reason": "operator"},
    "timestamp": time.time()
}
frame = framer.send_frame(json.dumps(command).encode('utf-8'))
sock.sendall(frame)

# Send clamp close
command = {
    "type": "clamp_close",
    "data": {},
    "timestamp": time.time()
}
frame = framer.send_frame(json.dumps(command).encode('utf-8'))
sock.sendall(frame)

sock.close()
```

**Note:** This requires HMAC authentication with the correct PSK. The PSK must match the one configured on both Pi systems.

#### Receive Telemetry (Robot → Base)

```python
import socket
import json
from common.framing import SecureFramer

# Initialize secure framing
framer = SecureFramer(role="base_pi_server")

# Connect to Base Pi telemetry receiver
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.100.1", 5003))  # Base Pi IP and telemetry port

# Receive telemetry frames
while True:
    data = sock.recv(4096)
    if not data:
        break

    # Decode HMAC-authenticated frame
    payload, valid = framer.receive_frame(data)
    if valid and payload:
        telemetry = json.loads(payload.decode('utf-8'))
        print(f"Voltage: {telemetry['voltage']}")
        print(f"E-STOP: {telemetry['estop']['engaged']}")
        print(f"RTT: {telemetry['rtt_ms']}ms")
        print(f"IMU: {telemetry['imu']}")
        print(f"Barometer: {telemetry['barometer']}")

sock.close()
```

---

### Method 2: Video HTTP Integration (Recommended for Video)

Use the Video HTTP endpoint on Base Pi (port 5004) for easy video streaming.

#### Stream Video in Web Browser

```html
<!DOCTYPE html>
<html>
<head>
    <title>Robot Video Feed</title>
</head>
<body>
    <h1>Robot Camera Feed</h1>
    <img src="http://192.168.100.1:5004/video" alt="Robot Video" style="width: 100%;">

    <h2>Health Status</h2>
    <pre id="health"></pre>

    <script>
        // Fetch health status
        fetch('http://192.168.100.1:5004/health')
            .then(response => response.json())
            .then(data => {
                document.getElementById('health').textContent = JSON.stringify(data, null, 2);
            });

        // Refresh health every 2 seconds
        setInterval(() => {
            fetch('http://192.168.100.1:5004/health')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('health').textContent = JSON.stringify(data, null, 2);
                });
        }, 2000);
    </script>
</body>
</html>
```

#### Stream Video in Python

```python
import requests
import cv2
import numpy as np

# MJPEG stream from Base Pi
url = "http://192.168.100.1:5004/video"
stream = requests.get(url, stream=True)

bytes_data = b''
for chunk in stream.iter_content(chunk_size=1024):
    bytes_data += chunk
    a = bytes_data.find(b'\xff\xd8')  # JPEG start
    b = bytes_data.find(b'\xff\xd9')  # JPEG end
    if a != -1 and b != -1:
        jpg = bytes_data[a:b+2]
        bytes_data = bytes_data[b+2:]

        # Decode JPEG
        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        cv2.imshow('Robot Camera', img)

        if cv2.waitKey(1) == 27:  # ESC to exit
            break

cv2.destroyAllWindows()
```

#### Get Single Frame

```bash
# Command line
curl http://192.168.100.1:5004/frame > frame.jpg

# Python
import requests
response = requests.get("http://192.168.100.1:5004/frame")
with open("frame.jpg", "wb") as f:
    f.write(response.content)
```

---

### Method 3: High-Level Python Integration

Create a wrapper class for easier integration.

```python
import socket
import json
import time
import threading
import requests
from common.framing import SecureFramer

class RobotBridgeClient:
    """High-level client for Pi HaLow Bridge integration"""

    def __init__(self, base_pi_ip="192.168.100.1"):
        self.base_pi_ip = base_pi_ip
        self.control_framer = SecureFramer(role="base_pi_client")
        self.telemetry_framer = SecureFramer(role="base_pi_server")
        self.control_sock = None
        self.telemetry_sock = None
        self.telemetry_callback = None
        self.telemetry_thread = None
        self.running = False

    def connect(self):
        """Connect to Base Pi control and telemetry"""
        # Connect control
        self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.control_sock.connect((self.base_pi_ip, 5001))

        # Connect telemetry
        self.telemetry_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.telemetry_sock.connect((self.base_pi_ip, 5003))

        # Start telemetry receive thread
        self.running = True
        self.telemetry_thread = threading.Thread(target=self._receive_telemetry, daemon=True)
        self.telemetry_thread.start()

    def disconnect(self):
        """Disconnect from Base Pi"""
        self.running = False
        if self.control_sock:
            self.control_sock.close()
        if self.telemetry_sock:
            self.telemetry_sock.close()

    def send_emergency_stop(self, engage=True, reason="operator"):
        """Send E-STOP command"""
        command = {
            "type": "emergency_stop",
            "data": {"engage": engage, "reason": reason},
            "timestamp": time.time()
        }
        self._send_command(command)

    def send_clamp_close(self):
        """Close clamp"""
        command = {"type": "clamp_close", "data": {}, "timestamp": time.time()}
        self._send_command(command)

    def send_clamp_open(self):
        """Open clamp"""
        command = {"type": "clamp_open", "data": {}, "timestamp": time.time()}
        self._send_command(command)

    def send_camera_switch(self, camera_id):
        """Switch active camera (0, 1, or 2)"""
        command = {
            "type": "start_camera",
            "data": {"camera_id": camera_id},
            "timestamp": time.time()
        }
        self._send_command(command)

    def get_video_url(self):
        """Get video stream URL"""
        return f"http://{self.base_pi_ip}:5004/video"

    def get_health(self):
        """Get system health status"""
        response = requests.get(f"http://{self.base_pi_ip}:5004/health")
        return response.json()

    def set_telemetry_callback(self, callback):
        """Set callback for telemetry data: callback(telemetry_dict)"""
        self.telemetry_callback = callback

    def _send_command(self, command):
        """Send authenticated command"""
        frame = self.control_framer.send_frame(json.dumps(command).encode('utf-8'))
        self.control_sock.sendall(frame)

    def _receive_telemetry(self):
        """Receive telemetry in background thread"""
        buffer = b''
        while self.running:
            try:
                data = self.telemetry_sock.recv(4096)
                if not data:
                    break

                buffer += data
                payload, valid = self.telemetry_framer.receive_frame(buffer)
                if valid and payload:
                    telemetry = json.loads(payload.decode('utf-8'))
                    if self.telemetry_callback:
                        self.telemetry_callback(telemetry)
            except Exception as e:
                print(f"Telemetry receive error: {e}")
                break

# Usage example
if __name__ == "__main__":
    client = RobotBridgeClient(base_pi_ip="192.168.100.1")

    # Set telemetry callback
    def on_telemetry(data):
        print(f"Voltage: {data['voltage']}V, E-STOP: {data['estop']['engaged']}, RTT: {data['rtt_ms']}ms")

    client.set_telemetry_callback(on_telemetry)

    # Connect
    client.connect()

    # Send commands
    time.sleep(1)
    client.send_clamp_close()
    time.sleep(2)
    client.send_camera_switch(1)

    # Get health
    health = client.get_health()
    print(f"Health: {health}")

    # Run for 10 seconds
    time.sleep(10)

    # Disconnect
    client.disconnect()
```

---

## Common Integration Scenarios

### Scenario 1: Web Dashboard

**Goal:** Create a web dashboard to monitor robot status and send commands.

**Architecture:**
```
Browser <--WebSocket--> Flask/FastAPI Backend <--TCP--> Base Pi Bridge
```

**Backend (Flask + Flask-SocketIO):**

```python
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
from robot_bridge_client import RobotBridgeClient

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
robot = RobotBridgeClient(base_pi_ip="192.168.100.1")

# Connect to robot on startup
robot.connect()

# Forward telemetry to web clients
def on_telemetry(data):
    socketio.emit('telemetry', data)

robot.set_telemetry_callback(on_telemetry)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/video')
def video_feed():
    return jsonify({"url": robot.get_video_url()})

@socketio.on('emergency_stop')
def handle_estop(data):
    engage = data.get('engage', True)
    robot.send_emergency_stop(engage=engage)
    emit('command_sent', {'type': 'emergency_stop', 'engage': engage})

@socketio.on('clamp_close')
def handle_clamp_close():
    robot.send_clamp_close()
    emit('command_sent', {'type': 'clamp_close'})

@socketio.on('camera_switch')
def handle_camera_switch(data):
    camera_id = data.get('camera_id', 0)
    robot.send_camera_switch(camera_id)
    emit('command_sent', {'type': 'camera_switch', 'camera_id': camera_id})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)
```

---

### Scenario 2: Mobile App Integration

**Goal:** Control robot from mobile app.

**Architecture:**
```
Mobile App <--HTTP/WebSocket--> API Server <--TCP--> Base Pi Bridge
```

Use the Flask backend from Scenario 1, or create a REST API:

```python
from flask import Flask, request, jsonify
from robot_bridge_client import RobotBridgeClient

app = Flask(__name__)
robot = RobotBridgeClient(base_pi_ip="192.168.100.1")
robot.connect()

@app.route('/api/emergency_stop', methods=['POST'])
def emergency_stop():
    data = request.json
    engage = data.get('engage', True)
    reason = data.get('reason', 'mobile_app')
    robot.send_emergency_stop(engage=engage, reason=reason)
    return jsonify({"success": True})

@app.route('/api/clamp', methods=['POST'])
def clamp():
    action = request.json.get('action')  # 'open' or 'close'
    if action == 'close':
        robot.send_clamp_close()
    elif action == 'open':
        robot.send_clamp_open()
    else:
        return jsonify({"error": "Invalid action"}), 400
    return jsonify({"success": True})

@app.route('/api/camera', methods=['POST'])
def camera():
    camera_id = request.json.get('camera_id', 0)
    robot.send_camera_switch(camera_id)
    return jsonify({"success": True})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify(robot.get_health())

@app.route('/api/video_url', methods=['GET'])
def video_url():
    return jsonify({"url": robot.get_video_url()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

---

### Scenario 3: Automation/Scripting

**Goal:** Automate robot tasks via Python script.

```python
from robot_bridge_client import RobotBridgeClient
import time

robot = RobotBridgeClient(base_pi_ip="192.168.100.1")
robot.connect()

# Automated task sequence
print("Starting automated sequence...")

# 1. Ensure E-STOP is clear
robot.send_emergency_stop(engage=False, reason="automation_start")
time.sleep(1)

# 2. Switch to camera 0
robot.send_camera_switch(0)
time.sleep(1)

# 3. Close clamp
robot.send_clamp_close()
time.sleep(2)

# 4. Wait for 5 seconds
time.sleep(5)

# 5. Open clamp
robot.send_clamp_open()
time.sleep(2)

# 6. Engage E-STOP at end
robot.send_emergency_stop(engage=True, reason="automation_complete")

print("Sequence complete")
robot.disconnect()
```

---

## Security Considerations

### PSK Management

The Pi HaLow Bridge uses HMAC-SHA256 authentication with a pre-shared key (PSK). Integration systems must:

1. **Store PSK securely** - Environment variables, secrets manager, or key vault
2. **Never commit PSK to version control**
3. **Rotate PSK periodically** (manual process in v1.1)
4. **Use same PSK as Base Pi and Robot Pi**

### Integration Security

1. **Expose limited API** - Only expose necessary commands to external systems
2. **Add authentication** - Add auth layer (JWT, API keys) to integration API
3. **Rate limiting** - Prevent command flooding
4. **Audit logging** - Log all commands sent to robot

Example authentication wrapper:

```python
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)
API_KEY = "your-api-key-here"  # Store securely!

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/emergency_stop', methods=['POST'])
@require_api_key
def emergency_stop():
    # ... implementation
    pass
```

---

## Monitoring and Debugging

### Health Check

```python
import requests

response = requests.get("http://192.168.100.1:5004/health")
health = response.json()

print(f"Backend connected: {health['backend_connected']}")
print(f"Control connected: {health['control_connected']}")
print(f"Telemetry connected: {health['telemetry_connected']}")
print(f"Video connected: {health['video_connected']}")
print(f"E-STOP state: {health['estop_engaged']}")
print(f"RTT: {health['rtt_ms']}ms")
```

### Telemetry Monitoring

```python
def on_telemetry(data):
    voltage = data.get('voltage')
    estop = data.get('estop', {}).get('engaged')
    rtt = data.get('rtt_ms')

    # Alert on low voltage
    if voltage < 11.0:
        print(f"WARNING: Low voltage: {voltage}V")

    # Alert on high RTT
    if rtt > 100:
        print(f"WARNING: High latency: {rtt}ms")

    # Alert on E-STOP
    if estop:
        print(f"ALERT: E-STOP engaged!")

client.set_telemetry_callback(on_telemetry)
```

---

## Troubleshooting

### Cannot Connect to Base Pi

```bash
# Check Base Pi bridge is running
ssh pi@192.168.100.1
sudo systemctl status serpent-base-bridge

# Check ports are listening
ss -tlnp | grep 500

# Test video HTTP
curl http://192.168.100.1:5004/health
```

### HMAC Authentication Failures

```bash
# Verify PSK matches
md5sum /etc/serpent/psk  # On both Pis, should match

# Check logs for HMAC errors
sudo journalctl -u serpent-base-bridge | grep HMAC
```

### Telemetry Not Received

```bash
# Check Robot Pi is sending
ssh pi@192.168.100.2
sudo journalctl -u serpent-robot-bridge | grep telemetry

# Check Base Pi is receiving
ssh pi@192.168.100.1
sudo journalctl -u serpent-base-bridge | grep telemetry
```

---

## Reference: Control Commands

| Command Type | Data Fields | Description |
|--------------|-------------|-------------|
| `emergency_stop` | `engage` (bool), `reason` (str) | Engage/clear E-STOP |
| `clamp_close` | None | Close clamp |
| `clamp_open` | None | Open clamp |
| `start_camera` | `camera_id` (int: 0-2) | Switch active camera |
| `height_update` | `height` (float) | Update height setpoint |
| `force_update` | `force` (float) | Update force setpoint |
| `input_event` | `type`, `index`, `value` | Gamepad input event |
| `ping` | `ts` (float), `seq` (int) | Heartbeat ping |

---

## Reference: Telemetry Data

| Field | Type | Description |
|-------|------|-------------|
| `voltage` | float | Battery voltage (V) |
| `height` | float | Current height (cm) |
| `estop` | dict | E-STOP state (`engaged`, `reason`) |
| `pong` | dict | Ping response (`ping_ts`, `ping_seq`) |
| `control_age_ms` | int | Age of last control message (ms) |
| `rtt_ms` | int | Round-trip time (ms) |
| `imu` | dict | IMU data (quat, accel, gyro) |
| `barometer` | dict | Barometer data (pressure, altitude, temp) |
| `motor_currents` | list | Motor currents (A) |
| `timestamp` | float | Telemetry timestamp |

---

## Conclusion

The Pi HaLow Bridge v1.1 provides multiple integration methods:

✅ **Direct TCP** - Low-level control with HMAC authentication
✅ **Video HTTP** - Easy video streaming for web/mobile apps
✅ **High-level Python client** - Simplified integration wrapper
✅ **REST API** - Standard HTTP API for external systems
✅ **WebSocket** - Real-time telemetry streaming

Choose the method that best fits your use case and security requirements.

For deployment and configuration, see **README.md** and **QUICK_REFERENCE.md**.

---

**Version:** 1.1
**Last Updated:** 2026-01-29

# Base Pi HaLow Bridge

Base Pi component for Serpent Robotics rope-climbing robot. Receives control commands from `serpent_backend`, forwards them to Robot Pi over HaLow, and receives video/telemetry back.

## Components

- **config.py** - Configuration and environment variables
- **halow_bridge.py** - Main coordinator, integrates with serpent_backend
- **control_forwarder.py** - Forwards control commands to Robot Pi (TCP)
- **telemetry_receiver.py** - Receives sensor data from Robot Pi (TCP)
- **video_receiver.py** - Receives MJPEG video stream from Robot Pi (TCP)

## Installation

```bash
cd base_pi
pip install -r requirements.txt
```

## Configuration

Set environment variables or create a `.env` file:

```bash
# Network
ROBOT_PI_IP=192.168.100.2
CONTROL_PORT=5001
VIDEO_PORT=5002
TELEMETRY_PORT=5003

# Backend
BACKEND_URL=http://localhost:5000
BACKEND_SOCKETIO_URL=http://localhost:5000

# Video
VIDEO_ENABLED=true
VIDEO_BUFFER_SIZE=65536

# Safety
WATCHDOG_TIMEOUT=5.0
RECONNECT_DELAY=2.0

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/serpent/base_pi_bridge.log
```

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

## Integration with serpent_backend

The bridge connects to `serpent_backend_trimui_s.py` as a Socket.IO client and subscribes to control events:

- `emergency_toggle`
- `clamp_close`, `clamp_open`
- `height_update`, `force_update`
- `start_camera`
- `input_event`, `raw_button_press`

The bridge also emits telemetry events back to the backend:
- `telemetry` - Contains IMU, barometer, motor currents, latency

### Video Integration

To expose video from Robot Pi through serpent_backend, add this to your Flask app:

```python
from halow_bridge import bridge

@app.route('/video_feed/<int:camera_id>')
def video_feed(camera_id):
    """MJPEG video stream from Robot Pi"""
    if bridge and bridge.get_video_stream():
        return Response(bridge.get_video_stream(),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return "Video not available", 503
```

## Architecture

```
TrimUI App
    |
    | Socket.IO / HTTP
    v
serpent_backend
    |
    | Socket.IO
    v
Base Pi HaLow Bridge
    |
    | TCP (Control, Video, Telemetry)
    v
HaLow Router A <---> HaLow Router B
    |
    v
Robot Pi
```

## Safety Features

- **Watchdog**: Triggers E-STOP if no telemetry received for 5 seconds
- **Auto-reconnect**: Automatically reconnects to Robot Pi on connection loss
- **Connection monitoring**: Logs connection status every 10 seconds

## Logging

Logs are written to:
- Console (stdout/stderr)
- `/var/log/serpent/base_pi_bridge.log` (if configured)

Log levels: DEBUG, INFO, WARNING, ERROR

## Troubleshooting

### Cannot connect to Robot Pi
- Check HaLow link status
- Verify ROBOT_PI_IP is correct
- Check firewall rules: `sudo ufw allow 5001:5003/tcp`

### No telemetry received
- Check Robot Pi is running
- Verify telemetry port (5003) is open
- Check logs for connection errors

### Video not streaming
- Verify VIDEO_ENABLED=true
- Check video port (5002) is open
- Ensure Robot Pi has cameras connected

### Backend connection issues
- Verify serpent_backend is running
- Check BACKEND_SOCKETIO_URL is correct
- Review backend logs for Socket.IO errors

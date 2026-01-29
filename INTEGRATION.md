# Integration Guide: Pi HaLow Bridge with serpent_backend_trimui_s.py

This guide explains how to integrate the Pi HaLow Bridge with your existing `serpent_backend_trimui_s.py` system.

## Architecture Before vs After

### Before (Direct WiFi)
```
TrimUI App <--WiFi--> serpent_backend (Base Pi) <--Local--> USB Cameras + GPIO
```

### After (HaLow Bridge)
```
TrimUI App <--WiFi--> serpent_backend (Base Pi) <--Socket.IO--> Base Pi Bridge
                                                        |
                                                  HaLow Link
                                                        |
                                                  Robot Pi Bridge <--> Cameras + Sensors + Motors
```

## Step-by-Step Integration

### Phase 1: Base Pi Setup (No Code Changes Required)

The Base Pi Bridge integrates as a Socket.IO client to your existing backend.

1. **Install Base Pi Bridge**
   ```bash
   cd /home/pi/serpent/pi_halow_bridge/base_pi
   pip install -r requirements.txt
   ```

2. **Configure Base Pi Bridge**
   ```bash
   cp .env.example .env
   nano .env
   ```

   Set:
   ```
   ROBOT_PI_IP=192.168.100.2
   BACKEND_SOCKETIO_URL=http://localhost:5000
   ```

3. **Test Integration**
   ```bash
   # In one terminal: Run your existing backend
   python /path/to/serpent_backend_trimui_s.py

   # In another terminal: Run the bridge
   python halow_bridge.py
   ```

   You should see:
   ```
   INFO - Connected to serpent_backend
   INFO - Attempting to connect to Robot Pi...
   ```

4. **Verify Socket.IO Events**

   The bridge automatically subscribes to these events from your backend:
   - `emergency_toggle`
   - `clamp_close`, `clamp_open`
   - `height_update`, `force_update`
   - `start_camera`
   - `input_event`, `raw_button_press`

   **No changes needed** to your backend event emitters - the bridge listens automatically!

### Phase 2: Robot Pi Setup

1. **Install Robot Pi Bridge**
   ```bash
   cd /home/pi/serpent/pi_halow_bridge/robot_pi
   pip install -r requirements.txt
   ```

2. **Configure Hardware**
   ```bash
   # Enable I2C
   sudo raspi-config
   # Interface Options -> I2C -> Enable

   # Verify I2C devices
   sudo i2cdetect -y 1
   ```

3. **Configure Robot Pi Bridge**
   ```bash
   cp .env.example .env
   nano .env
   ```

   Set:
   ```
   BASE_PI_IP=192.168.100.1
   CAMERA_0=/dev/video0
   CAMERA_1=/dev/video2
   CAMERA_2=/dev/video4
   ```

4. **Test Robot Pi Bridge**
   ```bash
   python halow_bridge.py
   ```

### Phase 3: Video Integration (Optional Backend Modification)

If you want to serve Robot Pi video through your existing backend endpoints:

#### Option A: Add New Endpoint (Recommended)

Add to `serpent_backend_trimui_s.py`:

```python
from flask import Response
import sys
sys.path.append('/home/pi/serpent/pi_halow_bridge/base_pi')

# Global bridge reference
halow_bridge = None

def init_halow_bridge():
    """Initialize HaLow bridge (call this after SocketIO setup)"""
    global halow_bridge
    from halow_bridge import HaLowBridge
    halow_bridge = HaLowBridge()
    # Start bridge in background thread
    import threading
    bridge_thread = threading.Thread(target=halow_bridge.start, daemon=True)
    bridge_thread.start()

@app.route('/video_feed_halow/<int:camera_id>')
def video_feed_halow(camera_id):
    """Stream video from Robot Pi via HaLow"""
    if halow_bridge and halow_bridge.get_video_stream():
        return Response(halow_bridge.get_video_stream(),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    return "Video not available", 503

# In your main/init section:
if __name__ == '__main__':
    init_halow_bridge()
    socketio.run(app, host='0.0.0.0', port=5000)
```

#### Option B: Run Bridge as Separate Service (No Backend Changes)

Keep the bridge as a separate systemd service and expose video via a simple Flask proxy:

```bash
# Install bridge as service
sudo cp base_pi/serpent-base-bridge.service /etc/systemd/system/
sudo systemctl enable serpent-base-bridge
sudo systemctl start serpent-base-bridge
```

Then access video at: `http://base-pi-ip:5002/` (direct from bridge)

Or create a simple proxy in your backend:

```python
import requests

@app.route('/video_feed_halow/<int:camera_id>')
def video_feed_halow(camera_id):
    """Proxy video from HaLow bridge"""
    try:
        return Response(
            requests.get('http://localhost:5002/video', stream=True).iter_content(chunk_size=1024),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )
    except:
        return "Video not available", 503
```

### Phase 4: Telemetry Integration

The Base Pi Bridge automatically forwards telemetry to your backend via Socket.IO.

Add a handler to `serpent_backend_trimui_s.py`:

```python
@socketio.on('telemetry')
def handle_telemetry(data):
    """Receive telemetry from Robot Pi (via HaLow bridge)"""
    # Forward to TrimUI app
    emit('telemetry', data, broadcast=True)

    # Or process locally
    imu_data = data.get('imu', {})
    motor_currents = data.get('motor_currents', [])
    # ... your processing logic
```

In your TrimUI app, subscribe to `telemetry` events:

```dart
socket.on('telemetry', (data) {
  setState(() {
    // Update UI with IMU, barometer, motor currents, etc.
    imuData = data['imu'];
    barometerData = data['barometer'];
    motorCurrents = data['motor_currents'];
    connectionLatency = data['connection_latency'];
  });
});
```

## Control Flow Examples

### Example 1: Emergency Stop

1. **User presses E-STOP in TrimUI app**
   ```dart
   socket.emit('emergency_toggle', {});
   ```

2. **Backend receives and emits Socket.IO event**
   ```python
   @socketio.on('emergency_toggle')
   def handle_emergency_toggle(data):
       emit('emergency_toggle', data, broadcast=True)
   ```

3. **Base Pi Bridge receives and forwards to Robot Pi**
   ```python
   # In HaLowBridge._setup_socketio_handlers()
   @self.sio.on('emergency_toggle')
   def on_emergency_toggle(data):
       self.control_forwarder.send_command('emergency_toggle', data)
   ```

4. **Robot Pi receives and executes**
   ```python
   # In Robot Pi halow_bridge.py
   def _process_control_command(message):
       if command_type == 'emergency_toggle':
           self.actuator_controller.emergency_stop_all()
   ```

### Example 2: Camera Switch

1. **User selects camera 2 in TrimUI app**
   ```dart
   socket.emit('start_camera', {'camera_id': 2});
   ```

2. **Backend broadcasts event**
   ```python
   @socketio.on('start_camera')
   def handle_start_camera(data):
       emit('start_camera', data, broadcast=True)
   ```

3. **Base Pi Bridge forwards to Robot Pi**
   ```python
   @self.sio.on('start_camera')
   def on_start_camera(data):
       camera_id = data.get('camera_id', 0)
       self.active_camera_id = camera_id
       self.control_forwarder.send_command('start_camera', data)
   ```

4. **Robot Pi switches active camera**
   ```python
   if command_type == 'start_camera':
       camera_id = data.get('camera_id', 0)
       self.video_capture.set_active_camera(camera_id)
   ```

### Example 3: Motor Control via Gamepad

1. **User moves joystick in TrimUI app**
   ```dart
   socket.emit('input_event', {
     'type': 'axis',
     'index': 0,
     'value': 0.75
   });
   ```

2. **Backend forwards event**
   ```python
   @socketio.on('input_event')
   def handle_input_event(data):
       emit('input_event', data, broadcast=True)
   ```

3. **Robot Pi maps input to motor**
   ```python
   def _handle_input_event(data):
       if event_type == 'axis' and index == 0:
           speed = int(value * 800)
           self.actuator_controller.set_motor_speed(0, speed)
   ```

## Deployment Checklist

### Pre-Deployment

- [ ] HaLow routers configured and tested
- [ ] Base Pi can ping Robot Pi (192.168.100.2)
- [ ] Robot Pi can ping Base Pi (192.168.100.1)
- [ ] I2C devices detected on Robot Pi (`i2cdetect -y 1`)
- [ ] Cameras detected on Robot Pi (`v4l2-ctl --list-devices`)
- [ ] Dependencies installed on both Pis

### Deployment

#### Base Pi
```bash
cd /home/pi/serpent/pi_halow_bridge/base_pi

# Install service
sudo cp serpent-base-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-base-bridge

# Start services in order
sudo systemctl start serpent-base-bridge
sudo systemctl start serpent_backend  # Your existing service

# Verify
sudo systemctl status serpent-base-bridge
journalctl -u serpent-base-bridge -f
```

#### Robot Pi
```bash
cd /home/pi/serpent/pi_halow_bridge/robot_pi

# Install service
sudo cp serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-robot-bridge

# Start service
sudo systemctl start serpent-robot-bridge

# Verify
sudo systemctl status serpent-robot-bridge
journalctl -u serpent-robot-bridge -f
```

### Post-Deployment Verification

- [ ] Base Pi Bridge: "Connected to serpent_backend"
- [ ] Base Pi Bridge: "Connected to Robot Pi control"
- [ ] Robot Pi Bridge: "Connected to Base Pi control"
- [ ] Robot Pi Bridge: "Connected to Base Pi telemetry"
- [ ] Video stream visible in TrimUI app
- [ ] Telemetry updates in TrimUI app (IMU, barometer)
- [ ] Controls respond (E-STOP, clamp, motors)
- [ ] Watchdog triggers E-STOP after 5s disconnect (test)

## Customizing Motor/Input Mappings

Edit `robot_pi/halow_bridge.py`, function `_handle_input_event()`:

```python
def _handle_input_event(self, data):
    """Map gamepad inputs to robot actions"""
    event_type = data.get('type')
    index = data.get('index', 0)
    value = data.get('value', 0.0)

    if event_type == 'axis':
        # Example: Map left stick to drive motors
        if index == 0:  # Left stick X (steering)
            speed = int(value * 800)
            self.actuator_controller.set_motor_speed(0, speed)
            self.actuator_controller.set_motor_speed(1, -speed)

        elif index == 1:  # Left stick Y (throttle)
            speed = int(value * 800)
            self.actuator_controller.set_motor_speed(2, speed)
            self.actuator_controller.set_motor_speed(3, speed)

    elif event_type == 'button':
        # Example: Map buttons to clamp
        if index == 0 and value > 0:  # A button
            self._handle_clamp_close()
        elif index == 1 and value > 0:  # B button
            self._handle_clamp_open()
```

## Monitoring and Debugging

### Real-time Logs

```bash
# Base Pi
journalctl -u serpent-base-bridge -f

# Robot Pi
journalctl -u serpent-robot-bridge -f
```

### Check Connection Status

Base Pi status appears in logs every 10 seconds:
```
INFO - Status - Backend: connected, Control: connected, Telemetry: connected, Video: connected
```

Robot Pi status:
```
INFO - Status - Control: connected, Telemetry: connected, E-STOP: clear
```

### Performance Monitoring

Check latency in telemetry data:
```python
# In your backend or TrimUI app
connection_latency = telemetry_data['connection_latency']  # milliseconds
print(f"Link latency: {connection_latency}ms")
```

Typical latencies:
- < 50ms: Excellent
- 50-100ms: Good
- 100-200ms: Acceptable
- > 200ms: Check HaLow link quality

## Rollback Plan

If you need to revert to direct connection:

1. Stop bridges:
   ```bash
   sudo systemctl stop serpent-base-bridge
   sudo systemctl stop serpent-robot-bridge
   ```

2. Your original `serpent_backend_trimui_s.py` continues to work unchanged

3. Reconnect cameras/GPIO locally to Base Pi

## Next Steps

1. **Test E-STOP**: Verify watchdog triggers after 5s disconnect
2. **Test Failover**: Disconnect HaLow and verify E-STOP
3. **Tune Video**: Adjust resolution/FPS/quality for your link
4. **Customize Controls**: Map gamepad inputs to your robot's motors
5. **Add Voltage Monitoring**: Implement battery voltage reading in Robot Pi
6. **Add Logging**: Configure log rotation for production

## Support

- Base Pi issues: See `base_pi/README.md`
- Robot Pi issues: See `robot_pi/README.md`
- Integration issues: Check this guide
- HaLow link issues: Check router logs/status

## Summary

The Pi HaLow Bridge integrates seamlessly with your existing system:

✅ **No breaking changes** to serpent_backend
✅ **No changes needed** to TrimUI app
✅ **Backward compatible** - backend works with or without bridge
✅ **Safety first** - E-STOP, watchdog, auto-reconnect built-in
✅ **Production ready** - systemd services, logging, monitoring included

Happy climbing! 🤖🧗

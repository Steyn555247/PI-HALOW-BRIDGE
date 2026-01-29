# Pi HaLow Bridge - Quick Reference

## Common Commands

### System Control

```bash
# Start services
sudo systemctl start serpent-base-bridge    # Base Pi
sudo systemctl start serpent-robot-bridge   # Robot Pi

# Stop services
sudo systemctl stop serpent-base-bridge
sudo systemctl stop serpent-robot-bridge

# Restart services
sudo systemctl restart serpent-base-bridge
sudo systemctl restart serpent-robot-bridge

# Enable on boot
sudo systemctl enable serpent-base-bridge
sudo systemctl enable serpent-robot-bridge

# Check status
sudo systemctl status serpent-base-bridge
sudo systemctl status serpent-robot-bridge

# View logs (real-time)
journalctl -u serpent-base-bridge -f
journalctl -u serpent-robot-bridge -f

# View last 50 lines
journalctl -u serpent-base-bridge -n 50
journalctl -u serpent-robot-bridge -n 50
```

### Network Diagnostics

```bash
# Test HaLow link
ping 192.168.100.2   # From Base Pi
ping 192.168.100.1   # From Robot Pi

# Check open ports
sudo netstat -tlnp | grep 500[1-3]

# Test port connectivity
nc -zv 192.168.100.2 5001   # Control port
nc -zv 192.168.100.2 5002   # Video port
nc -zv 192.168.100.2 5003   # Telemetry port
```

### I2C Diagnostics (Robot Pi)

```bash
# List I2C buses
ls /dev/i2c-*

# Scan I2C bus 1
sudo i2cdetect -y 1

# Expected devices:
# 0x10, 0x11, 0x12, 0x13 - Motoron boards
# 0x4A - BNO085 IMU
# 0x77 - BMP388 Barometer
```

### Camera Diagnostics (Robot Pi)

```bash
# List video devices
v4l2-ctl --list-devices

# Test camera capture
ffplay /dev/video0

# Check camera capabilities
v4l2-ctl -d /dev/video0 --all
```

## Configuration Files

### Base Pi
```
/home/pi/serpent/pi_halow_bridge/base_pi/.env
```

Key settings:
- `ROBOT_PI_IP=192.168.100.2`
- `BACKEND_SOCKETIO_URL=http://localhost:5000`
- `VIDEO_ENABLED=true`
- `WATCHDOG_TIMEOUT=5.0`

### Robot Pi
```
/home/pi/serpent/pi_halow_bridge/robot_pi/.env
```

Key settings:
- `BASE_PI_IP=192.168.100.1`
- `CAMERA_0=/dev/video0`
- `I2C_BUS=1`
- `BNO085_ADDRESS=0x4A`
- `MOTORON_ADDR_0=0x10`

## Port Reference

| Port | Direction | Protocol | Purpose |
|------|-----------|----------|---------|
| 5001 | Base → Robot | TCP | Control commands |
| 5002 | Robot → Base | TCP | Video stream (MJPEG) |
| 5003 | Robot → Base | TCP | Telemetry (JSON) |
| 5000 | TrimUI → Base | HTTP/WS | serpent_backend |

## Message Formats

### Control (Base → Robot)
```json
{"type": "emergency_toggle", "data": {}, "timestamp": 1234567890.123}
{"type": "clamp_close", "data": {}, "timestamp": 1234567890.123}
{"type": "start_camera", "data": {"camera_id": 0}, "timestamp": 1234567890.123}
```

### Telemetry (Robot → Base)
```json
{
  "voltage": 12.6,
  "height": 45.0,
  "imu": {"quat_w": 0.99, "accel_z": 9.8, ...},
  "barometer": {"pressure": 1013.25, "altitude": 100.0},
  "motor_currents": [0.5, 0.3, ...],
  "connection_latency": 15,
  "timestamp": 1234567890.123
}
```

## I2C Address Map (Robot Pi)

| Device | Address | Interface |
|--------|---------|-----------|
| Motoron Board 0 | 0x10 | I2C Bus 1 |
| Motoron Board 1 | 0x11 | I2C Bus 1 |
| Motoron Board 2 | 0x12 | I2C Bus 1 |
| Motoron Board 3 | 0x13 | I2C Bus 1 |
| BNO085 IMU | 0x4A | I2C Bus 1 |
| BMP388 Barometer | 0x77 | I2C Bus 1 |
| Servo | GPIO 12 | Hardware PWM |

## Motor Channel Map

| Motor ID | Motoron Board | Channel | Usage |
|----------|---------------|---------|-------|
| 0 | 0 (0x10) | 1 | Motor 0 |
| 1 | 0 (0x10) | 2 | Motor 1 |
| 2 | 1 (0x11) | 1 | Motor 2 |
| 3 | 1 (0x11) | 2 | Motor 3 |
| 4 | 2 (0x12) | 1 | Motor 4 |
| 5 | 2 (0x12) | 2 | Motor 5 |
| 6 | 3 (0x13) | 1 | Motor 6 |
| 7 | 3 (0x13) | 2 | (Unused) |

## Troubleshooting Quick Fixes

### "Cannot connect to Robot Pi"
```bash
# Check HaLow link
ping 192.168.100.2

# Check firewall
sudo ufw allow 5001:5003/tcp

# Restart bridge
sudo systemctl restart serpent-base-bridge
```

### "No telemetry received"
```bash
# Check Robot Pi is running
ssh pi@192.168.100.2 'systemctl status serpent-robot-bridge'

# Check Robot Pi logs
ssh pi@192.168.100.2 'journalctl -u serpent-robot-bridge -n 20'
```

### "Video not streaming"
```bash
# Robot Pi: Check cameras
v4l2-ctl --list-devices

# Robot Pi: Test camera
ffplay /dev/video0

# Base Pi: Check video port
nc -zv 192.168.100.2 5002
```

### "I2C devices not detected"
```bash
# Enable I2C
sudo raspi-config
# Interface Options -> I2C -> Enable

# Reboot
sudo reboot

# Verify
sudo i2cdetect -y 1
```

### "E-STOP keeps triggering"
```bash
# Check watchdog timeout (may be too short)
# Edit .env: WATCHDOG_TIMEOUT=10.0

# Check connection quality
ping -c 100 192.168.100.2  # Look for packet loss

# Check logs for disconnect events
journalctl -u serpent-robot-bridge | grep -i disconnect
```

## Performance Tuning

### Low Bandwidth (< 1 Mbps)
```bash
# Robot Pi .env
CAMERA_WIDTH=320
CAMERA_HEIGHT=240
CAMERA_FPS=5
CAMERA_QUALITY=40
```

### High Latency (> 100ms)
- Reduce telemetry rate: `TELEMETRY_INTERVAL=0.2`
- Check HaLow signal strength
- Reduce video FPS: `CAMERA_FPS=5`

### CPU Usage High
- Reduce camera resolution: `320×240`
- Reduce FPS: `CAMERA_FPS=5`
- Increase telemetry interval: `0.2` seconds

## Startup Sequence

1. **Power on HaLow routers** → Wait for link establishment (30s)
2. **Boot Robot Pi** → Auto-start bridge service
3. **Boot Base Pi** → Auto-start bridge service
4. **Start serpent_backend** → Socket.IO connection
5. **Launch TrimUI app** → Connect to backend
6. **Verify telemetry** → Check latency < 100ms
7. **Test E-STOP** → Verify immediate response
8. **Test camera** → Verify video streaming

## Safety Checklist

Before operation:
- [ ] E-STOP button tested and working
- [ ] Watchdog timeout configured (5s default)
- [ ] Connection latency < 100ms
- [ ] All motors respond to commands
- [ ] Telemetry updates visible (10 Hz)
- [ ] Video stream active
- [ ] Battery voltage monitoring working
- [ ] Failover tested (disconnect HaLow, verify E-STOP)

## Log Levels

Set via `LOG_LEVEL` environment variable:

- **DEBUG**: All messages (very verbose)
- **INFO**: Startup, connections, status (default)
- **WARNING**: Disconnects, retries, timeouts
- **ERROR**: Failures, exceptions

## Useful Grep Patterns

```bash
# Find connection events
journalctl -u serpent-robot-bridge | grep -i connect

# Find errors
journalctl -u serpent-robot-bridge | grep ERROR

# Find E-STOP events
journalctl -u serpent-robot-bridge | grep -i emergency

# Find telemetry issues
journalctl -u serpent-base-bridge | grep -i telemetry

# Find video issues
journalctl -u serpent-base-bridge | grep -i video
```

## File Locations

```
/home/pi/serpent/pi_halow_bridge/
├── base_pi/
│   ├── halow_bridge.py          # Main coordinator
│   ├── config.py                # Configuration
│   ├── .env                     # Your settings (gitignored)
│   └── serpent-base-bridge.service
└── robot_pi/
    ├── halow_bridge.py          # Main coordinator
    ├── config.py                # Configuration
    ├── .env                     # Your settings (gitignored)
    └── serpent-robot-bridge.service

/etc/systemd/system/
├── serpent-base-bridge.service
└── serpent-robot-bridge.service

/var/log/serpent/
├── base_pi_bridge.log
└── robot_pi_bridge.log
```

## Environment Variables Cheat Sheet

### Must Configure
- `ROBOT_PI_IP` / `BASE_PI_IP` - Peer IP address
- `CAMERA_0`, `CAMERA_1`, `CAMERA_2` - Camera device paths (Robot Pi)

### Recommended to Review
- `WATCHDOG_TIMEOUT` - E-STOP timeout (default 5.0s)
- `CAMERA_FPS` - Frame rate (default 10)
- `CAMERA_QUALITY` - JPEG quality (default 60)
- `LOG_LEVEL` - Logging verbosity (default INFO)

### Advanced
- `TELEMETRY_INTERVAL` - Send rate (default 0.1s)
- `SENSOR_READ_INTERVAL` - Sensor read rate (default 0.1s)
- `MOTORON_ADDR_*` - I2C addresses (default 0x10-0x13)

## Getting Help

1. Check component READMEs: `base_pi/README.md`, `robot_pi/README.md`
2. Review integration guide: `INTEGRATION.md`
3. Check logs: `journalctl -u serpent-*-bridge -f`
4. Verify hardware: `i2cdetect`, `v4l2-ctl`
5. Test connectivity: `ping`, `nc -zv`

## Quick Test Script

Save as `test_bridge.sh`:

```bash
#!/bin/bash

echo "=== Testing Pi HaLow Bridge ==="

echo "1. Testing HaLow link..."
ping -c 3 192.168.100.2 || echo "FAIL: Cannot reach Robot Pi"

echo "2. Testing control port..."
nc -zv 192.168.100.2 5001 || echo "FAIL: Control port not open"

echo "3. Checking Base Pi service..."
systemctl is-active serpent-base-bridge || echo "FAIL: Base bridge not running"

echo "4. Checking Robot Pi service..."
ssh pi@192.168.100.2 'systemctl is-active serpent-robot-bridge' || echo "FAIL: Robot bridge not running"

echo "5. Checking recent logs..."
journalctl -u serpent-base-bridge -n 5 --no-pager

echo "=== Test complete ==="
```

Run: `bash test_bridge.sh`

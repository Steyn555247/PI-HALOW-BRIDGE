# Robot Pi HaLow Bridge

Robot Pi component for Serpent Robotics rope-climbing robot. Controls actuators (Motoron + servo), reads sensors (IMU + barometer), captures video from 3 USB cameras, and communicates with Base Pi over HaLow.

## Components

- **config.py** - Configuration and environment variables
- **halow_bridge.py** - Main coordinator, receives control, sends telemetry/video
- **actuator_controller.py** - Controls 4× Motoron boards (7 motors) + 1 servo
- **sensor_reader.py** - Reads BNO085 IMU and BMP388 barometer via I2C
- **video_capture.py** - Captures from 3 ELP USB cameras, streams MJPEG

## Hardware

### Actuators
- **4× Pololu Motoron M2H18v20** - I2C addresses 0x10, 0x11, 0x12, 0x13
  - 8 motor channels (2 per board), 7 active
  - I2C bus 1, up to 400 kHz
- **1× Servo** - GPIO 12 (hardware PWM), 50 Hz

### Sensors
- **Adafruit BNO085** - 9-DOF IMU (I2C address 0x4A)
  - Quaternion, acceleration, gyroscope
  - 100ms read interval
- **Adafruit BMP388** - Barometer (I2C address 0x77)
  - Pressure, temperature, altitude
  - 100ms read interval

### Cameras
- **3× ELP USB Camera** - Sony IMX323, 1080P
  - `/dev/video0`, `/dev/video2`, `/dev/video4`
  - Stream resolution: 640×480 @ 10fps
  - JPEG quality: 60

## Installation

```bash
cd robot_pi
pip install -r requirements.txt
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

## Configuration

Set environment variables or create a `.env` file:

```bash
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

# Telemetry
TELEMETRY_INTERVAL=0.1

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/serpent/robot_pi_bridge.log
```

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

## Control Commands

The bridge receives JSON commands over TCP:

### Emergency Toggle
```json
{"type": "emergency_toggle", "data": {}, "timestamp": 1234567890.123}
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

## Telemetry Format

The bridge sends JSON telemetry over TCP every 100ms:

```json
{
  "voltage": 12.6,
  "height": 45.0,
  "force": 30.0,
  "chainsaw_force": 0.0,
  "rope_force": 0.0,
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
  "connection_latency": 15,
  "timestamp": 1234567890.123
}
```

## Motor Mapping

- **Motor 0-1**: Motoron board 0 (0x10), channels 1-2
- **Motor 2-3**: Motoron board 1 (0x11), channels 1-2
- **Motor 4-5**: Motoron board 2 (0x12), channels 1-2
- **Motor 6-7**: Motoron board 3 (0x13), channels 1-2

Only motors 0-6 are active (7 total).

Speed range: -800 to +800 (0 = stop)

## Safety Features

- **Emergency Stop**: Stops all motors and servo immediately
- **Watchdog**: Triggers E-STOP if no control commands for 5 seconds
- **Connection Loss**: E-STOP on disconnect from Base Pi
- **Command Validation**: All commands validated before execution

## Logging

Logs are written to:
- Console (stdout/stderr)
- `/var/log/serpent/robot_pi_bridge.log` (if configured)

Log levels: DEBUG, INFO, WARNING, ERROR

## Troubleshooting

### Cannot connect to Base Pi
- Check HaLow link status
- Verify BASE_PI_IP is correct
- Check firewall rules: `sudo ufw allow 5001:5003/tcp`

### I2C devices not detected
```bash
# Check I2C is enabled
ls /dev/i2c-*

# Scan I2C bus
sudo i2cdetect -y 1

# Check permissions
sudo usermod -a -G i2c $USER
```

### Cameras not working
```bash
# List devices
v4l2-ctl --list-devices

# Check permissions
sudo usermod -a -G video $USER

# Test camera
ffplay /dev/video0
```

### Motors not responding
- Verify Motoron boards detected on I2C
- Check power supply to motors
- Ensure E-STOP is cleared
- Review motor current readings

### GPIO permissions
```bash
sudo usermod -a -G gpio $USER
```

### Mock mode (for testing without hardware)
If hardware libraries are not available, the bridge runs in mock mode with simulated sensors and actuators.

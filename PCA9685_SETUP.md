# PCA9685 Servo Controller Setup Guide

## Hardware Connections

### I2C Wiring (Pi to PCA9685)
```
Raspberry Pi         PCA9685 Board
-----------          -------------
3.3V         →       VCC (logic power)
GND          →       GND
SCL (GPIO 3) →       SCL
SDA (GPIO 2) →       SDA
```

### Servo Connections
```
PCA9685 Channel 0:
- Orange wire → PWM pin 0
- Red wire    → V+ (servo power rail)
- Brown wire  → GND (servo power rail)
```

### Power Supply
**CRITICAL**: Do NOT power servos from Raspberry Pi's 5V!

1. Connect external 5-6V power supply to PCA9685:
   - **V+** terminal → Positive (+) from power supply
   - **GND** terminal → Negative (-) from power supply

2. Power supply requirements:
   - AITRIP 35KG servo: Up to 2A at stall
   - Recommended: 5V 3A+ power supply
   - Add capacitor (1000uF 16V) across V+/GND for stability

## Software Installation

### 1. Install Python Library
```bash
sudo pip3 install adafruit-circuitpython-servokit
```

### 2. Enable I2C
```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
sudo reboot
```

### 3. Verify I2C Connection
```bash
sudo i2cdetect -y 1
```

You should see `40` at address 0x40:
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: 10 11 12 13 -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
60: -- -- -- -- -- -- -- -- -- -- -- -- 6c -- -- --
70: 70 -- -- -- -- -- -- --
```

## Configuration

The code is already configured for PCA9685 in `robot_pi/config.py`:

```python
USE_PCA9685 = True              # Enable PCA9685 mode
PCA9685_ADDRESS = 0x40          # I2C address
SERVO_CHANNEL = 0               # Which channel (0-15)
SERVO_MIN_PULSE = 500           # 0° position (500us)
SERVO_MAX_PULSE = 2500          # 180° position (2500us)
SERVO_ACTUATION_RANGE = 180     # Full range in degrees
```

### To Switch Back to GPIO PWM (if needed)
```python
USE_PCA9685 = False
```

## Testing

### Quick Test
```bash
sudo python3 test_servo.py
```

Expected output:
```
============================================================
Testing Servo Control
============================================================
Configuration:
  - Mode: PCA9685 I2C Servo Controller
  - I2C Address: 0x40
  - Servo Channel: 0
  - Pulse Width: 500-2500us
  - Actuation Range: 180°

Creating ActuatorController...
Starting ActuatorController (initializing hardware)...
Initializing PCA9685 at 0x40, 16 channels...
PCA9685 servo initialized - channel 0 at 90.0° (neutral)
...
```

### Manual Test in Python
```python
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16, address=0x40)

# Configure servo
kit.servo[0].actuation_range = 180
kit.servo[0].set_pulse_width_range(500, 2500)

# Test movement
kit.servo[0].angle = 0      # Minimum position
kit.servo[0].angle = 90     # Center
kit.servo[0].angle = 180    # Maximum position
```

## Advantages of PCA9685

✓ **Zero Jitter** - Dedicated PWM chip, no CPU timing issues
✓ **16 Channels** - Control up to 16 servos from one board
✓ **I2C Interface** - Only uses 2 GPIO pins (SDA/SCL)
✓ **Precise Control** - 12-bit resolution (4096 steps)
✓ **Low CPU Usage** - Hardware PWM offloads work from Pi
✓ **Chainable** - Can use multiple boards (up to 62 boards = 992 servos!)

## Troubleshooting

### "OSError: [Errno 121] Remote I/O error"
- Check I2C wiring (SDA, SCL)
- Verify I2C is enabled: `sudo raspi-config`
- Check address conflict: `sudo i2cdetect -y 1`

### "ServoKit library not available"
```bash
sudo pip3 install adafruit-circuitpython-servokit
```

### Servo doesn't move
- Check servo power supply (V+ and GND)
- Verify servo signal wire on correct channel
- Test with manual Python code above
- Check servo isn't mechanically blocked

### Servo jitters
- Add capacitor (1000uF) across servo power supply
- Use proper power supply (not Pi's 5V rail)
- Check power supply current rating (3A+ recommended)

## Multiple Servos

To add more servos, just connect them to different channels:

```python
# In config.py - add more servo channels if needed
BRAKE_SERVO_CHANNEL = 0
CAMERA_PAN_CHANNEL = 1
CAMERA_TILT_CHANNEL = 2
```

```python
# In code
kit.servo[0].angle = 90   # Brake
kit.servo[1].angle = 45   # Camera pan
kit.servo[2].angle = 120  # Camera tilt
```

## PCA9685 Address Configuration

Default: **0x40**

To change address (allows multiple boards):
- Solder address jumpers A0-A5 on PCA9685 board
- Each jumper adds to base address 0x40
- Example: A0 soldered = 0x41, A1 soldered = 0x42

Update config.py:
```python
PCA9685_ADDRESS = 0x41  # If A0 jumper soldered
```

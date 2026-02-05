# Quick Start: Multi-Sensor I2C Setup

## Installation

```bash
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
pip install -r robot_pi/requirements.txt
```

## Hardware Verification

### Scan for all I2C devices:
```bash
python3 scripts/scan_i2c_devices.py
```

### Expected output:
```
Channel 0: 0x4A (BNO085 IMU)
Channel 1: 0x77 (BMP388 Barometer)
Channel 2: 0x40 (INA219 Battery Current Sensor)
Channel 3: 0x41 (INA219 System Current Sensor)
Channel 4: 0x44 (INA219 Servo Current Sensor)
```

## Testing

### Test in simulation mode (no hardware):
```bash
SIM_MODE=true python3 -c "
from robot_pi.sensor_reader import SensorReader
import time

sr = SensorReader(
    use_multiplexer=True,
    current_sensors={
        'battery': {'addr': 0x40, 'channel': 2, 'shunt_ohms': 0.1, 'max_amps': 3.2},
        'system': {'addr': 0x41, 'channel': 3, 'shunt_ohms': 0.1, 'max_amps': 3.2},
        'servo': {'addr': 0x44, 'channel': 4, 'shunt_ohms': 0.1, 'max_amps': 3.2}
    }
)
sr.start()
time.sleep(1)
print(sr.get_all_data())
sr.stop()
"
```

## Deployment

### Restart the service:
```bash
sudo systemctl restart serpent-robot-bridge.service
```

### Monitor telemetry:
```bash
journalctl -u serpent-robot-bridge.service -f
```

### Check for current sensor data:
```bash
journalctl -u serpent-robot-bridge.service -f | grep -i "battery\|current"
```

## Configuration

### Disable multiplexer (rollback):
Edit `/etc/systemd/system/serpent-robot-bridge.service`:
```ini
[Service]
Environment="USE_I2C_MULTIPLEXER=false"
```

### Custom addresses:
```bash
# Change multiplexer address
export I2C_MUX_ADDRESS=0x70

# Change sensor channels
export IMU_MUX_CHANNEL=0
export BAROMETER_MUX_CHANNEL=1
export CURRENT_SENSOR_BATTERY_CHANNEL=2
export CURRENT_SENSOR_SYSTEM_CHANNEL=3
export CURRENT_SENSOR_SERVO_CHANNEL=4
```

## Troubleshooting

### No devices found on scan:
1. Check I2C is enabled: `sudo raspi-config` → Interface Options → I2C
2. Check wiring connections
3. Verify multiplexer is powered (3.3V)

### Current sensors not reading:
1. Verify INA219 library installed: `pip list | grep ina219`
2. Check sensor addresses don't conflict
3. Test in simulation mode first

### Multiplexer not detected:
1. Check address is 0x70: `i2cdetect -y 1`
2. Verify pullup resistors on SDA/SCL
3. Try scanning without multiplexer

### Service fails to start:
```bash
# Check service status
sudo systemctl status serpent-robot-bridge.service

# View detailed logs
journalctl -u serpent-robot-bridge.service -n 50

# Test manually
SIM_MODE=true python3 -m robot_pi.halow_bridge
```

## New Telemetry Fields

The robot now sends these additional fields:

```json
{
  "voltage": 12.45,        // Real battery voltage (was hardcoded 12.0)
  "battery": {
    "voltage": 12.45,      // Battery voltage (V)
    "current": 850.2,      // Battery current (mA)
    "power": 10585.4       // Battery power (mW)
  },
  "system_power": {
    "voltage": 12.40,      // System voltage (V)
    "current": 420.5,      // System current (mA)
    "power": 5214.2        // System power (mW)
  },
  "servo_power": {
    "voltage": 5.0,        // Servo voltage (V)
    "current": 320.1,      // Servo current (mA)
    "power": 1600.5        // Servo power (mW)
  }
}
```

## Files Modified

- ✅ `robot_pi/i2c_multiplexer.py` (NEW)
- ✅ `robot_pi/sensor_reader.py` (MODIFIED)
- ✅ `robot_pi/config.py` (MODIFIED)
- ✅ `robot_pi/halow_bridge.py` (MODIFIED)
- ✅ `robot_pi/requirements.txt` (MODIFIED)
- ✅ `scripts/scan_i2c_devices.py` (NEW)

## Support

For detailed implementation information, see:
- `MULTI_SENSOR_IMPLEMENTATION.md` - Full implementation details
- `README.md` - Main project documentation
- `HALOW_SETUP_GUIDE.md` - HaLow network setup

# Pull Sensor Updates on Hub/Base Pi

## Quick Setup (Run on Hub at 192.168.1.10)

```bash
cd /path/to/PI-HALOW-BRIDGE

# Pull the latest changes
git pull origin main

# 1. CRITICAL: Setup PSK (Pre-Shared Key) for authentication
./setup_psk_on_hub.sh

# 2. Install sensor libraries in venv (if not already done)
source venv/bin/activate
pip install adafruit-circuitpython-bno055 adafruit-circuitpython-bmp5xx adafruit-circuitpython-tca9548a

# 3. Services will already be restarted by setup_psk_on_hub.sh
# But if needed, you can restart manually:
# sudo systemctl restart serpent-base-bridge
# sudo systemctl restart serpent-dashboard-base

# 4. Check services are running
sudo systemctl status serpent-base-bridge --no-pager | head -15
sudo systemctl status serpent-dashboard-base --no-pager | head -15

# 5. Verify PSK is loaded
sudo journalctl -u serpent-base-bridge -n 20 | grep 'PSK'
# Should see: "[base_pi] PSK loaded successfully"
```

## Verify Sensor Data

After pulling and restarting services, you should see sensor data at:

**Base Pi Dashboard:** `http://192.168.1.10:5006`

The dashboard will show:
- **IMU (BNO055)**: Quaternion, acceleration, gyroscope
- **Barometer (BMP581)**: Pressure, temperature, altitude

The sensor data is received via telemetry from Robot Pi and displayed in real-time.

## Troubleshooting

If sensors don't appear on the Base Pi dashboard:

1. **Check telemetry connection:**
   ```bash
   sudo journalctl -u serpent-base-bridge -n 50 | grep -i telemetry
   ```
   Should see "Robot Pi telemetry connected"

2. **Check for sensor data in logs:**
   ```bash
   sudo journalctl -u serpent-base-bridge -n 50 | grep -i '"imu"'
   ```
   Should see JSON with IMU/barometer data

3. **Verify dashboard service:**
   ```bash
   curl -s http://localhost:5006/api/status | python3 -m json.tool | grep -A 5 sensors
   ```
   Should show sensor data structure

## What Changed

- ✅ Robot Pi sends IMU/barometer data in telemetry (10 Hz)
- ✅ Base Pi receives and broadcasts via WebSocket
- ✅ Dashboard transforms and displays sensor data
- ✅ Status logs include sensor readings every 10 seconds

The same dashboard code works on both Robot Pi and Base Pi - it auto-detects the role and displays data from the appropriate source (logs vs telemetry).

# Robot Pi Dashboard - Installation Summary

## ✅ Correctly Installed on Robot Pi

The dashboard is now properly configured for the **Robot Pi** system.

## Configuration Details

### System Information
- **Location**: Robot Pi
- **Service**: `serpent-dashboard-robot.service`
- **Port**: `5005`
- **Role**: `robot_pi`
- **PSK**: Auto-loaded from robot bridge configuration

### Access URLs
```
Local:    http://localhost:5005
Network:  http://192.168.1.20:5005
          http://10.103.198.76:5005 (if on same network)
```

## What This Dashboard Shows

### Robot-Specific Data
- ✅ **Control Connection**: Robot → Base Pi communication
- ✅ **Telemetry Connection**: Sensor data transmission to Base Pi
- ✅ **Motor Currents**: Real-time current draw for all 8 motors (when available)
- ✅ **Sensor Data**: IMU (accelerometer, gyro, quaternion) and Barometer
- ✅ **E-STOP Status**: Detailed engagement reason and age
- ✅ **Camera Diagnostics**: Scan and test /dev/video* devices
- ✅ **Video Stats**: Frames sent, dropped, drop rate, errors

### Pages Available
1. **Main Dashboard** (`/`)
   - Real-time robot hardware monitoring
   - Connection status indicators
   - Motor and sensor displays
   - Video statistics

2. **Logs** (`/logs`)
   - View robot bridge logs
   - Filter by level (INFO, WARNING, ERROR)
   - Search functionality
   - Auto-refresh

3. **Diagnostics** (`/diagnostics`)
   - Network connectivity tests
   - Camera device scanning
   - Issue detection with suggestions
   - System resource monitoring

## Features Enabled

### ✅ PSK Auto-Loading
- Automatically reads PSK from robot bridge systemd configuration
- Located: `/etc/systemd/system/serpent-robot-bridge.service.d/psk.conf`
- No manual PSK configuration needed
- Shows validation status in dashboard

### ✅ HDMI Auto-Start
- Dashboard only starts when HDMI display is connected
- Saves resources when robot is headless
- HDMI detection script: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh`

**Behavior**:
- **Boot with HDMI**: Dashboard starts automatically
- **Boot without HDMI**: Dashboard doesn't start (0% CPU, 0 MB)
- **Hot-plug HDMI**: Run `sudo systemctl start serpent-dashboard-robot`

## Service Management

### Start/Stop/Restart
```bash
sudo systemctl start serpent-dashboard-robot
sudo systemctl stop serpent-dashboard-robot
sudo systemctl restart serpent-dashboard-robot
```

### Check Status
```bash
sudo systemctl status serpent-dashboard-robot
```

### View Logs
```bash
sudo journalctl -u serpent-dashboard-robot -f
```

### Enable/Disable Auto-Start
```bash
sudo systemctl enable serpent-dashboard-robot   # Auto-start on boot (with HDMI)
sudo systemctl disable serpent-dashboard-robot  # Don't auto-start
```

## Quick Status Check

```bash
curl -s http://localhost:5005/api/status | python3 -m json.tool
```

Expected output:
```json
{
  "role": "robot_pi",
  "health": {
    "psk_valid": true,
    "uptime_s": 22
  },
  "connections": {
    "control": "connected",
    "telemetry": "connected"
  },
  "estop": {
    "engaged": true,
    "reason": "boot_default"
  }
}
```

## Installation Files

### Service Files
```
/etc/systemd/system/serpent-dashboard-robot.service
/etc/systemd/system/serpent-dashboard-robot.service.d/psk.conf
```

### Code Location
```
/home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/
```

### Scripts
```
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/install_dashboard.sh
```

## Corrections Made

### What Was Wrong
❌ Dashboard was initially installed as "Base Pi" role
- Service: `serpent-dashboard-base` (wrong)
- Port: 5006 (wrong)
- Role: `base_pi` (wrong)
- Tried to read from non-existent base bridge service

### What Was Fixed
✅ Dashboard now correctly configured as "Robot Pi"
- Service: `serpent-dashboard-robot` (correct)
- Port: 5005 (correct)
- Role: `robot_pi` (correct)
- Reads from robot bridge service logs

## For Base Pi/Hub Installation

If you want to also install the dashboard on your **Base Pi/Hub** (recommended for complete system visibility):

```bash
# SSH to Base Pi
ssh user@192.168.1.10

# Install dashboard
cd /home/user/Desktop/PI-HALOW-BRIDGE
./scripts/install_dashboard.sh base

# Access at: http://192.168.1.10:5006
```

See `DUAL_DEPLOYMENT.md` for complete dual-dashboard setup guide.

## Troubleshooting

### Dashboard Won't Start
```bash
# Check HDMI detection
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
echo $?  # 0 = HDMI detected, 1 = not detected

# Check service logs
sudo journalctl -u serpent-dashboard-robot -n 50
```

### Port Already in Use
```bash
# Find process using port 5005
sudo netstat -tlnp | grep 5005

# Kill the process
sudo kill -9 $(sudo lsof -t -i:5005)

# Restart service
sudo systemctl restart serpent-dashboard-robot
```

### PSK Shows Invalid
```bash
# Verify PSK is configured
sudo cat /etc/systemd/system/serpent-dashboard-robot.service.d/psk.conf

# Restart services
sudo systemctl restart serpent-robot-bridge
sudo systemctl restart serpent-dashboard-robot
```

### Cannot Access from Network
```bash
# Check if service is running
sudo systemctl is-active serpent-dashboard-robot

# Check if port is listening
sudo netstat -tlnp | grep 5005

# Check firewall (if enabled)
sudo ufw allow 5005/tcp
```

## Resource Usage

- **CPU**: <1% when running
- **Memory**: ~50 MB
- **When HDMI disconnected**: 0% CPU, 0 MB (service not started)

## Documentation

- `dashboard/README.md` - Complete feature documentation
- `dashboard/HDMI_AUTOSTART.md` - HDMI auto-start guide
- `dashboard/DUAL_DEPLOYMENT.md` - Installing on both Pis
- `dashboard/QUICK_REFERENCE.md` - Quick commands
- `dashboard/IMPROVEMENTS.md` - Recent improvements summary

## Support

If you encounter issues:
1. Check service status: `sudo systemctl status serpent-dashboard-robot`
2. View logs: `sudo journalctl -u serpent-dashboard-robot -n 100`
3. Test API: `curl http://localhost:5005/api/status`
4. Check HDMI: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh`

---

✅ **Dashboard is correctly installed on Robot Pi and ready to use!**

Open http://192.168.1.20:5005 in your browser to access it.

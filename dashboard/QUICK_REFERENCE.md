# Dashboard Quick Reference

## Access URLs
- **Local**: http://localhost:5006
- **Network**: http://10.103.198.76:5006
- **IP Address**: http://192.168.1.10:5006

## Service Commands

```bash
# Check status
sudo systemctl status serpent-dashboard-base

# Start/Stop/Restart
sudo systemctl start serpent-dashboard-base
sudo systemctl stop serpent-dashboard-base
sudo systemctl restart serpent-dashboard-base

# View logs
sudo journalctl -u serpent-dashboard-base -f

# Enable/Disable auto-start
sudo systemctl enable serpent-dashboard-base
sudo systemctl disable serpent-dashboard-base
```

## Feature Status Check

```bash
# Check PSK validation
curl -s http://localhost:5006/api/status | jq '.health.psk_valid'

# Check HDMI detection
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
echo $?  # 0 = connected, 1 = not detected

# View full status
curl -s http://localhost:5006/api/status | jq .
```

## HDMI Auto-Start

### Current Behavior
- ✅ **On boot with HDMI**: Dashboard starts automatically
- ✅ **On boot without HDMI**: Dashboard doesn't start (saves resources)
- ✅ **Hot-plug after boot**: Run `sudo systemctl start serpent-dashboard-base`

### Disable HDMI Requirement (Always Start)
```bash
sudo systemctl edit serpent-dashboard-base
# Add these lines:
[Service]
ExecStartPre=
ExecStartPre=/bin/true

# Save and exit, then:
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-base
```

### Re-enable HDMI Requirement
```bash
sudo systemctl revert serpent-dashboard-base
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-base
```

## PSK Configuration

### Check PSK Status
```bash
# View PSK configuration
sudo cat /etc/systemd/system/serpent-dashboard-base.service.d/psk.conf

# Check if PSK is valid in dashboard
curl -s http://localhost:5006/api/status | jq '.health.psk_valid'
# Output: true (good) or false (problem)
```

### Update PSK
If you change the PSK in the bridge service, update the dashboard:
```bash
# Copy PSK from robot bridge to dashboard
sudo cp /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf \
       /etc/systemd/system/serpent-dashboard-base.service.d/psk.conf

# Restart dashboard
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-base
```

## Troubleshooting

### Dashboard Won't Start
```bash
# Check if HDMI is detected
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
echo $?

# Check service condition
sudo systemctl status serpent-dashboard-base | grep Condition

# View detailed logs
sudo journalctl -u serpent-dashboard-base -n 50 --no-pager
```

### PSK Shows Invalid
```bash
# Check robot bridge PSK status
sudo journalctl -u serpent-robot-bridge -n 5 | grep psk_valid

# Verify dashboard has PSK configured
sudo systemctl show serpent-dashboard-base | grep SERPENT_PSK_HEX

# Restart both services
sudo systemctl restart serpent-robot-bridge
sudo systemctl restart serpent-dashboard-base
```

### Dashboard Not Accessible
```bash
# Check if service is running
sudo systemctl is-active serpent-dashboard-base

# Check port
sudo netstat -tlnp | grep 5006

# Test local connection
curl http://localhost:5006/

# Check firewall (if applicable)
sudo ufw status
```

## API Endpoints

```bash
# System status
curl http://localhost:5006/api/status | jq .

# View logs
curl "http://localhost:5006/api/logs?service=robot&lines=50" | jq .

# Network diagnostics
curl http://localhost:5006/api/diagnostics/network | jq .

# Camera scan
curl http://localhost:5006/api/diagnostics/cameras | jq .

# Detect issues
curl http://localhost:5006/api/diagnostics/issues | jq .

# System resources
curl http://localhost:5006/api/diagnostics/resources | jq .
```

## Dashboard Pages

- **Main Dashboard**: http://localhost:5006/
  - Real-time status, connections, sensors, motors, video

- **Logs**: http://localhost:5006/logs
  - Filter and search system logs

- **Diagnostics**: http://localhost:5006/diagnostics
  - Network tests, camera scan, issue detection

## Files and Locations

```
Configuration:
  /etc/systemd/system/serpent-dashboard-base.service
  /etc/systemd/system/serpent-dashboard-base.service.d/psk.conf

Scripts:
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/install_dashboard.sh

Code:
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/

Documentation:
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/README.md
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/HDMI_AUTOSTART.md
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/IMPROVEMENTS.md
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/QUICK_REFERENCE.md (this file)
```

## Resource Usage

```bash
# Check CPU and memory usage
ps aux | grep "dashboard.*web_server"

# Expected usage:
# CPU: <1%
# Memory: ~50 MB

# When not running (HDMI disconnected):
# CPU: 0%
# Memory: 0 MB (service not started)
```

## Installation on Other Systems

```bash
# On Robot Pi (port 5005)
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
./scripts/install_dashboard.sh robot

# On Base Pi (port 5006)
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
./scripts/install_dashboard.sh base

# Auto-detect
./scripts/install_dashboard.sh auto
```

## Common Tasks

### View Real-time Status Updates
```bash
# Watch status API
watch -n 1 'curl -s http://localhost:5006/api/status | jq ".health, .connections"'
```

### Check System Health
```bash
# Full diagnostic check
curl -s http://localhost:5006/api/diagnostics/issues | jq '.issues[]'
```

### Monitor Service Logs
```bash
# Follow logs in real-time
sudo journalctl -u serpent-dashboard-base -f
```

### Restart Everything
```bash
# Restart all services
sudo systemctl restart serpent-robot-bridge
sudo systemctl restart serpent-dashboard-base
```

## Support

For issues or questions:
1. Check `dashboard/README.md` for detailed documentation
2. Review logs: `sudo journalctl -u serpent-dashboard-base -n 100`
3. Verify configuration: See troubleshooting section above

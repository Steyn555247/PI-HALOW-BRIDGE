# Dual Dashboard Deployment Guide

Running dashboards on **both** Robot Pi and Base Pi provides complete system visibility.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DUAL DASHBOARD                           │
└─────────────────────────────────────────────────────────────────┘

ROBOT PI (192.168.1.20)                    BASE PI (192.168.1.10)
┌──────────────────────────┐              ┌──────────────────────────┐
│                          │              │                          │
│  Dashboard :5005         │              │  Dashboard :5006         │
│  ├─ Motor Currents       │              │  ├─ Backend Status       │
│  ├─ Sensor Data (IMU)    │              │  ├─ Video Stream View    │
│  ├─ Camera Stats         │              │  ├─ System Aggregation   │
│  ├─ E-STOP Details       │              │  ├─ Control Forwarding   │
│  └─ Hardware Diagnostics │              │  └─ Operator View        │
│                          │              │                          │
│  Robot Bridge            │◄────────────►│  Base Bridge             │
│  (Hardware Control)      │   HaLow      │  (Backend Interface)     │
└──────────────────────────┘              └──────────────────────────┘
         ▲                                          ▲
         │                                          │
    Local HDMI                                 Local HDMI
    (Field Monitoring)                    (Control Station)
```

## Benefits

### 1. Redundant Monitoring
- If Base Pi network fails, Robot Pi dashboard still works
- If Robot Pi fails, Base Pi dashboard shows connection loss

### 2. Different Perspectives
- **Robot Pi**: "What is the hardware doing right now?"
- **Base Pi**: "What is the system delivering to the operator?"

### 3. Targeted Diagnostics
- Robot Pi: Motor issues, sensor problems, camera failures
- Base Pi: Network issues, backend problems, video streaming

### 4. HDMI Auto-Start on Both
- Connect monitor to Robot Pi → See hardware stats
- Connect monitor to Base Pi → See operator view
- No monitor → Both save resources automatically

## Installation

### On Robot Pi

```bash
# SSH to Robot Pi
ssh robotpi@192.168.1.20

# Navigate to project
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE

# Install dashboard
./scripts/install_dashboard.sh robot

# Verify
curl http://localhost:5005/api/status | jq .
```

### On Base Pi (Already Done ✅)

```bash
# Already installed and running!
# Access at: http://192.168.1.10:5006
```

## Access URLs

### From Your Computer (on same network)

```
Robot Pi Dashboard:
  http://192.168.1.20:5005

Base Pi Dashboard:
  http://192.168.1.10:5006
```

### From Robot Pi (local)

```
Robot Dashboard:    http://localhost:5005
Base Dashboard:     http://192.168.1.10:5006
```

### From Base Pi (local)

```
Base Dashboard:     http://localhost:5006
Robot Dashboard:    http://192.168.1.20:5005
```

## PSK Configuration

Both dashboards need the PSK configured:

### Robot Pi

```bash
# Check if PSK exists
sudo cat /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Create dashboard PSK drop-in (if needed)
sudo mkdir -p /etc/systemd/system/serpent-dashboard-robot.service.d
sudo cp /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf \
        /etc/systemd/system/serpent-dashboard-robot.service.d/psk.conf

# Restart dashboard
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-robot
```

### Base Pi (Already Done ✅)

PSK already configured in:
`/etc/systemd/system/serpent-dashboard-base.service.d/psk.conf`

## Typical Usage Scenarios

### Scenario 1: Lab Testing
- **Base Pi Dashboard**: Main view on control station monitor
- **Robot Pi Dashboard**: Open in browser tab for hardware monitoring
- **Result**: Complete visibility while testing

### Scenario 2: Field Operation
- **Base Pi Dashboard**: Operator view (HDMI to operator station)
- **Robot Pi Dashboard**: Not displayed (no HDMI = auto-disabled)
- **Result**: Clean operator experience, robot saves resources

### Scenario 3: Hardware Debugging
- **Robot Pi Dashboard**: Main view on portable monitor
- **Base Pi Dashboard**: Browser access for comparison
- **Result**: Direct hardware insight + system context

### Scenario 4: Remote Operation
- **Both Dashboards**: Access via browser from any device
- **No HDMI**: Both run if needed, or manually start
- **Result**: Full remote monitoring capability

## Comparison Table

| Feature | Robot Pi Dashboard | Base Pi Dashboard |
|---------|-------------------|-------------------|
| **Port** | 5005 | 5006 |
| **Primary Data** | Robot bridge logs | Base bridge logs |
| **Motor Currents** | ✅ Real-time | ❌ Not available |
| **Sensor Data** | ✅ Direct access | ❌ Not available |
| **Camera Stats** | ✅ Detailed | ⚠️ Limited |
| **Backend Status** | ❌ Not visible | ✅ Full visibility |
| **Video Stream** | ❌ Not embedded | ✅ Embedded player |
| **E-STOP Info** | ✅ Detailed reason | ⚠️ Forwarded status |
| **Network Tests** | From robot perspective | From base perspective |
| **Best For** | Hardware debugging | System monitoring |

## Status Checks

### Verify Both Running

```bash
# Check Robot Pi dashboard (from Robot Pi)
curl http://localhost:5005/api/status | jq '.role'
# Should output: "robot_pi"

# Check Base Pi dashboard (from Base Pi)
curl http://localhost:5006/api/status | jq '.role'
# Should output: "base_pi"
```

### Check From External Machine

```bash
# From your laptop/desktop
curl http://192.168.1.20:5005/api/status | jq '.role'
curl http://192.168.1.10:5006/api/status | jq '.role'
```

## Firewall Configuration

If you have firewall enabled, allow dashboard ports:

```bash
# On Robot Pi
sudo ufw allow 5005/tcp comment 'SERPENT Dashboard Robot'

# On Base Pi
sudo ufw allow 5006/tcp comment 'SERPENT Dashboard Base'
```

## Resource Usage

### Per Dashboard
- **CPU**: <1% when running
- **Memory**: ~50 MB
- **Disk**: ~10 MB

### With HDMI Auto-Start
- **With HDMI**: Dashboard runs (~50 MB)
- **Without HDMI**: Dashboard disabled (0 MB)

## Troubleshooting Dual Setup

### Robot Pi Dashboard Not Starting

```bash
# SSH to Robot Pi
ssh robotpi@192.168.1.20

# Check service
sudo systemctl status serpent-dashboard-robot

# Check HDMI
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh

# View logs
sudo journalctl -u serpent-dashboard-robot -n 50
```

### Cannot Access Remote Dashboard

```bash
# Check network connectivity
ping 192.168.1.20  # Robot Pi
ping 192.168.1.10  # Base Pi

# Check if service is running
ssh robotpi@192.168.1.20 'sudo systemctl is-active serpent-dashboard-robot'
ssh robotpi@192.168.1.10 'sudo systemctl is-active serpent-dashboard-base'

# Check if port is listening
ssh robotpi@192.168.1.20 'sudo netstat -tlnp | grep 5005'
ssh robotpi@192.168.1.10 'sudo netstat -tlnp | grep 5006'
```

### Different Data Between Dashboards

This is **normal** - each dashboard shows its local perspective:
- Robot Pi sees hardware directly
- Base Pi sees aggregated system status
- Both are correct from their viewpoint

## Recommended Setup

**For Most Users**: Run both dashboards with HDMI auto-start enabled

```
Advantages:
  ✓ Complete visibility
  ✓ Automatic resource management (HDMI-based)
  ✓ Redundant monitoring
  ✓ Flexible access (local or remote)
  ✓ Independent operation
```

**Installation Steps**:
1. ✅ Base Pi dashboard (already installed)
2. Install Robot Pi dashboard (see above)
3. Configure PSK on both (see above)
4. Test access from your computer
5. Done!

## Quick Commands

```bash
# Install on Robot Pi (run on Robot Pi)
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE && ./scripts/install_dashboard.sh robot

# Install on Base Pi (already done)
# cd /home/robotpi/Desktop/PI-HALOW-BRIDGE && ./scripts/install_dashboard.sh base

# Check both from external machine
curl http://192.168.1.20:5005/api/status | jq '.role, .health.psk_valid'
curl http://192.168.1.10:5006/api/status | jq '.role, .health.psk_valid'

# Start both manually (if needed)
ssh robotpi@192.168.1.20 'sudo systemctl start serpent-dashboard-robot'
ssh robotpi@192.168.1.10 'sudo systemctl start serpent-dashboard-base'
```

# SERPENT Robot Dashboard

A standalone web-based monitoring dashboard for the PI-HALOW-BRIDGE system. Provides real-time status visibility, log viewing, and diagnostic capabilities without modifying any existing bridge code.

## Features

- **Real-time Status Monitoring**: WebSocket-based updates every second
- **Connection Status**: Visual indicators for Control, Telemetry, Video, and Backend connections
- **E-STOP Status**: Prominent display with reason and age
- **Sensor Data**: IMU (accelerometer, gyro, quaternion) and Barometer (pressure, temperature, altitude)
- **Motor Status**: Current draw visualization for all 8 motors
- **Video Stats**: Frames sent/dropped, drop rate, camera errors
- **Log Viewer**: Filter and search systemd journal logs with live updates
- **Diagnostics**: Network tests, camera scans, service status checks, issue detection
- **Zero Touch**: No modifications to existing bridge code required
- **PSK Auto-Loading**: Automatically reads PSK from systemd configuration
- **HDMI Auto-Start**: Only starts when HDMI display is connected (saves resources when headless)

## Architecture

The dashboard works by:
1. **Primary Data Source**: Parsing structured JSON logs from systemd journal (works always)
2. **Optional Direct Inspection**: Importing bridge modules for real-time data between log intervals (if methods exist)
3. **Read-Only**: Pure monitoring, no control of robot systems

## Installation

### Quick Install

```bash
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
./scripts/install_dashboard.sh [robot|base|auto]
```

The script will:
- Install Python dependencies
- Install systemd service
- Enable and optionally start the service

### Manual Install

```bash
# Install dependencies
source venv/bin/activate
pip install -r dashboard/requirements.txt

# Copy systemd service
sudo cp dashboard/systemd/serpent-dashboard-robot.service /etc/systemd/system/
# OR for Base Pi:
# sudo cp dashboard/systemd/serpent-dashboard-base.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable serpent-dashboard-robot
sudo systemctl start serpent-dashboard-robot
```

## Access URLs

- **Robot Pi Dashboard**: http://192.168.1.20:5005
- **Base Pi Dashboard**: http://192.168.1.10:5006

## Pages

### Main Dashboard (/)
- Connection status cards for all connections
- E-STOP status with reason and age
- Sensor data (IMU, Barometer)
- Motor current visualization
- Servo position indicator
- Video stream (embedded from port 5004)
- Video statistics
- Detected issues with suggestions

### Logs (/logs)
- Service selection (Robot Bridge / Base Bridge / Backend)
- Log level filtering (ALL / INFO / WARNING / ERROR / CRITICAL)
- Line count selection (50 / 100 / 500 / 1000)
- Search/filter box
- Auto-refresh every 5 seconds
- JSON pretty-printing for structured logs

### Diagnostics (/diagnostics)
- Issue detection with troubleshooting suggestions
- Network connectivity tests (ping + port checks)
- Camera device scanning
- Service status checks
- System resource monitoring (CPU, memory, disk, temperature)

## Configuration

Environment variables (set in systemd service):

- `DASHBOARD_PORT`: Web server port (default: 5005 for robot, 5006 for base)
- `DASHBOARD_ROLE`: `robot_pi` | `base_pi` | `auto` (default: auto)
- `ENABLE_DIRECT_INSPECTION`: Import bridge modules for real-time data (default: True)
- `ENABLE_SERVICE_CONTROL`: Allow service restart actions (default: False, requires sudo)

Edit `/etc/systemd/system/serpent-dashboard-robot.service` to change settings, then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-robot
```

### PSK Authentication

The dashboard automatically inherits the PSK from the bridge service configuration:

- PSK is stored in `/etc/systemd/system/serpent-*-bridge.service.d/psk.conf`
- Dashboard reads `SERPENT_PSK_HEX` environment variable
- PSK validation status shown in dashboard health section
- No manual PSK configuration needed for dashboard

If PSK shows as invalid, verify:
```bash
# Check if PSK is configured
sudo cat /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Restart services with new PSK
sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge
sudo systemctl restart serpent-dashboard-robot
```

### HDMI Auto-Start

Dashboard automatically starts only when HDMI display is connected:

- **Enabled by default** (saves resources when headless)
- HDMI detection script: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh`
- Service starts on boot only if HDMI detected

Check HDMI status:
```bash
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
echo "Exit code: $?"  # 0 = connected, 1 = not connected
```

Disable HDMI requirement (always start):
```bash
sudo systemctl edit serpent-dashboard-base
# Add:
[Service]
ExecStartPre=
ExecStartPre=/bin/true

sudo systemctl daemon-reload
```

See `HDMI_AUTOSTART.md` for detailed documentation.

## API Endpoints

REST API for integration:

- `GET /api/status` - Aggregated system status JSON
- `GET /api/logs?service=robot&lines=100&level=INFO` - Filtered logs
- `GET /api/diagnostics/network` - Network connectivity tests
- `GET /api/diagnostics/cameras` - Camera detection
- `GET /api/diagnostics/services` - Service status checks
- `GET /api/diagnostics/resources` - System resource usage
- `GET /api/diagnostics/issues` - Issue detection with suggestions
- `POST /api/diagnostics/restart_service` - Restart service (requires ENABLE_SERVICE_CONTROL)

WebSocket:
- `ws://HOST:PORT/ws/status` - Real-time status push (1 Hz)

## Issue Detection

The dashboard automatically detects and suggests fixes for:

1. **E-STOP engaged >30s**: Suggests checking connections and clearing E-STOP
2. **Control disconnected**: Suggests network checks and port verification
3. **Control commands stale >5s**: Suggests checking if backend is sending commands
4. **Video drop rate >10%**: Suggests checking network congestion and reducing quality
5. **Camera errors >10**: Suggests checking camera connections
6. **Telemetry disconnected**: Suggests network and port checks
7. **Backend disconnected**: Suggests checking backend service status
8. **Invalid PSK**: Suggests verifying pre-shared key configuration

## Troubleshooting

### Dashboard won't start

```bash
# Check service status
sudo systemctl status serpent-dashboard-robot

# View logs
sudo journalctl -u serpent-dashboard-robot -n 50

# Check if port is already in use
sudo netstat -tlnp | grep 5005
```

### No data showing

- Verify bridge services are running: `sudo systemctl status serpent-robot-bridge`
- Check if logs are being generated: `sudo journalctl -u serpent-robot-bridge -n 20`
- Refresh the page to reconnect WebSocket

### Direct inspection warnings

Warnings like "Failed to get video stats: module 'robot_pi.video_capture' has no attribute 'get_stats'" are normal. These are optional features that fall back to log parsing (the primary data source).

To silence these warnings, set `ENABLE_DIRECT_INSPECTION=False` in the systemd service.

### Performance impact

The dashboard is designed to be lightweight:
- Target: <5% CPU usage
- Primary data source: systemd logs (no bridge modifications)
- Optional direct inspection only when available
- 1-second cache TTL to minimize overhead

## Useful Commands

```bash
# Start/stop/restart
sudo systemctl start serpent-dashboard-robot
sudo systemctl stop serpent-dashboard-robot
sudo systemctl restart serpent-dashboard-robot

# Enable/disable autostart
sudo systemctl enable serpent-dashboard-robot
sudo systemctl disable serpent-dashboard-robot

# View logs
sudo journalctl -u serpent-dashboard-robot -f

# Check status
sudo systemctl status serpent-dashboard-robot

# Test manually (without systemd)
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
source venv/bin/activate
python3 dashboard/web_server.py
```

## Development

To run in development mode:

```bash
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
source venv/bin/activate

# Set environment variables
export DASHBOARD_ROLE=robot_pi
export DASHBOARD_PORT=5005

# Run server
python3 dashboard/web_server.py
```

Access at http://localhost:5005

## Files Structure

```
dashboard/
├── __init__.py              # Package init
├── config.py                # Configuration with env vars
├── log_parser.py            # Parse journalctl JSON logs
├── status_aggregator.py     # Collect status from multiple sources
├── diagnostics.py           # Network tests, camera scans, issue detection
├── web_server.py            # Flask app with REST API + WebSocket
├── requirements.txt         # Python dependencies
│
├── static/
│   ├── css/
│   │   └── dashboard.css    # Styles
│   └── js/
│       ├── dashboard.js     # Main UI logic
│       └── diagnostics.js   # Diagnostic UI
│
├── templates/
│   ├── index.html          # Main dashboard
│   ├── logs.html           # Log viewer
│   └── diagnostics.html    # Diagnostics page
│
└── systemd/
    ├── serpent-dashboard-robot.service
    └── serpent-dashboard-base.service
```

## Dependencies

- flask==3.0.0
- flask-socketio==5.3.5
- flask-cors==4.0.0
- python-socketio==5.10.0
- psutil==5.9.6

## Design Principles

1. **Zero Touch**: No modifications to existing bridge code
2. **Read-Only**: Pure monitoring, no robot control
3. **Graceful Degradation**: Works even if bridges stopped or network down
4. **Lightweight**: <5% CPU, <50MB RAM target
5. **Real-Time**: 1 second update latency via WebSocket
6. **Actionable**: Every issue includes specific troubleshooting suggestion

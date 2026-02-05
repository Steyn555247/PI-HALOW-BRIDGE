# HDMI Auto-Start Feature

The dashboard now automatically starts only when an HDMI display is connected.

## How It Works

1. **HDMI Detection Script**: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh`
   - Checks multiple sources to detect HDMI connection:
     - `tvservice` (legacy Raspberry Pi)
     - DRM connectors (`/sys/class/drm/`)
     - `vcgencmd` (Raspberry Pi specific)
     - X11 DISPLAY environment variable
     - Framebuffer configuration

2. **Systemd Integration**:
   - `ExecStartPre=/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh`
   - Service only starts if script returns success (exit code 0)
   - If HDMI is disconnected, service won't start on boot

3. **Behavior**:
   - **On boot with HDMI**: Dashboard starts automatically
   - **On boot without HDMI**: Dashboard doesn't start (saves resources)
   - **Hot-plug**: To start after connecting HDMI, run: `sudo systemctl start serpent-dashboard-base`

## Testing HDMI Detection

### Check Current HDMI Status
```bash
/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
echo "Exit code: $?"
# Exit code 0 = HDMI connected
# Exit code 1 = No HDMI detected
```

### Test Dashboard Start Condition
```bash
# Check if service would start
sudo systemctl start serpent-dashboard-base
sudo systemctl status serpent-dashboard-base

# If HDMI not connected, you'll see:
# "Condition: start condition failed"
```

### Manual Override (Start Without HDMI)
If you need to run the dashboard without HDMI (e.g., remote access):

```bash
# Temporarily disable HDMI check
sudo systemctl edit --full serpent-dashboard-base
# Comment out the ExecStartPre line

# Or create a drop-in override
sudo systemctl edit serpent-dashboard-base
# Add:
[Service]
ExecStartPre=
ExecStartPre=/bin/true

sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-base
```

## Debugging

### Check Service Logs
```bash
sudo journalctl -u serpent-dashboard-base -n 50 | grep -i hdmi
```

### View systemd Condition Status
```bash
systemctl show serpent-dashboard-base | grep Condition
```

### Test HDMI Script Manually
```bash
# Run with verbose output
bash -x /home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
```

## Configuration

### Disable HDMI Auto-Start (Always Start)
Edit `/etc/systemd/system/serpent-dashboard-base.service`:
```ini
# Comment out these lines:
# ConditionPathExists=/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
# ExecStartPre=/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart serpent-dashboard-base
```

### Customize HDMI Detection
Edit `/home/robotpi/Desktop/PI-HALOW-BRIDGE/scripts/check_hdmi.sh` to adjust detection methods.

## Notes

- HDMI detection runs at service start time only (not continuous monitoring)
- If you connect HDMI after boot, manually start the service
- The dashboard uses minimal resources when not running (~0% CPU, 0MB RAM)
- This feature is useful for headless operation (saves resources when no display attached)

## Use Cases

1. **Development/Testing**: Dashboard only runs when monitor connected
2. **Field Deployment**: Conserve resources when operated headless
3. **Demo Mode**: Dashboard automatically appears when monitor plugged in
4. **Remote Operation**: Can still access via browser even without local display

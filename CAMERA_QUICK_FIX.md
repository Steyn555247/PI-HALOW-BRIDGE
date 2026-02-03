# Quick Start: Fix Camera Issues

## TL;DR - Do This First

### On Your Robot Pi:

```bash
# 1. Check if cameras exist
ls -la /dev/video*

# 2. Run the diagnostic tool
cd ~/pi_halow_bridge
python3 scripts/diagnose_cameras.py

# 3. If cameras exist but permissions deny, fix it:
sudo usermod -aG video $USER
# Then log out and back in

# 4. If cameras are at wrong paths, set environment variables:
export CAMERA_0=/dev/video0
export CAMERA_1=/dev/video1   # (adjust to actual devices)
export CAMERA_2=/dev/video2

# 5. If you have NO cameras connected, test with synthetic mode:
export SIM_MODE=true

# 6. Start the bridge
python3 pi_halow_bridge/robot_pi/halow_bridge.py
```

---

## What Changed (Better Camera Detection)

The Robot Pi bridge now:

✓ **Automatically detects** all available cameras on startup  
✓ **Logs clearly** which cameras work and which don't  
✓ **Falls back gracefully** to synthetic frames if real cameras fail  
✓ **Shows recommendations** when cameras are missing  

### Before:
```
❌ Failed to open camera 0
❌ No cameras initialized
❌ (silently falls back to synthetic mode)
```

### Now:
```
✓ Available cameras: ['/dev/video0', '/dev/video2']
⚠️  Camera 2 not available. Available cameras: ['/dev/video0', '/dev/video2']
✓ Successfully initialized 2/3 cameras
✓ Camera 0 initialized (config: /dev/video0, index: 0)
✓ Camera 1 initialized (config: /dev/video2, index: 2)
```

---

## Common Fixes

| Issue | Fix |
|-------|-----|
| **No /dev/video* at all** | Cameras not connected. Run `lsusb` to check USB connection |
| **Devices exist, "permission denied"** | `sudo usermod -aG video $USER` then log out/in |
| **Wrong device paths** | Set `CAMERA_0=/dev/video0`, etc. before starting |
| **Cameras sometimes work** | Try: `sudo chmod 666 /dev/video*` or `sudo modprobe uvcvideo` |
| **Want to test without cameras** | `export SIM_MODE=true` |

---

## Diagnostic Tools

### 1. **diagnose_cameras.py** (New!)
```bash
python3 pi_halow_bridge/scripts/diagnose_cameras.py
```
Comprehensive camera check with all details

### 2. **v4l2-ctl** (Linux)
```bash
# Install if needed
sudo apt-get install v4l2-utils

# List devices
v4l2-ctl --list-devices

# Test specific device
v4l2-ctl --device /dev/video0 --info
```

### 3. **OpenCV Test**
```python
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
print("✓ Camera works!" if ret else "✗ Failed")
cap.release()
```

---

## Files Modified/Created

**Modified:**
- [robot_pi/video_capture.py](robot_pi/video_capture.py) - Enhanced camera detection & logging

**Created:**
- [CAMERA_TROUBLESHOOTING.md](CAMERA_TROUBLESHOOTING.md) - Comprehensive troubleshooting guide
- [scripts/diagnose_cameras.py](scripts/diagnose_cameras.py) - Diagnostic tool

---

## Log Messages to Look For

When the bridge starts, look for these messages:

| Log | Meaning |
|-----|---------|
| `✓ Available cameras: [...]` | These devices were found and are readable |
| `✓ Successfully initialized X/Y cameras` | This many cameras are working |
| `✓ Camera 0 initialized (config: /dev/video0, index: 0)` | Camera is working |
| `✗ Camera 1 not available. Available cameras: [...]` | This camera config doesn't match any device |
| `⚠️ No cameras detected! Falling back to synthetic frames` | No real cameras, using SIM_MODE |
| `🎬 SIM_MODE: Using synthetic video frames` | Explicitly enabled synthetic mode |

---

## Next Steps

1. **Run the diagnostic** and share output if cameras still don't work
2. **Check environment variables** are set: `env | grep CAMERA`
3. **Review logs** for specific error messages
4. **Try SIM_MODE** to verify rest of system works
5. **Refer to CAMERA_TROUBLESHOOTING.md** for detailed solutions

---

## Got It Working?

If cameras start streaming:
- Check logs for: `Sent video frame: XXXX bytes`
- The Base Pi should log: `Connected to video stream` or similar
- Backend should show: `Proxying video from Base Pi`

---

## Questions?

See:
- [CAMERA_TROUBLESHOOTING.md](CAMERA_TROUBLESHOOTING.md) - Detailed troubleshooting
- [INTEGRATION.md](INTEGRATION.md) - System architecture
- [../BACKEND_VIDEO_SETUP.md](../BACKEND_VIDEO_SETUP.md) - Backend video proxy setup


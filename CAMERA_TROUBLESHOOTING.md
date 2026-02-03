# Camera Troubleshooting Guide

## Problem: Video feed not working - cameras can't open

This guide helps you diagnose and fix camera connection issues in the Pi HaLow Bridge video system.

---

## Quick Diagnosis

### 1. Check Camera Detection on Robot Pi

SSH into your Robot Pi and run:

```bash
# List all /dev/video* devices
ls -la /dev/video*

# Example output (you should see devices like):
# crw-rw----+ 1 root video 81,   0 Feb  3 10:45 /dev/video0
# crw-rw----+ 1 root video 81,   2 Feb  3 10:45 /dev/video2
# crw-rw----+ 1 root video 81,   4 Feb  3 10:45 /dev/video4
```

**Expected:** You should see `/dev/video0`, `/dev/video2`, `/dev/video4` or other consecutive even-numbered devices.

**If no devices appear:**
- USB cameras may not be connected
- Camera drivers may not be loaded
- Cameras may need to be initialized

### 2. Check Camera Permissions

```bash
# Check if your user can read video devices
groups $USER

# You should see "video" in the output:
# user adm dialout cdrom sudo audio video

# If not in video group, add yourself:
sudo usermod -aG video $USER
# You'll need to log out and back in
```

### 3. Test Camera Directly with v4l2-ctl

```bash
# Install v4l2-utils if needed
sudo apt-get install v4l2-utils

# List all video devices with details
v4l2-ctl --list-devices

# Test specific camera
v4l2-ctl --device /dev/video0 --info

# Check if camera is being used by another process
lsof /dev/video0
```

### 4. Check Camera Module is Loaded

```bash
# For USB cameras (UVC)
sudo modprobe uvcvideo

# Check if loaded
lsmod | grep uvc

# For ELP cameras specifically
sudo modprobe v4l2_common
```

---

## Common Issues & Solutions

### Issue 1: No /dev/video* Devices

**Symptoms:**
- `ls /dev/video*` shows nothing
- Error: "No such file or directory"

**Possible causes:**
- USB cameras not connected
- Camera drivers not installed
- Camera module not loaded

**Solutions:**

```bash
# 1. Check USB connection
lsusb | grep -i "camera\|video\|usb\|elp"

# 2. Load camera drivers
sudo modprobe uvcvideo
sudo modprobe v4l2_common

# 3. Check dmesg for errors
dmesg | tail -20

# 4. Restart video subsystem
sudo service media-server restart

# 5. Unplug cameras, wait 5 seconds, plug back in
# Then check again
ls /dev/video*
```

### Issue 2: /dev/video Devices Exist But Can't Open

**Symptoms:**
- Logs show: "Failed to open camera 0 (config: /dev/video0, index: 0)"
- Devices exist but permission denied

**Solutions:**

```bash
# 1. Check permissions
ls -la /dev/video0
# Should show: crw-rw---- (666 or 664 would be ideal)

# 2. Fix permissions (temporary)
sudo chmod 666 /dev/video*

# 3. Add user to video group (permanent)
sudo usermod -aG video $(whoami)
# Log out and back in

# 4. Set udev rules (permanent)
sudo nano /etc/udev/rules.d/99-video.rules
# Add: SUBSYSTEM=="video4linux", MODE="0666"
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Issue 3: Cameras Detected But Wrong Device Paths

**Symptoms:**
- Bridge logs show: "No cameras initialized"
- Logs show detection found cameras but config points to wrong paths
- Example: Expected `/dev/video0`, `/dev/video2`, `/dev/video4` but have `/dev/video0`, `/dev/video1`

**Solutions:**

**Option A: Update Environment Variables**

```bash
# Set custom camera paths before running the bridge
export CAMERA_0=/dev/video0
export CAMERA_1=/dev/video1
export CAMERA_2=/dev/video2

# Or discover which ones are working
for i in 0 1 2 3 4 5; do
  echo -n "/dev/video$i: "
  v4l2-ctl --device /dev/video$i --info 2>/dev/null | head -1 || echo "Not accessible"
done
```

**Option B: Update config.py**

Edit [robot_pi/config.py](robot_pi/config.py) and change:

```python
# OLD:
CAMERA_DEVICES = [
    os.getenv('CAMERA_0', '/dev/video0'),
    os.getenv('CAMERA_1', '/dev/video2'),
    os.getenv('CAMERA_2', '/dev/video4')
]

# NEW (for example, if your cameras are 0,1,2):
CAMERA_DEVICES = [
    os.getenv('CAMERA_0', '/dev/video0'),
    os.getenv('CAMERA_1', '/dev/video1'),
    os.getenv('CAMERA_2', '/dev/video2')
]
```

### Issue 4: Camera Opens But No Frames Captured

**Symptoms:**
- Logs show "✓ Camera 0 initialized" but no frames being sent
- Errors like "Failed to read from camera 0"

**Solutions:**

```bash
# 1. Test with ffmpeg
ffmpeg -f v4l2 -i /dev/video0 -t 1 test.jpg

# 2. Test with python and opencv directly
python3 << 'EOF'
import cv2
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    print("✓ Camera works!")
    print(f"  Resolution: {frame.shape[1]}x{frame.shape[0]}")
else:
    print("✗ Failed to read frame")
cap.release()
EOF

# 3. Try with different backends
python3 << 'EOF'
import cv2
for backend_name, backend_id in [('V4L2', cv2.CAP_V4L2), 
                                  ('AUTO', cv2.CAP_DSHOW),
                                  ('DEFAULT', cv2.CAP_ANY)]:
    cap = cv2.VideoCapture(0, backend_id)
    if cap.isOpened():
        print(f"✓ {backend_name} backend works")
        cap.release()
    else:
        print(f"✗ {backend_name} backend failed")
EOF
```

---

## SIM_MODE: Test Without Real Cameras

If you don't have cameras connected or want to test the system, use **SIM_MODE**:

```bash
# Enable synthetic video frames
export SIM_MODE=true

# Start the robot Pi bridge
cd pi_halow_bridge/robot_pi
python3 halow_bridge.py

# The system will generate synthetic test frames with:
# - Gradient backgrounds that pulse
# - Frame counter
# - Timestamp
# - Current camera ID
```

This is useful for:
- Testing the entire system without hardware
- Verifying network connectivity
- Debugging video streaming pipeline
- Development and integration testing

To disable: `export SIM_MODE=false`

---

## Robot Pi Bridge Startup Sequence

When you start the Robot Pi bridge, it will:

1. **Scan for available cameras** (all /dev/video* devices)
2. **Attempt to initialize configured cameras** (CAMERA_0, CAMERA_1, CAMERA_2)
3. **Log success/failure** for each camera
4. **Start video streaming** (real or synthetic)

Check the logs:

```bash
# During startup, look for these lines:
# ✓ Available cameras: ['/dev/video0', '/dev/video2']
# ✓ Successfully initialized 2/3 cameras
# ✓ Camera 0 initialized (config: /dev/video0, index: 0)
# ✓ Camera 1 initialized (config: /dev/video2, index: 2)
# ✗ Camera 2 not available. Available cameras: ['/dev/video0', '/dev/video2']
```

---

## Complete Diagnostic Script

Save this as `diagnose_cameras.sh`:

```bash
#!/bin/bash

echo "========== CAMERA DIAGNOSTIC REPORT =========="
echo "Date: $(date)"
echo

echo "1. System Info"
echo "  OS: $(uname -s)"
echo "  Kernel: $(uname -r)"
echo

echo "2. Video Devices"
echo -n "  Found: "
ls /dev/video* 2>/dev/null | wc -l
echo "  Devices:"
ls -la /dev/video* 2>/dev/null || echo "    (none)"
echo

echo "3. Video Group Membership"
echo "  Groups: $(groups $USER)"
echo

echo "4. Camera Details"
which v4l2-ctl > /dev/null && {
    v4l2-ctl --list-devices
} || echo "  v4l2-ctl not installed (install: sudo apt-get install v4l2-utils)"
echo

echo "5. Loaded Kernel Modules"
echo "  UVC: $(lsmod | grep -c uvcvideo) module(s) loaded"
echo "  V4L2: $(lsmod | grep -c v4l2) module(s) loaded"
echo

echo "6. USB Devices"
lsusb | grep -i "camera\|video" || echo "  No obvious camera USB devices detected"
echo

echo "7. Dmesg Errors (last 10 lines)"
dmesg | grep -i "video\|camera\|uvc\|usb" | tail -10 || echo "  None"
echo

echo "========== END DIAGNOSTIC =========="
```

Run with:
```bash
chmod +x diagnose_cameras.sh
./diagnose_cameras.sh
```

---

## Next Steps

1. **Run the diagnostic script** above and share the output
2. **Check environment variables** are set correctly:
   ```bash
   env | grep CAMERA
   ```
3. **Review logs** from the Robot Pi bridge for specific errors
4. **Try SIM_MODE** to verify the rest of the system works
5. **Test individual cameras** with v4l2-ctl or ffmpeg

---

## Related Documentation

- [INTEGRATION.md](INTEGRATION.md) - Bridge architecture and integration
- [BACKEND_VIDEO_SETUP.md](../BACKEND_VIDEO_SETUP.md) - Backend video configuration
- [README.md](robot_pi/README.md) - Robot Pi setup instructions


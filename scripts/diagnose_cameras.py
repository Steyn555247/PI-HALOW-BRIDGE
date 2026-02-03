#!/usr/bin/env python3
"""
Camera Diagnostic Tool for Pi HaLow Bridge

Usage:
    python3 diagnose_cameras.py

This script:
1. Detects available video devices
2. Tests each device with OpenCV
3. Provides recommendations for fixes
"""

import os
import sys
import subprocess
import platform
import glob

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)

def print_section(text):
    print(f"\n► {text}")
    print("-" * 60)

def run_command(cmd, silent=False):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception as e:
        if not silent:
            print(f"  Error: {e}")
        return None

def check_video_devices():
    """Check for /dev/video* devices"""
    print_section("Video Device Detection")
    
    IS_LINUX = platform.system() == 'Linux'
    
    if IS_LINUX:
        devices = sorted(glob.glob('/dev/video*'))
        if devices:
            print(f"✓ Found {len(devices)} device(s):")
            for dev in devices:
                stat = os.stat(dev)
                mode = oct(stat.st_mode)[-3:]
                readable = "✓" if os.access(dev, os.R_OK) else "✗"
                print(f"  {readable} {dev} (permissions: {mode})")
        else:
            print("✗ No /dev/video* devices found")
            print("  → Check if USB cameras are connected")
            print("  → Run: lsusb | grep -i camera")
    else:
        print(f"  Running on {platform.system()} - video device detection works differently")
        print("  Will test camera indices 0-9 instead")

def check_video_group():
    """Check video group membership"""
    print_section("Permissions & Video Group")
    
    user = os.getenv('USER', 'unknown')
    groups_output = run_command(f"groups {user}")
    
    if groups_output:
        has_video = 'video' in groups_output
        status = "✓" if has_video else "✗"
        print(f"{status} User '{user}' in groups: {groups_output}")
        if not has_video:
            print("  → Add to video group: sudo usermod -aG video $USER")
            print("  → Then log out and back in")
    else:
        print("✗ Could not check group membership")

def check_kernel_modules():
    """Check if video kernel modules are loaded"""
    print_section("Kernel Modules")
    
    IS_LINUX = platform.system() == 'Linux'
    if not IS_LINUX:
        print(f"  Skipping on {platform.system()}")
        return
    
    modules = {
        'uvcvideo': 'USB Video Class (webcam support)',
        'v4l2_common': 'Video for Linux 2 Common',
        'videobuf2_core': 'Video buffer framework'
    }
    
    for module, description in modules.items():
        count = run_command(f"lsmod | grep -c {module}", silent=True)
        if count and int(count) > 0:
            print(f"✓ {module:20} ({description})")
        else:
            print(f"✗ {module:20} - NOT LOADED")
            print(f"  → Load it: sudo modprobe {module}")

def check_cameras_with_opencv():
    """Test each camera with OpenCV"""
    print_section("OpenCV Camera Tests")
    
    try:
        import cv2
    except ImportError:
        print("✗ OpenCV not installed")
        print("  → Install: pip install opencv-python")
        return
    
    # Test indices 0-9 on all platforms
    working_cameras = []
    
    for idx in range(10):
        try:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    working_cameras.append(idx)
                    print(f"✓ Camera {idx}: {w}x{h} (working)")
                else:
                    print(f"⚠ Camera {idx}: Opens but frame read failed")
                cap.release()
            else:
                # Don't print for non-existent cameras on Windows/Mac
                pass
        except Exception as e:
            pass
    
    if not working_cameras:
        print("✗ No working cameras detected")
    else:
        print(f"\n✓ Found {len(working_cameras)} working camera(s): {working_cameras}")

def check_v4l2_ctl():
    """Check v4l2-ctl if available"""
    print_section("v4l2-ctl Camera Info")
    
    if not run_command("which v4l2-ctl", silent=True):
        print("✗ v4l2-ctl not installed")
        print("  → Install: sudo apt-get install v4l2-utils")
        return
    
    output = run_command("v4l2-ctl --list-devices", silent=True)
    if output:
        print(output)
    else:
        print("  (no output)")

def check_current_config():
    """Check current configuration"""
    print_section("Current Bridge Configuration")
    
    config_vars = {
        'CAMERA_0': '/dev/video0',
        'CAMERA_1': '/dev/video2',
        'CAMERA_2': '/dev/video4',
        'NUM_CAMERAS': '3',
        'CAMERA_WIDTH': '640',
        'CAMERA_HEIGHT': '480',
        'CAMERA_FPS': '10',
        'SIM_MODE': 'false'
    }
    
    print("Current environment variables:")
    for var, default in config_vars.items():
        current = os.getenv(var, f"{default} (default)")
        print(f"  {var:20} = {current}")

def main():
    print_header("PI HALOW BRIDGE - CAMERA DIAGNOSTIC TOOL")
    print(f"\nSystem: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")
    
    # Run all checks
    check_video_devices()
    check_video_group()
    check_kernel_modules()
    check_cameras_with_opencv()
    check_v4l2_ctl()
    check_current_config()
    
    # Summary and recommendations
    print_header("RECOMMENDATIONS")
    print("""
If cameras aren't working:

1. ✓ No /dev/video* devices?
   → Check USB connection
   → Run: sudo modprobe uvcvideo
   → Run: dmesg | tail -20 to see errors

2. ✓ Devices exist but "not readable"?
   → Add yourself to video group: sudo usermod -aG video $USER
   → Then log out and back in

3. ✓ Device exists but OpenCV can't open it?
   → Check if another process is using it: lsof /dev/videoX
   → Try different OpenCV backend
   → Run: v4l2-ctl --device /dev/videoX --info

4. ✓ Want to test without cameras?
   → Use SIM_MODE=true
   → Export before running: export SIM_MODE=true

5. ✓ Wrong camera devices?
   → Update CAMERA_0, CAMERA_1, CAMERA_2 environment variables
   → Or edit robot_pi/config.py CAMERA_DEVICES list
""")
    
    print(f"\n{'='*60}")
    print("For more help, see: pi_halow_bridge/CAMERA_TROUBLESHOOTING.md")
    print('='*60 + "\n")

if __name__ == '__main__':
    main()

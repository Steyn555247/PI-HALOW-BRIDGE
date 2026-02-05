#!/bin/bash
#
# Check if HDMI display is connected
# Returns 0 if connected, 1 if not connected
#
# Works on Raspberry Pi by checking video output status

# Method 1: Try tvservice (legacy Raspberry Pi)
if command -v tvservice &> /dev/null; then
    # tvservice -s returns status like:
    # "state 0x2 [TV is off]" or "state 0x120002 [HDMI DMT...]"
    status=$(tvservice -s 2>/dev/null)
    if echo "$status" | grep -qE "HDMI|DVI"; then
        exit 0  # HDMI connected
    fi
fi

# Method 2: Check DRM (modern Linux)
# Check if any display is connected via /sys/class/drm/
for connector in /sys/class/drm/card*/status; do
    if [ -f "$connector" ]; then
        status=$(cat "$connector")
        if [ "$status" = "connected" ]; then
            exit 0  # Display connected
        fi
    fi
done

# Method 3: Check vcgencmd (Raspberry Pi specific)
if command -v vcgencmd &> /dev/null; then
    # Check if display is detected
    display_status=$(vcgencmd display_power 2>/dev/null)
    if echo "$display_status" | grep -q "display_power=1"; then
        exit 0  # Display active
    fi
fi

# Method 4: Check for X11 DISPLAY environment
if [ -n "$DISPLAY" ]; then
    exit 0  # X11 session exists, assume display present
fi

# Method 5: Check for active framebuffer
if [ -c /dev/fb0 ] && command -v fbset &> /dev/null; then
    # If framebuffer is configured with non-zero resolution, display likely present
    if fbset -fb /dev/fb0 2>/dev/null | grep -q "mode"; then
        exit 0
    fi
fi

# No display detected
exit 1

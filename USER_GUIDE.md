# Serpent Robot Control System - User Guide

> **For operators of the Serpent rope-climbing robot system**

---

# Getting Started

## What You Need

- **Robot** - The Serpent rope-climbing robot (with Robot Pi inside)
- **Hub** - The base station box (with Base Pi inside)
- **TrimUI Controller** - Your handheld TrimUI Smart Pro S with the Serpent app installed

---

# Step-by-Step: Powering On the System

Follow these steps in order. **Timing is important** - the wireless link takes time to establish.

## Step 1: Turn On the Robot

1. Connect power to the robot
2. The Robot Pi inside will boot up
3. **Wait about 1 minute** for the operating system to fully boot

> The robot's E-STOP is automatically engaged on startup - this is normal and safe.

## Step 2: Turn On the Hub (Base Station)

1. Connect power to the hub/base station box
2. The Base Pi inside will boot up
3. **Wait about 1 minute** for the operating system to fully boot

## Step 3: Wait for the Wireless Link

**This is the longest wait - be patient!**

The HaLow wireless radios need time to find each other and establish a secure connection.

| Time After Both Powered On | What's Happening |
|---------------------------|------------------|
| 0-30 seconds | Radios initializing |
| 30-90 seconds | Radios searching for each other |
| 90-180 seconds | Link establishing, authenticating |
| **2-3 minutes** | **Link ready** |

**Total wait time from power on: approximately 2-3 minutes**

## Step 4: Turn On the TrimUI Controller

1. Power on your TrimUI Smart Pro S
2. Wait for it to boot to the home screen

## Step 5: Connect to the SerpentBase WiFi

1. On the TrimUI, go to **Settings**
2. Go to **WiFi**
3. Find and connect to the network called **"SerpentBase"**
4. **Important:** It will show "No Internet" or "Connected, no internet" - **this is normal!** The robot network is isolated and doesn't have internet access.
5. **Wait 10-30 seconds** for the WiFi connection to stabilize

## Step 6: Open the Serpent App

1. Go back to the home screen
2. Open the **Serpent** app
3. The app will show "Searching for Serpent backend..."
4. **Wait 10-30 seconds** for auto-discovery

### If Auto-Connect Works:
- You'll see "Connected!"
- The app will switch to the main control screen with video feed
- You're ready to operate!

### If Auto-Connect Fails:
The app will show "Could not find backend" with three options:

| Option | When to Use |
|--------|-------------|
| **Retry Auto-Discovery** | Try this first - sometimes it just needs another attempt |
| **Enter IP Manually** | If retry doesn't work, enter: `192.168.1.10` |
| **Demo Mode** | Only for testing the app without the robot |

**To enter the IP manually:**
1. Select "Enter IP Manually"
2. Type: `192.168.1.10`
3. Press Connect

---

# The TrimUI App Interface

## Main Screen Layout

When connected, you'll see:

```
┌────────────────────────────────────────────────────────────────┐
│ [SERPENT logo]                              [CONTROLLER badge] │
│                                                                │
│                                             ┌────────────────┐ │
│                                             │ Telemetry      │ │
│              LIVE VIDEO FEED                │ • Voltage: 12V │ │
│              (from robot cameras)           │ • Status: OK   │ │
│                                             │ • RTT: 45ms    │ │
│                                             └────────────────┘ │
│                                                                │
│ ┌──────────────┐                          ┌──────────────────┐│
│ │ Camera: 1/3  │                          │ Control Buttons  ││
│ └──────────────┘                          └──────────────────┘│
└────────────────────────────────────────────────────────────────┘
```

### Top Bar
- **SERPENT logo** - Shows you're in the Serpent app
- **CONTROLLER badge** - Confirms controller is detected

### Video Feed
- Takes up most of the screen
- Shows live video from the robot's cameras
- Updates at approximately 10 frames per second

### Telemetry Panel (Right Side)
Shows real-time robot status:
- **Voltage** - Battery level
- **Connection status** - Connected/Disconnected
- **RTT** - Round-trip time (latency) in milliseconds

### Bottom Bar
- **Camera selector** - Shows which camera is active (1, 2, or 3)
- **Control buttons** - On-screen buttons (you can also use physical buttons)

---

# Controller Button Guide

## Button Layout on TrimUI

```
              ┌─────────────────────────────────────────┐
              │           [L1]          [R1]            │
              │       Prev Camera    Next Camera        │
              │                                         │
              │  [L2]                          [R2]     │
              │  Clamp                         Clamp    │
              │  Close                         Open     │
              │                                         │
              │      ┌───┐                   [Y]        │
              │  ┌───┤ ↑ ├───┐           EMERGENCY     │
              │  │ ← │   │ → │            STOP         │
              │  └───┤ ↓ ├───┘                         │
              │      └───┘             [X]     [B]     │
              │     D-Pad                              │
              │   (Movement)            [A]            │
              │                                         │
              │    ○               ○                    │
              │   Left            Right                 │
              │   Stick           Stick                 │
              │                                         │
              │         [SELECT]    [START]             │
              │            └───── Menu ─────┘           │
              └─────────────────────────────────────────┘
```

## Button Functions

### Emergency Stop - Y Button (MOST IMPORTANT!)

| Action | How To |
|--------|--------|
| **ACTIVATE E-STOP** | Press Y once - robot stops immediately |
| **DEACTIVATE E-STOP** | Hold Y for 5 seconds continuously |

When E-STOP is active:
- Screen shows large red "EMERGENCY STOP" overlay
- ALL controls are blocked except Y button
- Text shows "Hold Y for 5 seconds to release"

> **Safety:** If you release Y before 5 seconds, the deactivation is cancelled and E-STOP stays active.

### Camera Controls

| Button | Function |
|--------|----------|
| **L1** | Previous camera (3 → 2 → 1 → 3) |
| **R1** | Next camera (1 → 2 → 3 → 1) |

The robot has 3 cameras. Use L1/R1 to cycle through them.

### Clamp/Claw Controls

| Button | Function |
|--------|----------|
| **L2** | Close the clamp |
| **R2** | Open the clamp |

### Menu

| Button | Function |
|--------|----------|
| **SELECT** | Open system menu |
| **START** | Open system menu |

### D-Pad (Movement)

| Button | Function |
|--------|----------|
| **Up** | Robot up (climb) |
| **Down** | Robot down (descend) |
| **Left** | Robot left (traverse) |
| **Right** | Robot right (traverse) |

### Face Buttons

| Button | Function |
|--------|----------|
| **A** | Chainsaw on (if configured) |
| **B** | Right chainsaw select |
| **X** | Left chainsaw select |
| **Y** | **EMERGENCY STOP** |

---

# The System Menu

Press **SELECT** or **START** to open the menu.

## Menu Navigation

| Control | Action |
|---------|--------|
| **D-Pad Up/Down** | Move selection up/down |
| **A button** | Select highlighted option |
| **B button** | Close menu / Go back |

## Menu Options

### 1. Calibrate Controller
Opens the controller calibration screen. Use this if buttons seem to be mapped incorrectly.

### 2. Reconnect to Backend
Disconnects and reconnects to the robot system. Use this if you lose connection.

**What happens:**
1. Shows "RECONNECTING..."
2. Disconnects from current connection
3. Attempts to find the backend again
4. Shows "CONNECTED" if successful, or "RECONNECT FAILED" if not

### 3. Camera Config
Adjust camera settings (reserved for future use).

### 4. Sensor Dashboard
Opens a detailed view of all sensor data:
- IMU (orientation, acceleration)
- Barometer (pressure, altitude, temperature)
- Motor currents

### 5. About
Shows version information and credits:
- App version
- Serpent Robotics information

---

# Operating the Robot

## Before Operating

1. **Verify connection** - Telemetry panel shows data updating
2. **Check video** - You can see the live feed
3. **E-STOP is active** - On first connection, E-STOP is engaged (normal)

## Clearing E-STOP to Enable Movement

When you first connect, the robot's E-STOP is engaged (all motors stopped). To enable movement:

1. Make sure the robot is in a safe position
2. **Hold the Y button for 5 full seconds**
3. The red E-STOP overlay will disappear
4. You can now control the robot

## Basic Operations

### Climbing Up
1. Ensure E-STOP is cleared
2. Press and hold **D-Pad Up**
3. Robot climbs up the rope
4. Release to stop

### Descending
1. Press and hold **D-Pad Down**
2. Robot descends
3. Release to stop

### Traversing Left/Right
1. Press and hold **D-Pad Left** or **D-Pad Right**
2. Robot moves sideways
3. Release to stop

### Operating the Clamp
- **R2** to open the clamp
- **L2** to close the clamp

### Switching Camera View
- **R1** for next camera
- **L1** for previous camera

## Emergency Stop

**Press Y immediately if anything goes wrong!**

The E-STOP:
- Stops all motors instantly
- Cannot be accidentally released (requires 5-second hold)
- Is also triggered automatically if connection is lost

---

# Connection Status Indicators

## On the TrimUI App

### Telemetry Panel Colors/Status
- **Data updating** = Connected and working
- **Data frozen** = Possible connection issue
- **"Connection Lost" overlay** = Disconnected, attempting to reconnect

### Video Feed
- **Live video showing** = Video connection working
- **Black/frozen image** = Video connection issue
- **"No Video" text** = Camera not available

## Automatic E-STOP Triggers

The robot will automatically engage E-STOP if:

| Trigger | What Happened |
|---------|---------------|
| **Connection lost** | WiFi disconnected or out of range |
| **No commands for 5 seconds** | Network issue or app frozen |
| **Startup default** | Robot just powered on |

This is a **safety feature** - the robot won't move uncontrolled.

---

# Troubleshooting

## App Won't Connect

### "Could not find backend" on startup

**Check the basics:**
1. Is the hub powered on? (wait 2-3 minutes after power on)
2. Is your TrimUI connected to "SerpentBase" WiFi?
3. Does WiFi show "Connected" (even if it says "no internet")?

**Try these fixes:**
1. Select "Retry Auto-Discovery" and wait
2. If that fails, select "Enter IP Manually" and type: `192.168.1.10`
3. If still failing, restart the hub and wait 3 minutes

### Connected but video not showing

1. Try switching cameras with L1/R1
2. Open menu → Reconnect to Backend
3. Check if the hub's video service is running (see Advanced Troubleshooting)

### Connected but controls not working

1. **Check E-STOP** - Is the red overlay showing? Hold Y for 5 seconds to clear it
2. **Check telemetry** - Is data updating? If frozen, try reconnecting
3. **Try the menu** - If menu opens with SELECT, the controller is working

## Connection Lost During Operation

**What happens:**
1. Screen shows "Connection Lost" overlay
2. E-STOP automatically engages on the robot
3. App attempts to reconnect automatically

**What to do:**
1. Don't panic - robot is safely stopped
2. Wait for "Attempting to reconnect..." to succeed
3. If it doesn't reconnect, check WiFi is still connected to SerpentBase
4. Press "Retry Connection" button on screen

## E-STOP Won't Clear

**Requirements to clear E-STOP:**
- Must be connected to the robot
- Connection must be fresh (less than 1.5 seconds old)
- Must hold Y for full 5 seconds without releasing

**If it still won't clear:**
1. Open menu → Reconnect to Backend
2. Wait for connection confirmation
3. Immediately hold Y for 5 seconds

## High Latency (Sluggish Controls)

Check the RTT value in the telemetry panel:

| RTT | Quality | Action |
|-----|---------|--------|
| < 50ms | Excellent | None needed |
| 50-100ms | Good | None needed |
| 100-200ms | Acceptable | Move closer to hub if possible |
| > 200ms | Poor | Check for interference, move closer |

## Video Stuttering or Dropping

This usually means network bandwidth issues:
1. Move the hub closer to the robot
2. Move yourself closer to the hub
3. Check for WiFi interference (other devices, microwave, etc.)

---

# Quick Reference Card

## Startup Sequence (Total: ~5 minutes)
1. Power on robot → wait 1 min
2. Power on hub → wait 1 min
3. Wait for link → **2-3 minutes**
4. Power on TrimUI
5. Connect to "SerpentBase" WiFi (shows "no internet" - OK!)
6. Open Serpent app → wait 10-30 sec
7. If needed, enter IP: `192.168.1.10`

## Essential Controls
| Button | Action |
|--------|--------|
| **Y** | E-STOP (press once to stop, hold 5s to clear) |
| **D-Pad** | Movement (up/down/left/right) |
| **L1/R1** | Switch cameras |
| **L2/R2** | Close/Open clamp |
| **SELECT** | Open menu |

## If Something Goes Wrong
1. **Press Y immediately** - activates E-STOP
2. Robot stops all motors
3. Assess the situation
4. When safe, hold Y for 5 seconds to resume

## Key IP Address
- **Backend IP:** `192.168.1.10`
- **WiFi Network:** `SerpentBase`

---

# For Technicians: Debug Dashboard

The web dashboard is available for debugging and diagnostics. It is NOT meant for normal operation - use the TrimUI app instead.

## Accessing the Dashboard

1. Connect a computer to the SerpentBase WiFi network
2. Open a web browser
3. Go to: `http://192.168.1.10:5000`

## Dashboard Features

The dashboard shows:
- **Connection status** for all 3 channels (control, telemetry, video)
- **E-STOP status** and manual clear/engage buttons
- **Detailed telemetry** including all sensor data
- **Motor currents** for diagnostics
- **Motor test controls** (on Robot Pi dashboard only)

## When to Use the Dashboard

- Diagnosing connection issues
- Checking sensor data in detail
- Testing individual motors
- Verifying system status before operation

## Dashboard E-STOP Controls

The dashboard has two buttons:
- **Clear E-STOP** - Requires confirmation dialog
- **Emergency Stop** - Immediately engages E-STOP

---

# System Timing Summary

| Event | Wait Time |
|-------|-----------|
| Robot Pi boot | ~60 seconds |
| Base Pi boot | ~60 seconds |
| HaLow link establishment | **2-3 minutes** |
| TrimUI WiFi connection | 10-30 seconds |
| App auto-discovery | 10-30 seconds |
| E-STOP watchdog timeout | 5 seconds (no commands = auto E-STOP) |
| E-STOP clear hold time | 5 seconds |
| Startup grace period | 30 seconds (watchdog inactive) |

---

# Safety Summary

1. **E-STOP is your friend** - Press Y immediately if anything seems wrong
2. **Connection loss = automatic stop** - Robot won't run away if you disconnect
3. **5-second rule** - Must hold Y for 5 seconds to clear E-STOP (prevents accidents)
4. **Startup = stopped** - Robot always starts with E-STOP engaged
5. **No internet is normal** - The SerpentBase network is isolated for safety

---

**Version:** 1.0
**Last Updated:** February 2026
**For:** Serpent Robotics Operators

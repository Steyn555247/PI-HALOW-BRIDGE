# Serpent Robot Control System - User Guide

> **For operators of the Serpent rope-climbing robot system**

---

# ⚠️ SAFETY INFORMATION - READ FIRST

## Critical Safety Rules

### 🚨 Emergency Stop Systems

The Serpent robot has **multiple emergency stop methods**:

1. **TrimUI Controller Y Button**
   - Press Y once to immediately engage E-STOP
   - Stops all motors and chainsaws instantly
   - Always accessible during operation

2. **Physical E-STOP Button on Robot**
   - Located on the robot chassis
   - Can be pressed at any time, even if wireless connection is lost
   - Immediately cuts power to all actuators
   - **This is your primary emergency backup**

3. **Hub Battery Disconnection**
   - As a last resort, disconnect the battery from the hub
   - This will break the wireless link and trigger automatic E-STOP on the robot
   - Only use if all other methods fail

### 🚷 Operator Positioning - CRITICAL

**NEVER stand or position yourself directly below the robot during operation.**

Hazards if positioned below:
- Falling debris or equipment
- Robot malfunction or power loss causing drop
- Chainsaw debris or sawdust
- Accidental release of payload
- Equipment falling during maintenance

**Safe positioning:**
- Stand to the side of the robot's path
- Maintain at least 3 meters (10 feet) lateral distance
- Keep clear line of sight to the robot
- Position yourself with an escape route

### 🔍 Pre-Operation Safety Checklist

Before **every** operation, verify:

- [ ] **Rope/anchor inspection** - Check for wear, fraying, or damage
- [ ] **Robot physical inspection** - No loose parts, damaged components, or leaks
- [ ] **Battery voltage** - Minimum 11.5V for operation (check telemetry panel)
- [ ] **Physical E-STOP test** - Press and verify it stops motors
- [ ] **Clear operation area** - No personnel below or in drop zone
- [ ] **Weather conditions** - No rain, high winds, or lightning
- [ ] **Communication check** - Verify video feed and telemetry updating
- [ ] **Load limits** - Do not exceed rated payload capacity

### ⚡ Operational Hazards

**Be aware of these hazards during operation:**

| Hazard | Risk | Mitigation |
|--------|------|------------|
| **Chainsaw operation** | Cutting, debris, kickback | Keep clear, wear eye protection, never reach near chainsaws |
| **High voltage** | Electric shock | Never open robot or hub enclosures while powered |
| **Moving parts** | Pinch points, entanglement | Keep hands clear of motors, pulleys, and actuators |
| **Falling objects** | Impact injury | Never stand below, secure loose items |
| **Battery failure** | Fire, chemical leak | Use only specified batteries, inspect before use |
| **Communication loss** | Uncontrolled robot | E-STOP auto-engages, but verify before approaching |
| **Rope failure** | Robot fall | Inspect rope before operation, use rated rope |

### 🌤️ Environmental Limitations

**Do NOT operate in these conditions:**

- Rain or wet conditions (water damage to electronics)
- Wind speeds above 25 mph (loss of control)
- Temperatures below -10°C or above 45°C
- Lightning or thunderstorm conditions
- Low visibility (fog, darkness without adequate lighting)
- Near power lines or electromagnetic interference sources

### 🔧 Maintenance Safety

- Always disconnect power before maintenance
- Engage physical E-STOP during work
- Use lockout/tagout procedures for team operations
- Never bypass safety interlocks
- Keep spare batteries stored safely (away from metal objects)

### 👥 Personnel Requirements

- Minimum 2 people for field operations (operator + spotter)
- All personnel must read this safety section
- Maintain radio/phone communication with team
- Know location of first aid kit and fire extinguisher
- Have emergency contact numbers readily available

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
              │  Chainsaw 1                 Chainsaw 2  │
              │  On                            On       │
              │                                         │
              │      ┌───┐                   [Y]        │
              │  ┌───┤ ↑ ├───┐           EMERGENCY     │
              │  │ ← │   │ → │            STOP         │
              │  └───┤ ↓ ├───┘                         │
              │      └───┘             [X]     [B]     │
              │     D-Pad                              │
              │   (Movement)            [A]            │
              │                                      Claw │
              │    ○               ○                    │
              │   Left            Right                 │
              │   Stick           Stick                 │
              │  (Chainsaw 1)   (Chainsaw 2)            │
              │                                         │
              │         [SELECT]    [START]             │
              │         Sensors       Menu              │
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

### Chainsaw Controls

| Button | Function |
|--------|----------|
| **L2** | Chainsaw 1 On (hold to run) |
| **R2** | Chainsaw 2 On (hold to run) |

### Menu

| Button | Function |
|--------|----------|
| **SELECT** | Open sensor dashboard |
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
| **A** | Claw open |
| **B** | (Unmapped) |
| **X** | (Unmapped) |
| **Y** | **EMERGENCY STOP** |

### Analog Sticks

| Control | Function |
|---------|----------|
| **Left Stick Up** | Chainsaw 1 actuate up |
| **Left Stick Down** | Chainsaw 1 actuate down |
| **Right Stick Up** | Chainsaw 2 actuate up |
| **Right Stick Down** | Chainsaw 2 actuate down |

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
2. Robot descends down the rope
3. Release to stop

### Traversing Left/Right
1. Press and hold **D-Pad Left** or **D-Pad Right**
2. Robot moves sideways
3. Release to stop

### Operating the Claw
- **A button** to open the claw

### Operating the Chainsaws
- **L2** to turn on Chainsaw 1 (hold to run)
- **R2** to turn on Chainsaw 2 (hold to run)
- **Left Stick Up/Down** to actuate Chainsaw 1 position
- **Right Stick Up/Down** to actuate Chainsaw 2 position

### Switching Camera View
- **R1** for next camera
- **L1** for previous camera

## Emergency Stop

**Multiple ways to stop the robot in an emergency:**

### 1. Controller Y Button (Primary)
**Press Y immediately if anything goes wrong!**
- Stops all motors and chainsaws instantly
- Cannot be accidentally released (requires 5-second hold to clear)
- Works as long as wireless connection is active

### 2. Physical E-STOP Button (Backup)
**Red button on the robot chassis**
- Works even if wireless connection is lost
- Immediately cuts power to all actuators
- Must be manually reset on the robot before operation can resume
- **Test this button before every operation**

### 3. Hub Battery Disconnect (Last Resort)
- Disconnect battery from hub base station
- Breaks wireless link, triggering automatic E-STOP on robot
- Only use if controller and physical E-STOP are inaccessible

### Automatic E-STOP Triggers:
- Connection lost to controller
- No commands received for 5 seconds
- System startup (default state)

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
| **D-Pad Up** | Climb up |
| **D-Pad Down** | Descend down |
| **D-Pad Left/Right** | Traverse left/right |
| **L1/R1** | Switch cameras |
| **L2/R2** | Chainsaw 1/2 On (hold to run) |
| **A** | Claw open |
| **SELECT** | Open sensor dashboard |
| **START** | Open menu |
| **Left/Right Sticks** | Chainsaw 1/2 actuation |

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

**⚠️ Read the full Safety Information section at the beginning of this guide before operating.**

## Emergency Stop Methods (In Order of Preference):
1. **Y Button on Controller** - Press immediately for any emergency
2. **Physical E-STOP on Robot** - Red button on robot chassis
3. **Hub Battery Disconnect** - Last resort emergency measure

## Critical Safety Rules:
1. **NEVER stand below the robot** - Stay to the side, minimum 3m distance
2. **E-STOP is your primary safety tool** - Press Y immediately if anything seems wrong
3. **Two-person operation required** - Never operate alone in the field
4. **Pre-operation checklist mandatory** - Check rope, battery, weather, clear area
5. **Connection loss = automatic stop** - Robot won't run away if you disconnect
6. **5-second rule** - Must hold Y for 5 seconds to clear E-STOP (prevents accidents)
7. **Startup = stopped** - Robot always starts with E-STOP engaged
8. **Weather limits** - No rain, high winds, or lightning
9. **Physical E-STOP test** - Test before every operation
10. **No internet is normal** - The SerpentBase network is isolated for safety

---

**Version:** 1.0
**Last Updated:** February 2026
**For:** Serpent Robotics Operators

# HaLow Setup Guide - ALFA HaLow-R Configuration

This guide walks you through setting up the ALFA HaLow-R devices to create a wireless bridge between your Robot Pi and Base Pi.

---

## Overview

**ALFA HaLow-R Specifications:**
- Chipset: Morse Micro MM6108
- Frequency: 902-928 MHz (US ISM band)
- Range: Up to 1 km line-of-sight
- Data Rate: 150 kbps - 15 Mbps
- Interface: Ethernet (100 Mbps)
- Topology: Bridge mode (transparent Ethernet bridge)
- Power: PoE or USB-C

**Note:** This guide uses the 192.168.1.x subnet to match the ALFA HaLow-R default configuration. The devices come preconfigured with IP 192.168.1.1, so we configure both Pis to use the same subnet for direct communication.

**Network Architecture:**
```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   BASE PI        │         │  ALFA HaLow-R A  │         │  ALFA HaLow-R B  │
│  192.168.1.10    │◄─Eth────│  (Access Point)  │~~~902MHz│  (Station Mode)  │
│                  │         │  192.168.1.1     │         │  192.168.1.1     │
└──────────────────┘         └──────────────────┘         └──────────────────┘
                                                                    │
                                                                   Eth
                                                                    │
                                                           ┌──────────────────┐
                                                           │   ROBOT PI       │
                                                           │  192.168.1.20    │
                                                           └──────────────────┘
```

---

## Part 1: Configure ALFA HaLow-R Devices

### Device A (Base Pi Side) - Access Point Mode

1. **Connect to HaLow-R Device A:**
   - Connect ALFA HaLow-R A to your computer via Ethernet
   - Power it via PoE or USB-C
   - Default IP is usually `192.168.1.1` or check manufacturer documentation

2. **Access Web Interface:**
   - Open browser: `http://192.168.1.1` (or device default IP)
   - Default credentials are usually `admin/admin` or check manual

3. **Configure as Access Point:**
   - **Mode:** Access Point (AP)
   - **SSID:** `SERPENT-HALOW` (or your preferred name)
   - **Channel:** Auto or specific channel (e.g., 1-26 for US)
   - **Security:** WPA2-PSK (if available) with strong password
   - **IP Mode:** Bridge mode (transparent)
   - **Save and Reboot**

### Device B (Robot Pi Side) - Station Mode

1. **Connect to HaLow-R Device B:**
   - Connect ALFA HaLow-R B to your computer via Ethernet
   - Power it via PoE or USB-C

2. **Access Web Interface:**
   - Open browser: `http://192.168.1.1`

3. **Configure as Station:**
   - **Mode:** Station (Client)
   - **SSID:** `SERPENT-HALOW` (same as Device A)
   - **Security:** WPA2-PSK with same password as Device A
   - **IP Mode:** Bridge mode (transparent)
   - **Save and Reboot**

**Note:** The ALFA HaLow-R devices act as a transparent Ethernet bridge. Once configured, they will bridge the Ethernet connections wirelessly, making the two Pis appear as if they're on the same local network.

---

## Part 2: Set Static IP on Robot Pi (This Device)

We need to set the Robot Pi to `192.168.1.20` to match the HaLow device subnet.

### Option A: Using dhcpcd (Recommended for Raspberry Pi OS)

1. **Edit dhcpcd configuration:**
   ```bash
   sudo nano /etc/dhcpcd.conf
   ```

2. **Add these lines at the end:**
   ```
   # HaLow Bridge - Robot Pi Static IP
   interface eth0
   static ip_address=192.168.1.20/24
   static domain_name_servers=8.8.8.8 1.1.1.1
   ```

3. **Save and exit:** Press `Ctrl+X`, then `Y`, then `Enter`

4. **Restart networking:**
   ```bash
   sudo systemctl restart dhcpcd
   # Or reboot
   sudo reboot
   ```

### Option B: Using NetworkManager (if installed)

```bash
sudo nmcli con mod "Wired connection 1" ipv4.addresses 192.168.1.20/24
sudo nmcli con mod "Wired connection 1" ipv4.dns "8.8.8.8 1.1.1.1"
sudo nmcli con mod "Wired connection 1" ipv4.method manual
sudo nmcli con up "Wired connection 1"
```

---

## Part 3: Set Static IP on Base Pi

**On your Base Pi**, set the static IP to `192.168.1.10`:

### Using dhcpcd:

1. **Edit dhcpcd configuration:**
   ```bash
   sudo nano /etc/dhcpcd.conf
   ```

2. **Add these lines at the end:**
   ```
   # HaLow Bridge - Base Pi Static IP
   interface eth0
   static ip_address=192.168.1.10/24
   static domain_name_servers=8.8.8.8 1.1.1.1
   ```

3. **Save and restart:**
   ```bash
   sudo systemctl restart dhcpcd
   # Or reboot
   sudo reboot
   ```

---

## Part 4: Physical Connections

1. **Robot Pi Setup:**
   ```
   Robot Pi [eth0] ──Ethernet──> [Ethernet Port] ALFA HaLow-R B
   ALFA HaLow-R B [Power] ──USB-C or PoE
   ```

2. **Base Pi Setup:**
   ```
   Base Pi [eth0] ──Ethernet──> [Ethernet Port] ALFA HaLow-R A
   ALFA HaLow-R A [Power] ──USB-C or PoE
   ```

3. **Place devices with line-of-sight:**
   - For best performance, position HaLow devices with minimal obstructions
   - Test at short range first (1-5 meters) before deploying at full range

---

## Part 5: Verify HaLow Connectivity

### Test Basic Connectivity

1. **From Robot Pi, ping HaLow device:**
   ```bash
   ping 192.168.1.1 -c 5
   ```
   This verifies your Robot Pi can reach the HaLow device on the same subnet.

2. **From Robot Pi, ping Base Pi:**
   ```bash
   ping 192.168.1.10 -c 5
   ```
   Should see replies with RTT typically 20-100ms

3. **From Base Pi, ping Robot Pi:**
   ```bash
   ping 192.168.1.20 -c 5
   ```

4. **Check link quality:**
   ```bash
   # Monitor ping continuously
   ping 192.168.1.10 -i 0.2
   ```
   Press `Ctrl+C` to stop. Look for:
   - **Good:** RTT < 50ms, 0% packet loss
   - **Acceptable:** RTT 50-200ms, < 5% packet loss
   - **Poor:** RTT > 200ms or > 10% packet loss (reposition devices)

### Test Bandwidth

```bash
# On Base Pi - start iperf3 server
sudo apt install -y iperf3
iperf3 -s

# On Robot Pi - test throughput
iperf3 -c 192.168.1.10 -t 10
```

Expected throughput: 1-10 Mbps (depending on range and conditions)

---

## Part 6: Configure Bridge Software IPs

Now configure the bridge software to use these IPs.

### On Robot Pi (This Device):

```bash
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE

# Set Base Pi IP
sudo bash scripts/set_bridge_ip.sh --robot 192.168.1.10

# This will:
# - Save IP to /etc/serpent/base_pi_ip
# - Update systemd service configuration
# - Restart the bridge service
```

### On Base Pi:

```bash
cd ~/PI-HALOW-BRIDGE  # Or wherever you cloned the repo

# Set Robot Pi IP
sudo bash scripts/set_bridge_ip.sh --base 192.168.1.20

# Restart the bridge
sudo systemctl restart serpent-base-bridge
```

---

## Part 7: Verify End-to-End Bridge

### Check Services Running

**On Robot Pi:**
```bash
sudo systemctl status serpent-robot-bridge
sudo journalctl -u serpent-robot-bridge -f
```

Look for:
- `Control server listening on port 5001`
- `Telemetry sender connecting to 192.168.1.10:5003`
- `Video sender connecting to 192.168.1.10:5002`

**On Base Pi:**
```bash
sudo systemctl status serpent-base-bridge
sudo journalctl -u serpent-base-bridge -f
```

Look for:
- `Control client connecting to 192.168.1.20:5001`
- `Telemetry receiver listening on port 5003`
- `Video receiver listening on port 5002`
- `video_connected: true`

### Test Video Stream

**On Base Pi:**
```bash
# Check health endpoint
curl http://localhost:5004/health

# Should show:
# {"status": "ok", "video_connected": true, "frames_received": <count>}

# View single frame
curl http://localhost:5004/frame > test_frame.jpg

# Stream video (open in browser)
# http://<base-pi-ip>:5004/video
```

### Test Control Commands

The control channel should automatically connect. Monitor logs to see heartbeat ping/pong:

```bash
# On Robot Pi
sudo journalctl -u serpent-robot-bridge -f | grep -i "ping\|pong\|rtt"

# On Base Pi
sudo journalctl -u serpent-base-bridge -f | grep -i "ping\|pong\|rtt"
```

You should see RTT measurements in the telemetry.

---

## Troubleshooting

### Subnet Mismatch Issues

If you configured your Pis with 192.168.100.x addresses following an older version of this guide:
- The HaLow devices use 192.168.1.1 by default
- Your Pis won't be able to reach them on different subnets
- Reconfigure using the 192.168.1.x addresses as shown above

To fix:
1. **On Robot Pi:** Change static IP to 192.168.1.20 (see Part 2)
2. **On Base Pi:** Change static IP to 192.168.1.10 (see Part 3)
3. **Update bridge IPs:** Run the commands in Part 6 with the new IPs
4. **Reboot both Pis** to ensure all changes take effect

### HaLow Devices Won't Connect

1. **Check power:** Ensure both devices have stable power (PoE or USB-C)
2. **Check SSID match:** Both devices must use same SSID and password
3. **Check mode:** One must be AP, one must be Station
4. **Check channel:** Use same channel or auto-select
5. **Check range:** Start with devices 1-5 meters apart for initial testing
6. **Check LEDs:** Most ALFA devices have status LEDs indicating connection

### Pis Can't Ping Each Other

1. **Check HaLow link first:**
   - Access HaLow device web interfaces
   - Verify "connected" or "link up" status

2. **Check static IPs:**
   ```bash
   ip addr show eth0
   ```
   Should show `192.168.1.20` on Robot Pi, `192.168.1.10` on Base Pi

3. **Check Ethernet cables:** Try different cables

4. **Check firewall:**
   ```bash
   sudo iptables -L -n
   # If blocking, temporarily disable for testing
   sudo iptables -F
   ```

### Bridge Services Won't Start

1. **Check PSK is set on both Pis:**
   ```bash
   sudo cat /etc/serpent/psk | wc -c
   # Should output 65 (64 chars + newline)
   ```
   Both Pis must have identical PSK.

2. **Check IP configuration:**
   ```bash
   # On Robot Pi
   sudo systemctl show serpent-robot-bridge --property=Environment | grep BASE_PI_IP

   # On Base Pi
   sudo systemctl show serpent-base-bridge --property=Environment | grep ROBOT_PI_IP
   ```

3. **Check logs for errors:**
   ```bash
   sudo journalctl -u serpent-robot-bridge -n 100
   sudo journalctl -u serpent-base-bridge -n 100
   ```

### High Latency or Packet Loss

1. **Check distance:** Move HaLow devices closer
2. **Check interference:** 900 MHz band can be crowded in some areas
3. **Reposition antennas:** Try different orientations
4. **Check for metal obstructions:** Metal barriers severely impact 900 MHz

### Video Not Streaming

1. **Verify ping works:** Control and telemetry have priority, video is lowest
2. **Check cameras on Robot Pi:**
   ```bash
   ls -la /dev/video*
   v4l2-ctl --list-devices
   ```
3. **Check video connection logs:**
   ```bash
   sudo journalctl -u serpent-robot-bridge | grep -i video
   sudo journalctl -u serpent-base-bridge | grep -i "video_connected\|frames_received"
   ```

---

## Expected Performance Over HaLow

| Metric | Typical Value | Notes |
|--------|--------------|-------|
| RTT (Round Trip Time) | 20-100 ms | Depends on range |
| Control Latency | 50-150 ms | Acceptable for robot control |
| Telemetry Rate | 10 Hz | 100ms interval |
| Video Frame Rate | 5-10 FPS | Auto-adjusts for bandwidth |
| Video Latency | 200-500 ms | Acceptable for monitoring |
| Range (Line of Sight) | Up to 1 km | Outdoor, no obstructions |
| Range (Indoor) | 100-300 m | Depends on walls/obstacles |

---

## Security Recommendations

1. **Change HaLow WPA2 password** from default
2. **Keep PSK secure** (`/etc/serpent/psk` is 600 permissions)
3. **Disable HaLow web interface** after configuration
4. **Use physical security** for both devices (locked enclosures)
5. **Regular firmware updates** for HaLow devices

---

## Quick Command Reference

```bash
# Set Robot Pi IP to 192.168.1.20
sudo nano /etc/dhcpcd.conf  # Add static IP config
sudo reboot

# Configure bridge to use Base Pi IP
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
sudo bash scripts/set_bridge_ip.sh --robot 192.168.1.10

# Check connectivity
ping 192.168.1.1 -c 5    # Ping HaLow device
ping 192.168.1.10 -c 5   # Ping Base Pi

# Monitor bridge logs
sudo journalctl -u serpent-robot-bridge -f

# Check video health (on Base Pi)
curl http://localhost:5004/health
```

---

## Next Steps After Setup

1. **Test at increasing ranges:** Start close, gradually move apart
2. **Run stress tests:** See `tests/STRESS_TESTING.md`
3. **Configure backend integration:** See `INTEGRATION.md`
4. **Field deployment:** See main `README.md` for deployment procedures

---

**Need help?** Check the main README.md and troubleshooting sections, or contact Serpent Robotics team.

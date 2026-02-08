# PI-HALOW-BRIDGE Setup Guide

## ✅ Robot Pi Setup - COMPLETE

Your Robot Pi is configured and ready to connect!

**PSK Generated:**
```
1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1
```

---

## 📋 Next Steps: Set Up Base Pi

### Step 1: Copy Files to Base Pi

From your Robot Pi, run:
```bash
# Copy setup script to Base Pi
scp setup_base_pi.sh robotpi@192.168.1.10:~/PI-HALOW-BRIDGE/

# Or copy the entire project if Base Pi doesn't have it yet
rsync -av --exclude 'venv' --exclude '__pycache__' \
  /home/robotpi/Desktop/PI-HALOW-BRIDGE/ \
  robotpi@192.168.1.10:~/PI-HALOW-BRIDGE/
```

### Step 2: Run Setup on Base Pi

SSH into Base Pi:
```bash
ssh robotpi@192.168.1.10
```

On Base Pi, run:
```bash
cd ~/PI-HALOW-BRIDGE
sudo ./setup_base_pi.sh 1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1
```

---

## 🚀 Starting the System

### On Base Pi (do this first):
```bash
sudo systemctl start serpent-base-bridge
sudo systemctl status serpent-base-bridge
# Check logs:
sudo journalctl -u serpent-base-bridge -f
```

### On Robot Pi (do this second):
```bash
sudo systemctl start serpent-robot-bridge
sudo systemctl status serpent-robot-bridge
# Check logs:
sudo journalctl -u serpent-robot-bridge -f
```

---

## 🎯 Verification Checklist

### 1. Check Connection Status
On Robot Pi:
```bash
sudo journalctl -u serpent-robot-bridge -n 50 | grep -i "control"
```

Look for: `Control server: Base Pi connected`

### 2. Verify E-STOP Status
Should show `E-STOP ENGAGED` until you clear it:
```bash
sudo journalctl -u serpent-robot-bridge | grep -i "estop"
```

### 3. Check Telemetry Flow
On Base Pi, check for incoming telemetry:
```bash
sudo journalctl -u serpent-base-bridge | grep -i "telemetry"
```

### 4. Test Dashboard
Access dashboards:
- **Robot Pi Dashboard:** http://192.168.1.20:5005
- **Base Pi Dashboard:** http://192.168.1.10:5006

Both should show:
- ✅ Same E-STOP status
- ✅ Same connection status
- ✅ Real-time telemetry
- ✅ Motor controls (Robot Pi dashboard)

---

## 🔧 Troubleshooting

### Connection Issues

**Problem:** Control not connecting
**Check:**
```bash
# On Robot Pi
ping 192.168.1.10

# Check if Base Pi is listening on port 5001
nc -zv 192.168.1.10 5001
```

**Solution:** Make sure Base Pi bridge started first!

### PSK Mismatch

**Problem:** Authentication failures in logs
**Check:** PSK must be identical on both Pis
```bash
# On both Pis:
sudo cat /etc/serpent/psk.key
```

### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u serpent-robot-bridge -n 100 --no-pager
```

**Common issues:**
- Python module import errors → Check venv is activated in service
- Permission denied → Check user groups (i2c, gpio, video)
- Port already in use → Stop simulation first: `pkill -f bridge_coordinator`

---

## 📊 Dashboard Setup (Optional)

To enable the monitoring dashboard on Robot Pi:

```bash
cd ~/PI-HALOW-BRIDGE/dashboard
sudo cp systemd/serpent-dashboard-robot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-dashboard-robot
sudo systemctl start serpent-dashboard-robot
```

Access at: http://192.168.1.20:5005

---

## 🎮 Testing Motor Controls

Once connected and E-STOP cleared:

1. Open Robot Pi Dashboard: http://192.168.1.20:5005
2. Click "Clear E-STOP" (requires authentication)
3. Use motor test controls:
   - Forward/Stop/Backward buttons for each motor
   - Test at 95% power (760/800)
4. Monitor motor currents in real-time

---

## 🔒 Safety Notes

- E-STOP engages automatically on:
  - System boot (fail-safe default)
  - Loss of control signal (5 second timeout)
  - Any critical error
  - Manual emergency stop button

- E-STOP can only be cleared via authenticated command
- Watchdog monitors control connection continuously
- All errors trigger immediate E-STOP

---

## 📝 Quick Commands Reference

```bash
# Start services
sudo systemctl start serpent-robot-bridge
sudo systemctl start serpent-base-bridge

# Stop services
sudo systemctl stop serpent-robot-bridge
sudo systemctl stop serpent-base-bridge

# Restart services
sudo systemctl restart serpent-robot-bridge
sudo systemctl restart serpent-base-bridge

# View logs (follow mode)
sudo journalctl -u serpent-robot-bridge -f
sudo journalctl -u serpent-base-bridge -f

# View recent logs
sudo journalctl -u serpent-robot-bridge -n 100 --no-pager
sudo journalctl -u serpent-base-bridge -n 100 --no-pager

# Check service status
sudo systemctl status serpent-robot-bridge
sudo systemctl status serpent-base-bridge
```

---

**Your PSK:** `1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1`

**Ready to connect!** 🚀

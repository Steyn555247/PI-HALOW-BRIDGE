# Setup PSK on Robot Pi for Auto-Boot

This guide ensures the PSK `1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1` is automatically loaded on the Robot Pi during boot.

## Current Status

✅ **Base Pi**: PSK is already configured and will load automatically on boot
- Configured in: `/etc/systemd/system/serpent-base-bridge.service.d/psk.conf`
- Backup location: `/etc/serpent/psk`
- Service: `enabled` (starts on boot)

## Robot Pi Setup

Run these commands on the Robot Pi (192.168.1.20):

### Option 1: Systemd Drop-in (Recommended)

```bash
# Create drop-in directory
sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d

# Create PSK configuration file
echo '[Service]
Environment="SERPENT_PSK_HEX=1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1"' | sudo tee /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Set secure permissions
sudo chmod 600 /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge
```

### Option 2: File-based PSK (Backup Method)

```bash
# Create serpent directory
sudo mkdir -p /etc/serpent

# Write PSK to file
echo "1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1" | sudo tee /etc/serpent/psk

# Set secure permissions (read-only by root)
sudo chmod 600 /etc/serpent/psk

# Restart service
sudo systemctl restart serpent-robot-bridge
```

### Both Methods (Most Reliable)

For maximum reliability, use BOTH methods:

```bash
# Systemd (primary)
sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d
echo '[Service]
Environment="SERPENT_PSK_HEX=1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1"' | sudo tee /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf
sudo chmod 600 /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# File backup (secondary)
sudo mkdir -p /etc/serpent
echo "1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk

# Apply changes
sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge
```

## Verification

After setting up the PSK on Robot Pi, verify it works:

### 1. Check Configuration Files

```bash
# On Robot Pi:
echo "=== Robot Pi PSK Check ==="
echo "Systemd PSK:"
sudo cat /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf
echo ""
echo "File PSK:"
sudo cat /etc/serpent/psk
echo "Length: $(sudo cat /etc/serpent/psk | wc -c) chars (should be 64)"
```

### 2. Verify Service Loads PSK

```bash
# Check service is running
sudo systemctl status serpent-robot-bridge

# Check for PSK errors in logs
sudo journalctl -u serpent-robot-bridge -n 50 | grep -i psk
# Should show: "PSK loaded successfully"
```

### 3. Test Connection

```bash
# On Base Pi, check connection status:
curl http://localhost:5006/api/status | grep -E "control|telemetry|video|psk_valid"

# Should show:
# "control": "connected"
# "telemetry": "connected"
# "video": "connected"
# "psk_valid": true
```

### 4. Test Reboot

```bash
# On Robot Pi, test that PSK persists after reboot:
sudo reboot

# After reboot, check service started with PSK:
sudo systemctl status serpent-robot-bridge
sudo journalctl -u serpent-robot-bridge | grep "PSK loaded"
```

## How It Works

### Boot Sequence

1. **System boots**
2. **Systemd starts serpent-robot-bridge.service**
3. **Service loads environment from drop-in files:**
   - `/etc/systemd/system/serpent-robot-bridge.service.d/psk.conf`
   - Sets `SERPENT_PSK_HEX` environment variable
4. **Python bridge code starts:**
   - Checks for `SERPENT_PSK_HEX` environment variable
   - If not found, reads from `/etc/serpent/psk` file
   - Loads PSK for HMAC authentication
5. **Bridge connects to Base Pi:**
   - Uses PSK to sign all messages
   - HMAC verification succeeds
   - Stable connection established

### Priority Order

The code checks for PSK in this order:
1. **Environment variable** `SERPENT_PSK_HEX` (from systemd drop-in)
2. **File** `/etc/serpent/psk` (backup method)
3. **Error** if neither is found

## Security Notes

### File Permissions

Always use restrictive permissions:
```bash
# PSK files should be readable only by root
sudo chmod 600 /etc/serpent/psk
sudo chmod 600 /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Verify permissions
ls -la /etc/serpent/psk
ls -la /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf
```

### Never Commit PSK to Git

The PSK should NEVER be committed to version control:
- ✅ Store in `/etc/serpent/psk` (not in git repo)
- ✅ Store in systemd drop-in (not in git repo)
- ❌ Never hardcode in Python files
- ❌ Never commit to git

## Troubleshooting

### PSK Not Loading

**Symptom:** Logs show "PSK not configured" or "HMAC verification failed"

**Solution:**
```bash
# Check if files exist
ls -la /etc/serpent/psk
ls -la /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Check PSK length (must be exactly 64)
sudo cat /etc/serpent/psk | wc -c

# Check for whitespace/newlines
sudo cat /etc/serpent/psk | od -c

# Recreate if needed
echo -n "1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1" | sudo tee /etc/serpent/psk
```

### PSK Doesn't Persist After Reboot

**Symptom:** Works after manual restart, fails after reboot

**Solution:**
```bash
# Verify service is enabled
systemctl is-enabled serpent-robot-bridge
# Should output: "enabled"

# If not enabled:
sudo systemctl enable serpent-robot-bridge

# Verify drop-in files are loaded
systemctl show serpent-robot-bridge -p DropInPaths
# Should include: psk.conf
```

### HMAC Still Failing

**Symptom:** "HMAC verification FAILED" even with correct PSK

**Possible causes:**
1. PSK mismatch between devices
2. Whitespace in PSK file
3. Wrong PSK length

**Solution:**
```bash
# Compare PSKs on both devices
# On Base Pi:
sudo cat /etc/serpent/psk

# On Robot Pi:
sudo cat /etc/serpent/psk

# They MUST be identical!

# If different, copy correct PSK to both:
echo "1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1" | sudo tee /etc/serpent/psk
sudo systemctl restart serpent-robot-bridge
```

## Quick Copy-Paste Setup

Complete setup script for Robot Pi:

```bash
#!/bin/bash
# Run on Robot Pi to setup PSK for auto-boot

PSK="1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1"

echo "Setting up PSK on Robot Pi..."

# Systemd drop-in
sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d
echo "[Service]
Environment=\"SERPENT_PSK_HEX=$PSK\"" | sudo tee /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf > /dev/null
sudo chmod 600 /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# File backup
sudo mkdir -p /etc/serpent
echo "$PSK" | sudo tee /etc/serpent/psk > /dev/null
sudo chmod 600 /etc/serpent/psk

# Apply
sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge

echo "Done! Verifying..."
sleep 2

# Verify
if sudo systemctl is-active --quiet serpent-robot-bridge; then
    echo "✅ Service is running"
else
    echo "❌ Service failed to start"
    exit 1
fi

if sudo journalctl -u serpent-robot-bridge -n 20 | grep -q "PSK loaded successfully"; then
    echo "✅ PSK loaded successfully"
else
    echo "⚠️  Check logs for PSK issues"
fi

echo ""
echo "PSK setup complete!"
echo "Both Base Pi and Robot Pi now have matching PSK configured for auto-boot."
```

## Summary

✅ **Base Pi**: Already configured, PSK will auto-load on boot
✅ **Robot Pi**: Follow steps above to configure matching PSK
✅ **Persistent**: PSK survives reboots on both devices
✅ **Secure**: Files have 600 permissions (root-only)
✅ **Redundant**: Both systemd and file backup methods configured

After completing Robot Pi setup, the system will automatically use the correct PSK on every boot.

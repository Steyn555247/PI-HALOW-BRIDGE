# Fix PSK Mismatch Issue

## Problem

The base_pi and robot_pi have **different PSKs**, causing:
1. ❌ HMAC verification failures
2. ❌ Rapid connect/disconnect loop (every 200ms)
3. ❌ "Shocky" dashboard behavior

## Root Cause

- **Base Pi PSK**: `89509ab4ed416191c1a91729a599eba0f1e98eaea5403bc02c86092afda012a2`
- **Robot Pi PSK**: Different (causing HMAC mismatch)

When robot sends telemetry, base rejects it → robot disconnects → robot retries immediately → loop continues.

## Solution: Sync PSKs

### Step 1: Copy Base Pi PSK

```bash
# On Base Pi (this machine):
sudo cat /etc/systemd/system/serpent-base-bridge.service.d/psk.conf
```

Copy the PSK value (64 hex characters).

### Step 2: Update Robot Pi PSK

```bash
# On Robot Pi (192.168.1.20):
# Option A: Update systemd service drop-in
sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d
sudo nano /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf

# Add this content (use SAME PSK as base_pi):
[Service]
Environment="SERPENT_PSK_HEX=89509ab4ed416191c1a91729a599eba0f1e98eaea5403bc02c86092afda012a2"

# Save and exit (Ctrl+X, Y, Enter)

# Option B: Update /etc/serpent/psk file
echo "89509ab4ed416191c1a91729a599eba0f1e98eaea5403bc02c86092afda012a2" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk
```

### Step 3: Restart Services

```bash
# On Robot Pi:
sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge

# On Base Pi (optional, but recommended):
sudo systemctl restart serpent-base-bridge
```

### Step 4: Verify Fix

```bash
# On Base Pi:
sudo journalctl -u serpent-base-bridge -f

# Look for:
✅ "Robot Pi telemetry connected" (and stays connected)
✅ No more "HMAC verification FAILED" messages
✅ Stable connection (no rapid disconnect/reconnect)

# Check dashboard:
curl http://localhost:5006/api/status | grep -E "telemetry|control"
# Should show: "connected" without flickering
```

## Quick Verification Script

Run this on **both devices** to compare PSKs:

```bash
#!/bin/bash
echo "=== PSK Configuration Check ==="
echo ""
echo "1. Systemd service PSK:"
sudo cat /etc/systemd/system/serpent-*-bridge.service.d/psk.conf 2>/dev/null | grep SERPENT_PSK_HEX || echo "Not configured in systemd"
echo ""
echo "2. File-based PSK (/etc/serpent/psk):"
if [ -f /etc/serpent/psk ]; then
    sudo cat /etc/serpent/psk
    echo "Length: $(sudo cat /etc/serpent/psk | wc -c) chars"
else
    echo "File does not exist"
fi
echo ""
echo "3. Environment variable (if set):"
echo "SERPENT_PSK_HEX=${SERPENT_PSK_HEX:-Not set}"
echo ""
echo "=== PSKs should be IDENTICAL on both devices ==="
```

## Expected Result

After fixing PSKs, you should see:

### Base Pi Logs:
```
[INFO] Robot Pi telemetry connected from ('192.168.1.20', 43644)
[INFO] PSK loaded successfully
[INFO] HMAC verified successfully
```

### Dashboard:
```json
{
  "connections": {
    "control": "connected",
    "telemetry": "connected",
    "video": "connected"
  },
  "health": {
    "psk_valid": true
  }
}
```

### No More Stuttering:
- Connection stays stable
- No rapid disconnect/reconnect
- Dashboard status doesn't flicker

## Additional Notes

### Why This Happened

Likely causes:
1. Different PSK was set during initial setup
2. One device was updated but PSK wasn't copied
3. PSK file was manually edited on one device

### Prevention

Always use **identical PSKs** on both devices. Store it securely:
```bash
# Generate once, use on both:
PSK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo $PSK

# Then set on BOTH devices with exact same value
```

### Troubleshooting

If issues persist:
1. **Restart both bridges**
2. **Check logs on both sides**
3. **Verify PSK length** (must be exactly 64 hex chars)
4. **Check for whitespace** (no trailing newlines or spaces)
5. **Verify network connectivity** (`ping 192.168.1.20`)

## Related Files

- `/etc/systemd/system/serpent-base-bridge.service.d/psk.conf` (Base Pi)
- `/etc/systemd/system/serpent-robot-bridge.service.d/psk.conf` (Robot Pi)
- `/etc/serpent/psk` (Alternative PSK location)
- `common/framing.py` (HMAC verification code)

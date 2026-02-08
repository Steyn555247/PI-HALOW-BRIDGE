#!/bin/bash
#
# Verify PSK Auto-Load Configuration
# Tests that PSK will be loaded automatically on boot
#

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

EXPECTED_PSK="1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1"

echo "============================================"
echo "  PSK Auto-Load Verification"
echo "============================================"
echo ""

# Detect device
if systemctl list-units | grep -q "serpent-robot-bridge"; then
    DEVICE="robot_pi"
    SERVICE="serpent-robot-bridge"
elif systemctl list-units | grep -q "serpent-base-bridge"; then
    DEVICE="base_pi"
    SERVICE="serpent-base-bridge"
else
    echo -e "${RED}ERROR: No serpent bridge service found${NC}"
    exit 1
fi

echo "Device: $DEVICE"
echo "Service: $SERVICE"
echo ""

PASS=0
FAIL=0

# Test 1: Service is enabled
echo "Test 1: Service enabled for auto-start on boot"
if systemctl is-enabled --quiet $SERVICE; then
    echo -e "${GREEN}✓ PASS${NC} - Service is enabled"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗ FAIL${NC} - Service is not enabled"
    echo "  Fix: sudo systemctl enable $SERVICE"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 2: Systemd drop-in exists
echo "Test 2: Systemd PSK drop-in file exists"
DROPIN="/etc/systemd/system/$SERVICE.service.d/psk.conf"
if [ -f "$DROPIN" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Drop-in file exists: $DROPIN"
    PASS=$((PASS + 1))

    # Check permissions
    PERMS=$(stat -c %a "$DROPIN")
    if [ "$PERMS" = "600" ]; then
        echo -e "${GREEN}✓ PASS${NC} - Permissions are secure (600)"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}⚠ WARN${NC} - Permissions are $PERMS (should be 600)"
        echo "  Fix: sudo chmod 600 $DROPIN"
    fi
else
    echo -e "${RED}✗ FAIL${NC} - Drop-in file not found"
    echo "  Create with: sudo mkdir -p /etc/systemd/system/$SERVICE.service.d"
    echo "              echo '[Service]' | sudo tee $DROPIN"
    echo "              echo 'Environment=\"SERPENT_PSK_HEX=$EXPECTED_PSK\"' | sudo tee -a $DROPIN"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 3: PSK file exists
echo "Test 3: PSK file exists as backup"
if [ -f /etc/serpent/psk ]; then
    echo -e "${GREEN}✓ PASS${NC} - PSK file exists: /etc/serpent/psk"
    PASS=$((PASS + 1))

    # Check permissions
    PERMS=$(stat -c %a /etc/serpent/psk)
    if [ "$PERMS" = "600" ]; then
        echo -e "${GREEN}✓ PASS${NC} - Permissions are secure (600)"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}⚠ WARN${NC} - Permissions are $PERMS (should be 600)"
        echo "  Fix: sudo chmod 600 /etc/serpent/psk"
    fi
else
    echo -e "${YELLOW}⚠ WARN${NC} - PSK file not found (optional backup)"
    echo "  Create with: echo '$EXPECTED_PSK' | sudo tee /etc/serpent/psk"
fi
echo ""

# Test 4: PSK value is correct
echo "Test 4: PSK value matches expected"
if [ -f "$DROPIN" ]; then
    DROPIN_PSK=$(sudo cat "$DROPIN" | grep SERPENT_PSK_HEX | cut -d'"' -f2)
    if [ "$DROPIN_PSK" = "$EXPECTED_PSK" ]; then
        echo -e "${GREEN}✓ PASS${NC} - Systemd PSK matches expected value"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗ FAIL${NC} - Systemd PSK does not match"
        echo "  Expected: $EXPECTED_PSK"
        echo "  Got:      $DROPIN_PSK"
        FAIL=$((FAIL + 1))
    fi
fi

if [ -f /etc/serpent/psk ]; then
    FILE_PSK=$(sudo cat /etc/serpent/psk)
    if [ "$FILE_PSK" = "$EXPECTED_PSK" ]; then
        echo -e "${GREEN}✓ PASS${NC} - File PSK matches expected value"
        PASS=$((PASS + 1))
    else
        echo -e "${YELLOW}⚠ WARN${NC} - File PSK does not match"
        echo "  Expected: $EXPECTED_PSK"
        echo "  Got:      $FILE_PSK"
    fi
fi
echo ""

# Test 5: Service is currently running
echo "Test 5: Service is currently running"
if systemctl is-active --quiet $SERVICE; then
    echo -e "${GREEN}✓ PASS${NC} - Service is active"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗ FAIL${NC} - Service is not running"
    echo "  Start with: sudo systemctl start $SERVICE"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 6: No recent PSK errors
echo "Test 6: No recent PSK authentication errors"
PSK_ERRORS=$(sudo journalctl -u $SERVICE --since "2 minutes ago" | grep -c "HMAC verification FAILED" || echo "0")
if [ "$PSK_ERRORS" = "0" ]; then
    echo -e "${GREEN}✓ PASS${NC} - No HMAC failures in last 2 minutes"
    PASS=$((PASS + 1))
else
    echo -e "${RED}✗ FAIL${NC} - Found $PSK_ERRORS HMAC failures in last 2 minutes"
    echo "  This means PSK mismatch between devices!"
    FAIL=$((FAIL + 1))
fi
echo ""

# Summary
echo "============================================"
echo "  Summary"
echo "============================================"
echo ""
echo "Tests passed: $PASS"
echo "Tests failed: $FAIL"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ SUCCESS!${NC}"
    echo ""
    echo "PSK is properly configured and will auto-load on boot."
    echo "Expected PSK: $EXPECTED_PSK"
    echo ""
    echo "After reboot, the service will:"
    echo "  1. Start automatically"
    echo "  2. Load PSK from systemd environment"
    echo "  3. Use PSK for HMAC authentication"
    echo "  4. Connect successfully to other device"
    echo ""
    exit 0
else
    echo -e "${RED}❌ ISSUES FOUND${NC}"
    echo ""
    echo "Please fix the issues above before rebooting."
    echo "See SETUP_PSK_ON_ROBOT.md for detailed instructions."
    echo ""
    exit 1
fi

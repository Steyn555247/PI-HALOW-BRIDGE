#!/bin/bash
#
# PSK Configuration Checker
# Verifies PSK configuration on base_pi or robot_pi
#

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================"
echo "  PSK Configuration Check"
echo "============================================"
echo ""

# Detect device type
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

# Check systemd drop-in
echo "1. Systemd Service PSK:"
SYSTEMD_PSK_FILE="/etc/systemd/system/$SERVICE.service.d/psk.conf"
if [ -f "$SYSTEMD_PSK_FILE" ]; then
    PSK_FROM_SYSTEMD=$(sudo cat $SYSTEMD_PSK_FILE | grep SERPENT_PSK_HEX | cut -d'"' -f2)
    if [ -n "$PSK_FROM_SYSTEMD" ]; then
        echo -e "${GREEN}✓ Found in systemd drop-in${NC}"
        echo "  Length: ${#PSK_FROM_SYSTEMD} characters"
        echo "  Value: $PSK_FROM_SYSTEMD"
        if [ ${#PSK_FROM_SYSTEMD} -eq 64 ]; then
            echo -e "  ${GREEN}✓ Length is correct (64 chars)${NC}"
        else
            echo -e "  ${RED}✗ Length is wrong (should be 64)${NC}"
        fi
    else
        echo -e "${YELLOW}! Systemd file exists but no PSK found${NC}"
    fi
else
    echo -e "${YELLOW}! Not configured in systemd${NC}"
    PSK_FROM_SYSTEMD=""
fi
echo ""

# Check /etc/serpent/psk
echo "2. File-based PSK (/etc/serpent/psk):"
if [ -f /etc/serpent/psk ]; then
    PSK_FROM_FILE=$(sudo cat /etc/serpent/psk)
    echo -e "${GREEN}✓ File exists${NC}"
    echo "  Length: ${#PSK_FROM_FILE} characters"
    echo "  Value: $PSK_FROM_FILE"
    if [ ${#PSK_FROM_FILE} -eq 64 ]; then
        echo -e "  ${GREEN}✓ Length is correct (64 chars)${NC}"
    else
        echo -e "  ${RED}✗ Length is wrong (should be 64)${NC}"
    fi
else
    echo -e "${YELLOW}! File does not exist${NC}"
    PSK_FROM_FILE=""
fi
echo ""

# Check environment variable
echo "3. Environment Variable (SERPENT_PSK_HEX):"
if [ -n "$SERPENT_PSK_HEX" ]; then
    echo -e "${GREEN}✓ Set in current environment${NC}"
    echo "  Length: ${#SERPENT_PSK_HEX} characters"
    echo "  Value: $SERPENT_PSK_HEX"
else
    echo -e "${YELLOW}! Not set in current environment${NC}"
fi
echo ""

# Verify which PSK is being used
echo "4. Active PSK (used by running service):"
if systemctl is-active --quiet $SERVICE; then
    echo -e "${GREEN}✓ Service is running${NC}"
    # The service uses systemd environment first, then file
    if [ -n "$PSK_FROM_SYSTEMD" ]; then
        ACTIVE_PSK="$PSK_FROM_SYSTEMD"
        echo "  Source: systemd drop-in"
    elif [ -n "$PSK_FROM_FILE" ]; then
        ACTIVE_PSK="$PSK_FROM_FILE"
        echo "  Source: /etc/serpent/psk"
    else
        echo -e "${RED}✗ No PSK configured!${NC}"
        ACTIVE_PSK=""
    fi

    if [ -n "$ACTIVE_PSK" ]; then
        echo "  Value: $ACTIVE_PSK"
    fi
else
    echo -e "${YELLOW}! Service is not running${NC}"
fi
echo ""

# Summary
echo "============================================"
echo "  Summary"
echo "============================================"
echo ""

ISSUES=0

# Check if PSK is configured
if [ -z "$PSK_FROM_SYSTEMD" ] && [ -z "$PSK_FROM_FILE" ]; then
    echo -e "${RED}✗ CRITICAL: No PSK configured${NC}"
    ISSUES=$((ISSUES + 1))
fi

# Check PSK length
if [ -n "$PSK_FROM_SYSTEMD" ] && [ ${#PSK_FROM_SYSTEMD} -ne 64 ]; then
    echo -e "${RED}✗ ERROR: Systemd PSK length is ${#PSK_FROM_SYSTEMD} (should be 64)${NC}"
    ISSUES=$((ISSUES + 1))
fi

if [ -n "$PSK_FROM_FILE" ] && [ ${#PSK_FROM_FILE} -ne 64 ]; then
    echo -e "${RED}✗ ERROR: File PSK length is ${#PSK_FROM_FILE} (should be 64)${NC}"
    ISSUES=$((ISSUES + 1))
fi

# Check if PSKs match (if both configured)
if [ -n "$PSK_FROM_SYSTEMD" ] && [ -n "$PSK_FROM_FILE" ] && [ "$PSK_FROM_SYSTEMD" != "$PSK_FROM_FILE" ]; then
    echo -e "${YELLOW}⚠ WARNING: Systemd PSK and file PSK are different${NC}"
    echo "  Service will use: systemd drop-in"
fi

# Check HMAC errors in logs
echo ""
echo "5. Recent HMAC Errors:"
HMAC_ERRORS=$(sudo journalctl -u $SERVICE --since "2 minutes ago" | grep -c "HMAC verification FAILED")
if [ $HMAC_ERRORS -gt 0 ]; then
    echo -e "${RED}✗ Found $HMAC_ERRORS HMAC verification failures in last 2 minutes${NC}"
    echo "  This means PSKs don't match between devices!"
    ISSUES=$((ISSUES + 1))
else
    echo -e "${GREEN}✓ No recent HMAC errors${NC}"
fi

echo ""
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}✓ PSK configuration looks good!${NC}"
else
    echo -e "${RED}✗ Found $ISSUES issue(s) - see FIX_PSK_MISMATCH.md for solutions${NC}"
fi
echo ""

# Provide fix instructions if issues found
if [ $ISSUES -gt 0 ]; then
    echo "To fix PSK issues:"
    echo "  1. Read: cat FIX_PSK_MISMATCH.md"
    echo "  2. Ensure BOTH devices have IDENTICAL 64-character PSKs"
    echo "  3. Restart services after fixing"
    echo ""
fi

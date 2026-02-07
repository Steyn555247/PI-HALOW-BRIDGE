#!/bin/bash
# Restart Robot Pi bridge service remotely
# This ensures Robot Pi loads the correct PSK and clears auth_failure E-STOP

ROBOT_IP="192.168.1.20"
ROBOT_USER="robotpi"

echo "=== Restarting Robot Pi Bridge Service ==="
echo "Robot IP: $ROBOT_IP"
echo ""

# Check if we can reach the robot
if ! ping -c 1 -W 2 $ROBOT_IP &>/dev/null; then
    echo "❌ ERROR: Cannot reach Robot Pi at $ROBOT_IP"
    exit 1
fi

echo "✅ Robot Pi is reachable"
echo ""

echo "Attempting to restart serpent-robot-bridge service..."
echo "You may be prompted for the robotpi password."
echo ""

# Try to restart the service via SSH
ssh -o ConnectTimeout=5 ${ROBOT_USER}@${ROBOT_IP} "sudo systemctl restart serpent-robot-bridge && echo '✅ Service restarted successfully' && sleep 2 && sudo systemctl status serpent-robot-bridge --no-pager | head -10"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Robot Pi bridge service restarted!"
    echo ""
    echo "Checking Base Pi logs for auth status..."
    sleep 3
    sudo journalctl -u serpent-base-bridge -n 20 --no-pager | grep -iE "estop|auth|connected"
else
    echo ""
    echo "❌ Failed to restart service. You may need to:"
    echo "   1. SSH manually: ssh ${ROBOT_USER}@${ROBOT_IP}"
    echo "   2. Run: sudo systemctl restart serpent-robot-bridge"
fi

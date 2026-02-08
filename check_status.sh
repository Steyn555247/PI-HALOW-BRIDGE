#!/bin/bash
# Quick Bridge Status Check

echo "=========================================="
echo "PI-HALOW-BRIDGE Status"
echo "=========================================="
echo ""

# Get latest status from logs
STATUS=$(sudo journalctl -u serpent-robot-bridge --since "30 seconds ago" --no-pager | grep '"event": "status"' | tail -1)

if [ -z "$STATUS" ]; then
    echo "⚠️  No recent status logs - bridge may not be running"
    sudo systemctl status serpent-robot-bridge --no-pager | head -10
else
    echo "✅ Bridge is running!"
    echo ""

    # Extract key info from JSON
    CONTROL=$(echo "$STATUS" | grep -o '"control_connected":[^,]*' | cut -d':' -f2)
    TELEMETRY=$(echo "$STATUS" | grep -o '"telemetry_connected":[^,]*' | cut -d':' -f2)
    ESTOP=$(echo "$STATUS" | grep -o '"estop_engaged":[^,]*' | cut -d':' -f2)
    ESTOP_REASON=$(echo "$STATUS" | grep -o '"estop_reason":"[^"]*"' | cut -d':' -f2 | tr -d '"')
    PSK=$(echo "$STATUS" | grep -o '"psk_valid":[^,]*' | cut -d':' -f2)

    echo "Control Connected:    $CONTROL"
    echo "Telemetry Connected:  $TELEMETRY"
    echo "E-STOP Engaged:       $ESTOP"
    echo "E-STOP Reason:        $ESTOP_REASON"
    echo "PSK Valid:            $PSK"
    echo ""
    echo "Full status:"
    echo "$STATUS" | sed 's/.*INFO - //' | python3 -m json.tool 2>/dev/null || echo "$STATUS"
fi

echo ""
echo "=========================================="

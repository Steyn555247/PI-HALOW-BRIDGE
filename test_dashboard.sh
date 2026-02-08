#!/bin/bash
# Test Dashboard Connectivity

echo "=========================================="
echo "Dashboard Status Test"
echo "=========================================="
echo ""

echo "1. Checking if dashboard is running..."
if systemctl is-active --quiet serpent-dashboard-robot; then
    echo "   ✓ Dashboard service is running"
else
    echo "   ✗ Dashboard service is not running"
    echo "   Start it with: sudo systemctl start serpent-dashboard-robot"
    exit 1
fi

echo ""
echo "2. Testing dashboard API..."
if curl -s http://localhost:5005/api/status > /dev/null; then
    echo "   ✓ Dashboard API is responding"
else
    echo "   ✗ Dashboard API is not responding"
    exit 1
fi

echo ""
echo "3. Checking dashboard status..."
STATUS=$(curl -s http://localhost:5005/api/status)
echo "$STATUS" | python3 -m json.tool

echo ""
echo "4. Dashboard access URLs:"
echo "   Local:   http://localhost:5005"
echo "   Network: http://192.168.1.20:5005"

echo ""
echo "5. WebSocket connection:"
echo "   ws://192.168.1.20:5005/ws/status"

echo ""
echo "=========================================="
echo "Dashboard is ready!"
echo "=========================================="
echo ""
echo "Once you start the robot bridge service, the dashboard will show:"
echo "  - E-STOP status"
echo "  - Connection status (control, telemetry, video)"
echo "  - Real-time sensor data"
echo "  - Motor controls and currents"
echo ""

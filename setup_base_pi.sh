#!/bin/bash
# Setup script for Base Pi HaLow Bridge
# Run with: sudo ./setup_base_pi.sh [PSK_FROM_ROBOT_PI]

set -e  # Exit on error

echo "=========================================="
echo "Base Pi HaLow Bridge Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root: sudo ./setup_base_pi.sh [PSK]"
    exit 1
fi

# Configuration
PROJECT_DIR="/home/robotpi/Desktop/PI-HALOW-BRIDGE"
SERVICE_USER="robotpi"
PSK_FILE="/etc/serpent/psk.key"

# Check if PSK provided as argument
if [ -n "$1" ]; then
    PROVIDED_PSK="$1"
else
    PROVIDED_PSK=""
fi

echo ""
echo "Step 1: Creating directories..."
mkdir -p /etc/serpent
mkdir -p /var/log/serpent
mkdir -p /run/serpent
chown $SERVICE_USER:$SERVICE_USER /var/log/serpent
chown $SERVICE_USER:$SERVICE_USER /run/serpent
chmod 755 /var/log/serpent /run/serpent
echo "✓ Directories created"

echo ""
echo "Step 2: Configuring PSK..."
if [ -n "$PROVIDED_PSK" ]; then
    echo "$PROVIDED_PSK" > "$PSK_FILE"
    chmod 600 "$PSK_FILE"
    chown root:root "$PSK_FILE"
    echo "✓ PSK configured from command line"
elif [ -f "$PSK_FILE" ]; then
    echo "✓ PSK already exists: $PSK_FILE"
else
    echo "ERROR: No PSK provided and none exists!"
    echo "Usage: sudo ./setup_base_pi.sh YOUR_PSK_FROM_ROBOT_PI"
    exit 1
fi

echo ""
echo "Step 3: Installing systemd service..."
# Update service file paths
sed "s|/home/serpentbase|$PROJECT_DIR|g" \
    "$PROJECT_DIR/base_pi/serpent-base-bridge.service" > /tmp/serpent-base-bridge.service
sed -i "s|User=serpentbase|User=$SERVICE_USER|g" /tmp/serpent-base-bridge.service

# Copy to systemd
cp /tmp/serpent-base-bridge.service /etc/systemd/system/
rm /tmp/serpent-base-bridge.service
echo "✓ Service file installed"

echo ""
echo "Step 4: Creating PSK environment file..."
mkdir -p /etc/systemd/system/serpent-base-bridge.service.d
cat > /etc/systemd/system/serpent-base-bridge.service.d/psk.conf <<EOF
[Service]
Environment="SERPENT_PSK_HEX=$(cat $PSK_FILE)"
EOF
echo "✓ PSK configured for service"

echo ""
echo "Step 5: Reloading systemd..."
systemctl daemon-reload
echo "✓ Systemd reloaded"

echo ""
echo "Step 6: Enabling service..."
systemctl enable serpent-base-bridge.service
echo "✓ Service enabled"

echo ""
echo "=========================================="
echo "✓ Base Pi Bridge Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Start service: sudo systemctl start serpent-base-bridge"
echo "2. Check status: sudo systemctl status serpent-base-bridge"
echo "3. View logs: sudo journalctl -u serpent-base-bridge -f"
echo ""

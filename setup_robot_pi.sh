#!/bin/bash
# Setup script for Robot Pi HaLow Bridge
# Run with: sudo ./setup_robot_pi.sh

set -e  # Exit on error

echo "=========================================="
echo "Robot Pi HaLow Bridge Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root: sudo ./setup_robot_pi.sh"
    exit 1
fi

# Configuration
PROJECT_DIR="/home/robotpi/Desktop/PI-HALOW-BRIDGE"
SERVICE_USER="robotpi"
PSK_FILE="/etc/serpent/psk.key"

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
echo "Step 2: Generating PSK (if not exists)..."
if [ ! -f "$PSK_FILE" ]; then
    # Generate 64-character hex key (256-bit)
    python3 -c "import secrets; print(secrets.token_hex(32))" > "$PSK_FILE"
    chmod 600 "$PSK_FILE"
    chown root:root "$PSK_FILE"
    echo "✓ PSK generated: $PSK_FILE"
else
    echo "✓ PSK already exists: $PSK_FILE"
fi

echo ""
echo "Step 3: Installing systemd service..."
# Update service file paths to use actual user home
sed "s|/home/serpentbase|$PROJECT_DIR|g" \
    "$PROJECT_DIR/robot_pi/serpent-robot-bridge.service" > /tmp/serpent-robot-bridge.service
sed -i "s|User=serpentbase|User=$SERVICE_USER|g" /tmp/serpent-robot-bridge.service

# Copy to systemd
cp /tmp/serpent-robot-bridge.service /etc/systemd/system/
rm /tmp/serpent-robot-bridge.service
echo "✓ Service file installed"

echo ""
echo "Step 4: Creating PSK environment file..."
cat > /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf <<EOF
[Service]
Environment="SERPENT_PSK_HEX=$(cat $PSK_FILE)"
EOF
mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d
cat > /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf <<EOF
[Service]
Environment="SERPENT_PSK_HEX=$(cat $PSK_FILE)"
EOF
echo "✓ PSK configured for service"

echo ""
echo "Step 5: Adding user to required groups..."
usermod -a -G i2c,gpio,video $SERVICE_USER || true
echo "✓ User groups updated"

echo ""
echo "Step 6: Reloading systemd..."
systemctl daemon-reload
echo "✓ Systemd reloaded"

echo ""
echo "Step 7: Enabling service..."
systemctl enable serpent-robot-bridge.service
echo "✓ Service enabled"

echo ""
echo "=========================================="
echo "✓ Robot Pi Bridge Setup Complete!"
echo "=========================================="
echo ""
echo "PSK Key: $(cat $PSK_FILE)"
echo ""
echo "IMPORTANT: Copy this PSK to your Base Pi!"
echo "Run on Base Pi: echo 'YOUR_PSK' | sudo tee /etc/serpent/psk.key"
echo ""
echo "Next steps:"
echo "1. Copy PSK to Base Pi (see above)"
echo "2. Start service: sudo systemctl start serpent-robot-bridge"
echo "3. Check status: sudo systemctl status serpent-robot-bridge"
echo "4. View logs: sudo journalctl -u serpent-robot-bridge -f"
echo ""

#!/bin/bash
#
# Deployment script for PI-HALOW-BRIDGE refactored system
#
# Usage: sudo ./scripts/deploy.sh
#

set -e  # Exit on error

echo "=================================================="
echo "PI-HALOW-BRIDGE Deployment Script"
echo "=================================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (use sudo)"
    exit 1
fi

# Configuration
INSTALL_DIR="/home/pi/serpent/pi_halow_bridge"
BACKUP_DIR="/home/pi/serpent/pi_halow_bridge.backup.$(date +%Y%m%d_%H%M%S)"
VENV_DIR="$INSTALL_DIR/venv"

echo "Step 1: Stopping services..."
systemctl stop serpent-base-bridge || true
systemctl stop serpent-robot-bridge || true
echo "✓ Services stopped"
echo ""

echo "Step 2: Creating backup..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Backing up to: $BACKUP_DIR"
    cp -r "$INSTALL_DIR" "$BACKUP_DIR"
    echo "✓ Backup created"
else
    echo "No existing installation found, skipping backup"
fi
echo ""

echo "Step 3: Checking virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi
echo ""

echo "Step 4: Installing dependencies..."
echo "Installing base_pi requirements..."
source "$VENV_DIR/bin/activate"
pip install -q -r "$INSTALL_DIR/base_pi/requirements.txt"
echo "✓ Base Pi dependencies installed"

echo "Installing robot_pi requirements..."
pip install -q -r "$INSTALL_DIR/robot_pi/requirements.txt"
echo "✓ Robot Pi dependencies installed"
deactivate
echo ""

echo "Step 5: Updating systemd services..."
# Copy service files
cp "$INSTALL_DIR/base_pi/serpent-base-bridge.service" /etc/systemd/system/
cp "$INSTALL_DIR/robot_pi/serpent-robot-bridge.service" /etc/systemd/system/

# Reload systemd
systemctl daemon-reload
echo "✓ Systemd services updated"
echo ""

echo "Step 6: Enabling services..."
systemctl enable serpent-base-bridge
systemctl enable serpent-robot-bridge
echo "✓ Services enabled"
echo ""

echo "Step 7: Starting services..."
systemctl start serpent-base-bridge
systemctl start serpent-robot-bridge
echo "✓ Services started"
echo ""

echo "Step 8: Verifying deployment..."
sleep 3

# Check base_pi status
if systemctl is-active --quiet serpent-base-bridge; then
    echo "✓ Base Pi bridge running"
else
    echo "✗ Base Pi bridge NOT running"
    systemctl status serpent-base-bridge --no-pager
fi

# Check robot_pi status
if systemctl is-active --quiet serpent-robot-bridge; then
    echo "✓ Robot Pi bridge running"
else
    echo "✗ Robot Pi bridge NOT running"
    systemctl status serpent-robot-bridge --no-pager
fi
echo ""

echo "=================================================="
echo "Deployment Complete!"
echo "=================================================="
echo ""
echo "Backup location: $BACKUP_DIR"
echo ""
echo "Monitor logs with:"
echo "  journalctl -u serpent-base-bridge -f"
echo "  journalctl -u serpent-robot-bridge -f"
echo ""
echo "Check status with:"
echo "  systemctl status serpent-base-bridge"
echo "  systemctl status serpent-robot-bridge"
echo ""
echo "Rollback if needed:"
echo "  sudo ./scripts/rollback.sh $BACKUP_DIR"
echo ""

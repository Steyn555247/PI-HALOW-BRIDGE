#!/bin/bash
#
# Rollback script for PI-HALOW-BRIDGE
#
# Usage: sudo ./scripts/rollback.sh [backup_directory]
#

set -e

echo "=================================================="
echo "PI-HALOW-BRIDGE Rollback Script"
echo "=================================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (use sudo)"
    exit 1
fi

# Check backup directory argument
if [ -z "$1" ]; then
    echo "ERROR: Please specify backup directory"
    echo "Usage: sudo ./scripts/rollback.sh [backup_directory]"
    exit 1
fi

BACKUP_DIR="$1"
INSTALL_DIR="/home/pi/serpent/pi_halow_bridge"

# Verify backup exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory not found: $BACKUP_DIR"
    exit 1
fi

echo "Rolling back to: $BACKUP_DIR"
echo ""

echo "Step 1: Stopping services..."
systemctl stop serpent-base-bridge || true
systemctl stop serpent-robot-bridge || true
echo "✓ Services stopped"
echo ""

echo "Step 2: Removing current installation..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "✓ Current installation removed"
fi
echo ""

echo "Step 3: Restoring from backup..."
cp -r "$BACKUP_DIR" "$INSTALL_DIR"
echo "✓ Backup restored"
echo ""

echo "Step 4: Restarting services..."
systemctl start serpent-base-bridge
systemctl start serpent-robot-bridge
echo "✓ Services started"
echo ""

echo "=================================================="
echo "Rollback Complete!"
echo "=================================================="
echo ""
echo "Verify with:"
echo "  systemctl status serpent-base-bridge"
echo "  systemctl status serpent-robot-bridge"
echo ""

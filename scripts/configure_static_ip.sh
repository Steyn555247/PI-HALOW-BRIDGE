#!/bin/bash
# Configure static IP for HaLow bridge
# Usage: sudo bash scripts/configure_static_ip.sh --robot
#        sudo bash scripts/configure_static_ip.sh --base

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Parse arguments
MODE=""
if [[ "$1" == "--robot" ]]; then
    MODE="robot"
    STATIC_IP="192.168.100.2"
    OTHER_IP="192.168.100.1"
    ROLE="Robot Pi"
elif [[ "$1" == "--base" ]]; then
    MODE="base"
    STATIC_IP="192.168.100.1"
    OTHER_IP="192.168.100.2"
    ROLE="Base Pi"
else
    echo "Usage: sudo bash $0 --robot|--base"
    echo ""
    echo "  --robot  : Configure Robot Pi (192.168.100.2)"
    echo "  --base   : Configure Base Pi (192.168.100.1)"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}HaLow Bridge - Static IP Configuration${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Configuring ${ROLE} with static IP: ${STATIC_IP}"
echo ""

# Get current IP
CURRENT_IP=$(hostname -I | awk '{print $1}')
echo "Current IP: ${CURRENT_IP}"
echo ""

# Check if dhcpcd is being used
if systemctl is-active --quiet dhcpcd; then
    echo "Detected dhcpcd (Raspberry Pi OS default)"
    CONFIG_METHOD="dhcpcd"
elif command -v nmcli &> /dev/null; then
    echo "Detected NetworkManager"
    CONFIG_METHOD="nmcli"
else
    echo -e "${YELLOW}Warning: Neither dhcpcd nor NetworkManager detected${NC}"
    echo "Will use dhcpcd method"
    CONFIG_METHOD="dhcpcd"
fi

echo ""
read -p "Continue with configuration? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Backup current configuration
echo ""
echo "Creating backup of current network configuration..."
if [[ -f /etc/dhcpcd.conf ]]; then
    cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S)
    echo "Backed up /etc/dhcpcd.conf"
fi

# Configure based on detected method
if [[ "$CONFIG_METHOD" == "dhcpcd" ]]; then
    echo ""
    echo "Configuring dhcpcd for static IP..."

    # Remove any existing HaLow Bridge config
    sed -i '/# HaLow Bridge/,+4d' /etc/dhcpcd.conf

    # Add new configuration
    cat >> /etc/dhcpcd.conf <<EOF

# HaLow Bridge - ${ROLE} Static IP
interface eth0
static ip_address=${STATIC_IP}/24
EOF

    # Only add gateway/DNS for Base Pi (Robot Pi doesn't need internet via HaLow)
    if [[ "$MODE" == "base" ]]; then
        cat >> /etc/dhcpcd.conf <<EOF
static domain_name_servers=8.8.8.8 1.1.1.1
EOF
    else
        # Robot Pi: set gateway to Base Pi for potential internet sharing
        cat >> /etc/dhcpcd.conf <<EOF
static routers=${OTHER_IP}
static domain_name_servers=8.8.8.8 1.1.1.1
EOF
    fi

    echo -e "${GREEN}✓ dhcpcd configured${NC}"

elif [[ "$CONFIG_METHOD" == "nmcli" ]]; then
    echo ""
    echo "Configuring NetworkManager for static IP..."

    # Get connection name
    CONN_NAME=$(nmcli -t -f NAME con show --active | head -n1)
    if [[ -z "$CONN_NAME" ]]; then
        CONN_NAME="Wired connection 1"
    fi

    echo "Using connection: ${CONN_NAME}"

    nmcli con mod "$CONN_NAME" ipv4.addresses "${STATIC_IP}/24"
    nmcli con mod "$CONN_NAME" ipv4.method manual
    nmcli con mod "$CONN_NAME" ipv4.dns "8.8.8.8 1.1.1.1"

    if [[ "$MODE" == "robot" ]]; then
        nmcli con mod "$CONN_NAME" ipv4.gateway "${OTHER_IP}"
    fi

    echo -e "${GREEN}✓ NetworkManager configured${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Configuration complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Reboot this Pi to apply network changes:"
echo "   sudo reboot"
echo ""
echo "2. After reboot, verify the IP:"
echo "   ip addr show eth0"
echo "   # Should show: ${STATIC_IP}/24"
echo ""
echo "3. Test connectivity to other Pi:"
echo "   ping ${OTHER_IP} -c 5"
echo ""
echo "4. Configure the bridge software IP:"
if [[ "$MODE" == "robot" ]]; then
    echo "   cd ${PROJECT_DIR}"
    echo "   sudo bash scripts/set_bridge_ip.sh --robot ${OTHER_IP}"
else
    echo "   cd ${PROJECT_DIR}"
    echo "   sudo bash scripts/set_bridge_ip.sh --base ${OTHER_IP}"
fi
echo ""
echo "See HALOW_SETUP_GUIDE.md for complete setup instructions."
echo ""

read -p "Reboot now? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Rebooting in 3 seconds..."
    sleep 3
    reboot
else
    echo "Remember to reboot before testing!"
fi

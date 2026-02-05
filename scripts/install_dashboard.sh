#!/bin/bash
#
# SERPENT Dashboard Installation Script
#
# Installs the dashboard service on Robot Pi or Base Pi
# Usage: ./install_dashboard.sh [robot|base]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_DIR="$PROJECT_ROOT/dashboard"
VENV_DIR="$PROJECT_ROOT/venv"

echo -e "${GREEN}SERPENT Dashboard Installation${NC}"
echo "================================"

# Check if role specified
ROLE="${1:-auto}"

if [ "$ROLE" != "robot" ] && [ "$ROLE" != "base" ] && [ "$ROLE" != "auto" ]; then
    echo -e "${RED}Error: Invalid role. Use 'robot', 'base', or 'auto'${NC}"
    echo "Usage: $0 [robot|base|auto]"
    exit 1
fi

echo -e "${YELLOW}Role: $ROLE${NC}"

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install dashboard dependencies
echo -e "${YELLOW}Installing dashboard dependencies...${NC}"
pip install -q --upgrade pip
pip install -q -r "$DASHBOARD_DIR/requirements.txt"

echo -e "${GREEN}✓ Dependencies installed${NC}"

# Install systemd service
if [ "$ROLE" == "robot" ]; then
    SERVICE_FILE="serpent-dashboard-robot.service"
    SERVICE_NAME="serpent-dashboard-robot"
elif [ "$ROLE" == "base" ]; then
    SERVICE_FILE="serpent-dashboard-base.service"
    SERVICE_NAME="serpent-dashboard-base"
else
    # Auto-detect
    hostname=$(hostname)
    if [[ $hostname == *"robot"* ]]; then
        SERVICE_FILE="serpent-dashboard-robot.service"
        SERVICE_NAME="serpent-dashboard-robot"
        echo -e "${GREEN}Auto-detected: Robot Pi${NC}"
    else
        SERVICE_FILE="serpent-dashboard-base.service"
        SERVICE_NAME="serpent-dashboard-base"
        echo -e "${GREEN}Auto-detected: Base Pi${NC}"
    fi
fi

echo -e "${YELLOW}Installing systemd service: $SERVICE_NAME${NC}"

# Copy service file
sudo cp "$DASHBOARD_DIR/systemd/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE"

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable "$SERVICE_NAME"

echo -e "${GREEN}✓ Service installed and enabled${NC}"

# Ask if user wants to start now
echo ""
read -p "Start dashboard service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl restart "$SERVICE_NAME"
    echo -e "${GREEN}✓ Service started${NC}"

    # Wait a moment for service to start
    sleep 2

    # Check status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}✓ Dashboard is running${NC}"

        # Determine port
        if [[ $SERVICE_NAME == *"robot"* ]]; then
            PORT=5005
            IP="192.168.1.20"
        else
            PORT=5006
            IP="192.168.1.10"
        fi

        echo ""
        echo -e "${GREEN}Dashboard URL: http://$IP:$PORT${NC}"
    else
        echo -e "${RED}✗ Service failed to start${NC}"
        echo "Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
else
    echo "Service not started. Start manually with:"
    echo "  sudo systemctl start $SERVICE_NAME"
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME   # Check status"
echo "  sudo systemctl restart $SERVICE_NAME  # Restart"
echo "  sudo journalctl -u $SERVICE_NAME -f   # View logs"

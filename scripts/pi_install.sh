#!/bin/bash
#
# Pi HaLow Bridge Installation Script
#
# Installs system dependencies, creates venv, installs Python packages,
# creates log directories, and optionally generates/configures PSK.
#
# Usage:
#   ./scripts/pi_install.sh          # Install everything
#   ./scripts/pi_install.sh --robot  # Install Robot Pi specific
#   ./scripts/pi_install.sh --base   # Install Base Pi specific
#
# Requirements:
#   - Raspberry Pi OS (Bullseye or later)
#   - sudo access
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
PI_TYPE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --robot)
            PI_TYPE="robot"
            shift
            ;;
        --base)
            PI_TYPE="base"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Detect Pi type if not specified
if [ -z "$PI_TYPE" ]; then
    if [ -d "$PROJECT_ROOT/robot_pi" ] && [ -f "/proc/device-tree/model" ]; then
        log_info "Detected Raspberry Pi"
        echo "Is this the Robot Pi or Base Pi?"
        select opt in "Robot" "Base"; do
            case $opt in
                "Robot") PI_TYPE="robot"; break;;
                "Base") PI_TYPE="base"; break;;
            esac
        done
    else
        log_error "Could not detect Pi type. Use --robot or --base"
        exit 1
    fi
fi

echo "============================================================"
echo "Pi HaLow Bridge Installation - ${PI_TYPE^^} PI"
echo "============================================================"
echo ""

# System dependencies
log_info "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libopencv-dev \
    python3-opencv \
    i2c-tools

# Robot-specific dependencies
if [ "$PI_TYPE" == "robot" ]; then
    log_info "Installing Robot Pi specific dependencies..."
    sudo apt-get install -y \
        python3-smbus \
        python3-rpi.gpio

    # Enable I2C
    if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
        log_info "Enabling I2C..."
        sudo raspi-config nonint do_i2c 0
    fi
fi

# Create virtual environment
VENV_DIR="$PROJECT_ROOT/venv"
if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install Python dependencies
log_info "Installing Python dependencies..."
pip install --upgrade pip

if [ "$PI_TYPE" == "robot" ]; then
    pip install -r "$PROJECT_ROOT/robot_pi/requirements.txt"
else
    pip install -r "$PROJECT_ROOT/base_pi/requirements.txt"
fi

# Create log directory
LOG_DIR="/var/log/serpent"
if [ ! -d "$LOG_DIR" ]; then
    log_info "Creating log directory..."
    sudo mkdir -p "$LOG_DIR"
    sudo chown $USER:$USER "$LOG_DIR"
fi

# PSK configuration
PSK_FILE="/etc/serpent/psk"
if [ ! -f "$PSK_FILE" ]; then
    log_info "No PSK configured."
    echo ""
    echo "A Pre-Shared Key (PSK) is required for authentication."
    echo "Options:"
    echo "  1. Generate new PSK (do this on ONE Pi, then copy to other)"
    echo "  2. Enter existing PSK"
    echo ""
    read -p "Generate new PSK? [y/N] " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        PSK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        log_info "Generated PSK: $PSK"
        echo ""
        echo "IMPORTANT: Copy this PSK to the other Pi!"
        echo ""
    else
        read -p "Enter PSK (64 hex characters): " PSK
        if [ ${#PSK} -ne 64 ]; then
            log_error "PSK must be exactly 64 hex characters"
            exit 1
        fi
    fi

    # Save PSK
    sudo mkdir -p /etc/serpent
    echo "$PSK" | sudo tee "$PSK_FILE" > /dev/null
    sudo chmod 600 "$PSK_FILE"
    log_info "PSK saved to $PSK_FILE"
else
    log_info "PSK already configured at $PSK_FILE"
fi

# Verify configuration
echo ""
log_info "Verifying installation..."

# Check I2C (Robot only)
if [ "$PI_TYPE" == "robot" ]; then
    if i2cdetect -y 1 > /dev/null 2>&1; then
        log_info "I2C: OK"
    else
        log_warn "I2C: Not working (check 'sudo raspi-config' -> Interface Options -> I2C)"
    fi
fi

# Check Python modules
python3 -c "import cv2; print(f'OpenCV: {cv2.__version__}')" || log_warn "OpenCV not working"

if [ "$PI_TYPE" == "robot" ]; then
    python3 -c "import RPi.GPIO; print('RPi.GPIO: OK')" || log_warn "RPi.GPIO not working"
fi

echo ""
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Ensure PSK is identical on both Pis"
echo "  2. Run: ./scripts/pi_enable_services.sh"
echo "  3. Check status: sudo systemctl status serpent-${PI_TYPE}-bridge"
echo ""

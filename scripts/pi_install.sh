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

# Robot-specific dependencies and Python version
# Robot Pi deps (e.g. some Adafruit packages) need Python >=3.7,<3.11 and others >3.9 → use 3.10
PYTHON_FOR_VENV="python3"
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

    # Robot Pi needs Python 3.10–3.12 (motoron and some Adafruit packages don't support 3.13 yet)
    for py in python3.12 python3.11 python3.10; do
        if command -v "$py" &>/dev/null; then
            PYTHON_FOR_VENV="$py"
            log_info "Using $py for venv (Robot Pi compatibility)"
            break
        fi
    done
    if [ "$PYTHON_FOR_VENV" = "python3" ]; then
        log_info "No Python 3.10–3.12 found; trying apt..."
        for pkg in python3.12 python3.11 python3.10; do
            if sudo apt-get install -y "${pkg}" "${pkg}-venv" "${pkg}-dev" 2>/dev/null; then
                PYTHON_FOR_VENV="$pkg"
                log_info "Using $pkg for venv"
                break
            fi
        done
    fi
    # Check if default python is 3.13+ (incompatible with motoron)
    DEFAULT_PY_VER=$("python3" -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null || echo "0 0")
    if [ "$PYTHON_FOR_VENV" = "python3" ] && [ "$DEFAULT_PY_VER" = "3 13" ] || [ "$DEFAULT_PY_VER" = "3 14" ]; then
        log_error "Robot Pi requires Python 3.10, 3.11, or 3.12 (motoron does not support 3.13+)."
        log_error "Your system has Python 3.13. Options:"
        log_error "  1. Use Raspberry Pi OS Bookworm (Python 3.11) - recommended"
        log_error "  2. Install Python 3.12: see SETUP_SECOND_PI.md section 'Robot Pi on Trixie'"
        if [ -d "$PROJECT_ROOT/venv" ]; then
            log_info "Removing existing venv so you can retry after installing a compatible Python..."
            rm -rf "$PROJECT_ROOT/venv"
        fi
        exit 1
    fi
fi

# Create virtual environment (required for Raspberry Pi OS "externally managed" Python)
VENV_DIR="$PROJECT_ROOT/venv"
log_info "Virtual environment directory: $VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment with $PYTHON_FOR_VENV..."
    $PYTHON_FOR_VENV -m venv "$VENV_DIR"
else
    # If Robot Pi and venv was created with 3.13, we must recreate with compatible Python
    if [ "$PI_TYPE" = "robot" ] && [ -f "$VENV_DIR/bin/python3" ]; then
        VENV_VER=$("$VENV_DIR/bin/python3" -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null || echo "0 0")
        if [ "$VENV_VER" = "3 13" ] || [ "$VENV_VER" = "3 14" ]; then
            log_warn "Existing venv uses Python 3.13 (incompatible with motoron). Recreating with $PYTHON_FOR_VENV..."
            rm -rf "$VENV_DIR"
            $PYTHON_FOR_VENV -m venv "$VENV_DIR"
        else
            log_info "Virtual environment already exists, reusing..."
        fi
    else
        log_info "Virtual environment already exists, reusing..."
    fi
fi

# Use venv's pip directly (avoids "externally managed" - never touches system Python)
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python3"

# Install Python dependencies into the venv (explicit path - no activation needed)
log_info "Installing Python dependencies into venv..."
"$VENV_PIP" install --upgrade pip

if [ "$PI_TYPE" == "robot" ]; then
    "$VENV_PIP" install -r "$PROJECT_ROOT/robot_pi/requirements.txt"
else
    "$VENV_PIP" install -r "$PROJECT_ROOT/base_pi/requirements.txt"
fi

# Ensure venv is owned by pi user (service runs as pi, not root)
if [ -n "$SUDO_USER" ]; then
    log_info "Setting venv ownership to $SUDO_USER..."
    sudo chown -R "$SUDO_USER:$SUDO_USER" "$VENV_DIR"
fi

log_info "Python packages installed successfully into venv."

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

# Check Python modules (use venv's python)
"$VENV_PYTHON" -c "import cv2; print(f'OpenCV: {cv2.__version__}')" || log_warn "OpenCV not working"
"$VENV_PYTHON" -c "import socketio; print('socketio: OK')" || log_warn "socketio not working"

if [ "$PI_TYPE" == "robot" ]; then
    python3 -c "import RPi.GPIO; print('RPi.GPIO: OK')" || log_warn "RPi.GPIO not working"
fi

echo ""
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "Virtual environment ready at: $VENV_DIR"
echo "Python interpreter: $VENV_DIR/bin/python3"
echo ""
echo "Next steps:"
echo "  1. Ensure PSK is identical on both Pis"
echo "  2. Run: sudo bash scripts/pi_enable_services.sh --${PI_TYPE}"
echo "  3. Check status: sudo systemctl status serpent-${PI_TYPE}-bridge"
echo ""

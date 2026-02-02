#!/bin/bash
#
# Enable and start systemd services for Pi HaLow Bridge
#
# Usage:
#   ./scripts/pi_enable_services.sh          # Auto-detect Pi type
#   ./scripts/pi_enable_services.sh --robot  # Robot Pi
#   ./scripts/pi_enable_services.sh --base   # Base Pi
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# Detect Pi type
if [ -z "$PI_TYPE" ]; then
    echo "Is this the Robot Pi or Base Pi?"
    select opt in "Robot" "Base"; do
        case $opt in
            "Robot") PI_TYPE="robot"; break;;
            "Base") PI_TYPE="base"; break;;
        esac
    done
fi

SERVICE_NAME="serpent-${PI_TYPE}-bridge"
SERVICE_FILE="${PI_TYPE}_pi/serpent-${PI_TYPE}-bridge.service"
SERVICE_PATH="$PROJECT_ROOT/$SERVICE_FILE"

echo "============================================================"
echo "Enabling ${SERVICE_NAME} Service"
echo "============================================================"
echo ""

# Check service file exists
if [ ! -f "$SERVICE_PATH" ]; then
    log_error "Service file not found: $SERVICE_PATH"
    exit 1
fi

# Resolve to absolute path (handles symlinks, relative paths)
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python3"
BRIDGE_SCRIPT="$PROJECT_ROOT/base_pi/halow_bridge.py"
if [ "$PI_TYPE" == "robot" ]; then
    BRIDGE_SCRIPT="$PROJECT_ROOT/robot_pi/halow_bridge.py"
fi

# Verify venv and Python exist before installing service
if [ ! -f "$VENV_PYTHON" ]; then
    log_error "Python venv not found at: $VENV_PYTHON"
    log_error "Run pi_install.sh first from the project directory."
    exit 1
fi
if [ ! -f "$BRIDGE_SCRIPT" ]; then
    log_error "Bridge script not found: $BRIDGE_SCRIPT"
    exit 1
fi
log_info "Using venv: $VENV_PYTHON"
log_info "Using script: $BRIDGE_SCRIPT"

# Check PSK is configured
PSK_FILE="/etc/serpent/psk"
if [ ! -f "$PSK_FILE" ]; then
    log_error "PSK not configured. Run pi_install.sh first."
    exit 1
fi

PSK=$(cat "$PSK_FILE")
log_info "PSK configured (${#PSK} chars)"

# Detect run-as user (prefer SUDO_USER when using sudo)
SERVICE_USER="${SUDO_USER:-$USER}"
if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "root" ]; then
    SERVICE_USER="serpentbase"
fi
# Verify user exists
if ! id "$SERVICE_USER" &>/dev/null; then
    log_error "User '$SERVICE_USER' does not exist. Service requires a valid user."
    log_error "Run this script with: sudo -u YOUR_USER bash scripts/pi_enable_services.sh --base"
    exit 1
fi
log_info "Service will run as user: $SERVICE_USER"

# Create systemd drop-in for PSK and User override
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.service.d"
sudo mkdir -p "$DROPIN_DIR"

log_info "Creating drop-in configuration (PSK + User)..."
cat << EOF | sudo tee "$DROPIN_DIR/psk.conf" > /dev/null
[Service]
User=${SERVICE_USER}
Environment="SERPENT_PSK_HEX=${PSK}"
EOF
sudo chmod 600 "$DROPIN_DIR/psk.conf"

# Copy service file, substituting ALL occurrences of the template path
# This handles: WorkingDirectory, ExecStart (venv python + script path)
log_info "Installing service file..."
log_info "Substituting /home/pi/serpent/pi_halow_bridge -> $PROJECT_ROOT"
sed "s|/home/pi/serpent/pi_halow_bridge|$PROJECT_ROOT|g" "$SERVICE_PATH" | sudo tee /etc/systemd/system/"$(basename "$SERVICE_PATH")" > /dev/null

# Reload systemd
log_info "Reloading systemd..."
sudo systemctl daemon-reload

# Enable service
log_info "Enabling ${SERVICE_NAME}..."
sudo systemctl enable "${SERVICE_NAME}"

# Start service
log_info "Starting ${SERVICE_NAME}..."
sudo systemctl start "${SERVICE_NAME}"

# Wait a moment for startup
sleep 2

# Show status
echo ""
log_info "Service status:"
sudo systemctl status "${SERVICE_NAME}" --no-pager || true

echo ""
echo "============================================================"
echo "Service Enabled Successfully!"
echo "============================================================"
echo ""
echo "Useful commands:"
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
echo ""

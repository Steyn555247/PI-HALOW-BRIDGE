#!/bin/bash
#
# Quickly set the other Pi's IP for the bridge (persists across reinstall).
# Writes to /etc/serpent/base_pi_ip (on Robot Pi) or /etc/serpent/robot_pi_ip (on Base Pi),
# updates the service drop-in, and restarts the bridge.
#
# Usage:
#   sudo bash scripts/set_bridge_ip.sh --robot [BASE_PI_IP]   # On Robot Pi: set Base Pi's IP
#   sudo bash scripts/set_bridge_ip.sh --base [ROBOT_PI_IP]   # On Base Pi: set Robot Pi's IP
#   sudo bash scripts/set_bridge_ip.sh                        # Prompts for Pi type and IP
#
# Examples:
#   sudo bash scripts/set_bridge_ip.sh --robot 10.103.198.124
#   sudo bash scripts/set_bridge_ip.sh --base 172.20.10.4
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
PI_TYPE=""
NEW_IP=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --robot) PI_TYPE="robot"; shift ;;
        --base)  PI_TYPE="base";  shift ;;
        [0-9]*.*) NEW_IP="$1"; shift ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Detect Pi type if not specified
if [ -z "$PI_TYPE" ]; then
    echo "Is this the Robot Pi or Base Pi?"
    select opt in "Robot" "Base"; do
        case $opt in
            Robot) PI_TYPE="robot"; break ;;
            Base)  PI_TYPE="base";  break ;;
        esac
    done
fi

# Prompt for IP if not given
if [ -z "$NEW_IP" ]; then
    if [ "$PI_TYPE" == "robot" ]; then
        read -p "Enter Base Pi IP address: " NEW_IP
    else
        read -p "Enter Robot Pi IP address: " NEW_IP
    fi
fi

# Validate IP (basic)
NEW_IP=$(echo "$NEW_IP" | tr -d '\n\r')
if [ -z "$NEW_IP" ]; then
    log_error "IP address is required."
    exit 1
fi

# Ensure /etc/serpent exists
sudo mkdir -p /etc/serpent

if [ "$PI_TYPE" == "robot" ]; then
    IP_FILE="/etc/serpent/base_pi_ip"
    ENV_KEY="BASE_PI_IP"
    SERVICE_NAME="serpent-robot-bridge"
else
    IP_FILE="/etc/serpent/robot_pi_ip"
    ENV_KEY="ROBOT_PI_IP"
    SERVICE_NAME="serpent-base-bridge"
fi

# Write persistent IP file
echo "$NEW_IP" | sudo tee "$IP_FILE" > /dev/null
sudo chmod 644 "$IP_FILE"
log_info "Wrote $ENV_KEY=$NEW_IP to $IP_FILE"

# Update the service drop-in (psk.conf) so the new IP takes effect without re-running pi_enable_services.sh
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.service.d"
DROPIN_FILE="$DROPIN_DIR/psk.conf"

if [ ! -f "$DROPIN_FILE" ]; then
    log_warn "Drop-in $DROPIN_FILE not found. Run: sudo bash scripts/pi_enable_services.sh --${PI_TYPE}"
    log_info "IP saved to $IP_FILE; it will be used next time you run pi_enable_services.sh."
    exit 0
fi

# Read current drop-in, add or replace the IP line, write back
TMP_FILE=$(mktemp)
sudo cat "$DROPIN_FILE" > "$TMP_FILE"

if grep -q "Environment=\"${ENV_KEY}=" "$TMP_FILE"; then
    # Replace existing line (GNU sed on Raspberry Pi; BSD sed uses -i '')
    sed -i.bak "s|Environment=\"${ENV_KEY}=.*|Environment=\"${ENV_KEY}=${NEW_IP}\"|" "$TMP_FILE" 2>/dev/null || \
    sed -i '' "s|Environment=\"${ENV_KEY}=.*|Environment=\"${ENV_KEY}=${NEW_IP}\"|" "$TMP_FILE"
    rm -f "${TMP_FILE}.bak"
else
    # Append new line
    echo "Environment=\"${ENV_KEY}=${NEW_IP}\"" >> "$TMP_FILE"
fi

sudo tee "$DROPIN_FILE" < "$TMP_FILE" > /dev/null
sudo chmod 600 "$DROPIN_FILE"
rm -f "$TMP_FILE"
log_info "Updated $DROPIN_FILE with $ENV_KEY=$NEW_IP"

# Reload and restart
log_info "Reloading systemd and restarting ${SERVICE_NAME}..."
sudo systemctl daemon-reload
sudo systemctl restart "${SERVICE_NAME}"

echo ""
log_info "Done. $ENV_KEY is now $NEW_IP (saved in $IP_FILE)."
log_info "Service restarted. Check: sudo systemctl status ${SERVICE_NAME}"
echo ""

#!/bin/bash
# Setup PSK on Hub/Base Pi
# Run this script on the Hub at 192.168.1.10

set -e

PSK="1deefbb6fd8b1c5684c6481733c6fc6ff88c00262470464533354b73efbdb6f1"

echo "=========================================="
echo "Setting up PSK on Hub/Base Pi"
echo "=========================================="
echo

# Create PSK config for base bridge
echo "Creating PSK config for serpent-base-bridge..."
sudo mkdir -p /etc/systemd/system/serpent-base-bridge.service.d/
sudo bash -c "cat > /etc/systemd/system/serpent-base-bridge.service.d/psk.conf" <<EOF
[Service]
Environment="SERPENT_PSK_HEX=${PSK}"
EOF
sudo chmod 600 /etc/systemd/system/serpent-base-bridge.service.d/psk.conf

# Create PSK config for dashboard (if it needs it)
echo "Creating PSK config for serpent-dashboard-base..."
sudo mkdir -p /etc/systemd/system/serpent-dashboard-base.service.d/
sudo bash -c "cat > /etc/systemd/system/serpent-dashboard-base.service.d/psk.conf" <<EOF
[Service]
Environment="SERPENT_PSK_HEX=${PSK}"
EOF
sudo chmod 600 /etc/systemd/system/serpent-dashboard-base.service.d/psk.conf

# Reload systemd
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Restart services
echo "Restarting services..."
sudo systemctl restart serpent-base-bridge
sudo systemctl restart serpent-dashboard-base

echo
echo "✅ PSK configured successfully!"
echo
echo "Verify PSK is loaded:"
echo "  sudo journalctl -u serpent-base-bridge -n 20 | grep 'PSK'"
echo
echo "You should see: '[base_pi] PSK loaded successfully'"

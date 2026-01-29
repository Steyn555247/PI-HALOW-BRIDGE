#!/usr/bin/env python3
"""
PSK Generator for Serpent Pi HaLow Bridge

Generates a cryptographically secure 256-bit pre-shared key (PSK)
for HMAC-SHA256 authentication between Base Pi and Robot Pi.

IMPORTANT:
- Generate ONCE and deploy to BOTH Pis
- Keep the PSK secure - anyone with it can control the robot
- Store in systemd drop-in file, not in code repository
"""

import secrets
import sys


def generate_psk() -> str:
    """Generate a 256-bit PSK as hex string"""
    return secrets.token_hex(32)


def print_deployment_instructions(psk: str):
    """Print deployment instructions"""
    print("=" * 70)
    print("SERPENT PI HALOW BRIDGE - PSK GENERATED")
    print("=" * 70)
    print()
    print("PSK (64 hex characters):")
    print(f"  {psk}")
    print()
    print("-" * 70)
    print("DEPLOYMENT INSTRUCTIONS")
    print("-" * 70)
    print()
    print("1. On BOTH Robot Pi and Base Pi, create a systemd drop-in:")
    print()
    print("   For Robot Pi:")
    print("   $ sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d")
    print("   $ sudo nano /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf")
    print()
    print("   For Base Pi:")
    print("   $ sudo mkdir -p /etc/systemd/system/serpent-base-bridge.service.d")
    print("   $ sudo nano /etc/systemd/system/serpent-base-bridge.service.d/psk.conf")
    print()
    print("2. Add the following content to psk.conf on BOTH Pis:")
    print()
    print("   [Service]")
    print(f'   Environment="SERPENT_PSK_HEX={psk}"')
    print()
    print("3. Set restrictive permissions:")
    print()
    print("   $ sudo chmod 600 /etc/systemd/system/serpent-*-bridge.service.d/psk.conf")
    print()
    print("4. Reload and restart:")
    print()
    print("   $ sudo systemctl daemon-reload")
    print("   $ sudo systemctl restart serpent-robot-bridge  # on Robot Pi")
    print("   $ sudo systemctl restart serpent-base-bridge   # on Base Pi")
    print()
    print("-" * 70)
    print("SECURITY NOTES")
    print("-" * 70)
    print()
    print("- The PSK must be IDENTICAL on both Pis")
    print("- Keep this PSK secret - it authorizes robot control")
    print("- If compromised, generate a new PSK and redeploy")
    print("- Do NOT commit the PSK to version control")
    print()
    print("=" * 70)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    psk = generate_psk()
    print_deployment_instructions(psk)


if __name__ == '__main__':
    main()

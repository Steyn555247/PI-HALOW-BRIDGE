# Claude Prompt: Persist IPs in Both Apps + Quick IP-Change Script

Copy the block below into a new chat with Claude (with this repo in context). Claude will implement the changes.

---

## Copy-paste prompt for Claude

```
In the Pi HaLow Bridge repo (pi_halow_bridge), do the following.

## 1. Persist IPs in both applications (survive reinstall)

**Robot Pi – Base Pi IP**
- The Robot Pi bridge needs BASE_PI_IP (the Base Pi’s IP) to connect.
- When enabling the robot service, the script should read BASE_PI_IP from a persistent file that it never overwrites, e.g. `/etc/serpent/base_pi_ip` (one line: the IP, no extra whitespace).
- In `scripts/pi_enable_services.sh`, when installing the **robot** service (PI_TYPE == robot): if `/etc/serpent/base_pi_ip` exists, read its contents (trim newlines/carriage returns) and inject `Environment="BASE_PI_IP=<value>"` into the same drop-in (e.g. psk.conf) that already has User and SERPENT_PSK_HEX. So every time the user runs `pi_enable_services.sh --robot`, the script writes BASE_PI_IP from that file into the service; re-running the script must not revert it to the default.

**Base Pi – Robot Pi IP**
- The Base Pi bridge needs ROBOT_PI_IP (the Robot Pi’s IP) to connect.
- When enabling the base service, the script should read ROBOT_PI_IP from a persistent file that it never overwrites, e.g. `/etc/serpent/robot_pi_ip` (one line: the IP).
- In `scripts/pi_enable_services.sh`, when installing the **base** service (PI_TYPE == base): if `/etc/serpent/robot_pi_ip` exists, read its contents (trim newlines/carriage returns) and inject `Environment="ROBOT_PI_IP=<value>"` into the same drop-in (psk.conf) that has User and SERPENT_PSK_HEX. So every time the user runs `pi_enable_services.sh --base`, the script writes ROBOT_PI_IP from that file; re-running must not revert it.

**Templates**
- The main service templates (`base_pi/serpent-base-bridge.service` and `robot_pi/serpent-robot-bridge.service`) can keep their default IPs (e.g. 192.168.100.1 / 192.168.100.2); the drop-in will override them when the persistent files exist.

## 2. Quick IP-change script

Create a single script the user can run to change the other Pi’s IP quickly, without re-running the full install or editing systemd by hand.

**Path:** `scripts/set_bridge_ip.sh`

**Behaviour:**
- **On Robot Pi:** set Base Pi’s IP. Reads or prompts for the IP, writes it to `/etc/serpent/base_pi_ip`, updates the service drop-in (psk.conf) to add or replace `Environment="BASE_PI_IP=<ip>"`, then runs `systemctl daemon-reload` and `systemctl restart serpent-robot-bridge`.
- **On Base Pi:** set Robot Pi’s IP. Reads or prompts for the IP, writes it to `/etc/serpent/robot_pi_ip`, updates the service drop-in (psk.conf) to add or replace `Environment="ROBOT_PI_IP=<ip>"`, then runs `systemctl daemon-reload` and `systemctl restart serpent-base-bridge`.

**Usage:**
- `sudo bash scripts/set_bridge_ip.sh --robot [BASE_PI_IP]`   → on Robot Pi: set Base Pi’s IP (prompt if IP omitted).
- `sudo bash scripts/set_bridge_ip.sh --base [ROBOT_PI_IP]`   → on Base Pi: set Robot Pi’s IP (prompt if IP omitted).
- `sudo bash scripts/set_bridge_ip.sh`                        → prompt for Pi type (Robot/Base) then prompt for IP.

**Implementation notes:**
- Ensure `/etc/serpent` exists (mkdir -p).
- When updating the drop-in, read the current psk.conf (with sudo), then either replace the existing `Environment="BASE_PI_IP=..."` or `Environment="ROBOT_PI_IP=..."` line, or append it if missing; write back with sudo and chmod 600.
- After updating the drop-in, run `sudo systemctl daemon-reload` and `sudo systemctl restart <service>`.
- Make the script executable and robust (trim IP, basic non-empty check). Use a temp file for editing the drop-in if needed.

## 3. Documentation

- In `SETUP_SECOND_PI.md` (or the main setup doc), add a short section that explains:
  - **Robot Pi:** one-time set Base Pi IP: `echo "<BASE_PI_IP>" | sudo tee /etc/serpent/base_pi_ip`, then run `sudo bash scripts/pi_enable_services.sh --robot`. Or use `sudo bash scripts/set_bridge_ip.sh --robot <BASE_PI_IP>` to set and apply immediately.
  - **Base Pi:** one-time set Robot Pi IP: `echo "<ROBOT_PI_IP>" | sudo tee /etc/serpent/robot_pi_ip`, then run `sudo bash scripts/pi_enable_services.sh --base`. Or use `sudo bash scripts/set_bridge_ip.sh --base <ROBOT_PI_IP>` to set and apply immediately.
  - To change IP later: run `sudo bash scripts/set_bridge_ip.sh --robot <ip>` or `--base <ip>` (or with no args to be prompted).

Implement all of the above in the repo. After your changes, re-running `pi_install.sh` and `pi_enable_services.sh` must not revert the IPs as long as the user has created `/etc/serpent/base_pi_ip` (on Robot Pi) and/or `/etc/serpent/robot_pi_ip` (on Base Pi). The quick script must update both the persistent file and the service drop-in and restart the bridge.
```

---

Paste the block above into a new Claude chat with the pi_halow_bridge repo in context so Claude can apply the edits.

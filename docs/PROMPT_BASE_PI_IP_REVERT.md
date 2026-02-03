# Prompt for Claude: Fix BASE_PI_IP Reverting to Default on Robot Pi

Use this prompt in a new chat with Claude (or another AI) to have it verify or fix the issue where `BASE_PI_IP` on the Robot Pi keeps reverting to `192.168.100.1` after the user sets it.

---

## Copy-paste prompt for Claude

```
## Context

Pi HaLow Bridge project: two Raspberry Pis – Base Pi (operator) and Robot Pi (on robot). They talk over TCP (control, telemetry, video). The Robot Pi must know the Base Pi's IP (BASE_PI_IP) to connect.

## Problem

On the Robot Pi, the user sets BASE_PI_IP to the real Base Pi IP (e.g. 10.103.198.124) via:
- `sudo systemctl edit serpent-robot-bridge` and adding Environment="BASE_PI_IP=10.103.198.124", or
- Creating a drop-in file: /etc/systemd/system/serpent-robot-bridge.service.d/base-pi-ip.conf with [Service] and Environment="BASE_PI_IP=10.103.198.124"

After that, BASE_PI_IP works for a while, but then it "keeps going back" to the old value (192.168.100.1). So the Robot Pi starts connecting to 192.168.100.1 again and video_connected becomes false on the Base Pi.

## Root cause to verify/fix

1. The main service file `robot_pi/serpent-robot-bridge.service` (template) contains `Environment="BASE_PI_IP=192.168.100.1"`.
2. The script `scripts/pi_enable_services.sh` runs `sed ... | sudo tee /etc/systemd/system/serpent-robot-bridge.service` and thus **overwrites the entire main service file** with the template every time the user runs it (e.g. after git pull or re-enabling the service).
3. So the main file in /etc/systemd/system/ always has BASE_PI_IP=192.168.100.1 after any run of pi_enable_services.sh.
4. A separate drop-in (e.g. base-pi-ip.conf) can override that in theory, but: (a) something may be overwriting or not preserving that drop-in, or (b) the user may be re-running pi_enable_services.sh and the script only writes psk.conf – it doesn't touch base-pi-ip.conf, so base-pi-ip.conf should persist unless the user created it in the wrong place or something else removes it. The exact reason the IP "reverts" on the user's system may be: merge order, wrong path, or another tool overwriting the .d directory.

## Required fix

Make BASE_PI_IP **persist** across re-runs of `pi_enable_services.sh` so it never reverts:

1. **Persistent store:** Use a file that the enable script does **not** overwrite as the source of truth for BASE_PI_IP on the Robot Pi. For example: `/etc/serpent/base_pi_ip` containing only the Base Pi IP (one line, no extra whitespace).

2. **Enable script:** In `scripts/pi_enable_services.sh`, when installing the **robot** service (PI_TYPE == robot):
   - If `/etc/serpent/base_pi_ip` exists, read its contents (trim newlines/carriage returns).
   - When writing the drop-in (e.g. psk.conf), **include** `Environment="BASE_PI_IP=<value from file>"` in the same drop-in that already has User and SERPENT_PSK_HEX.
   - So every time the user runs `pi_enable_services.sh --robot`, the script writes BASE_PI_IP from the file into the drop-in; the main service file can keep the default 192.168.100.1 in the template, but the drop-in will override it with the value from the file.

3. **Documentation:** In `SETUP_SECOND_PI.md` (or README), add clear steps:
   - On the Robot Pi, one-time: `echo "<BASE_PI_IP>" | sudo tee /etc/serpent/base_pi_ip` (replace with real Base Pi IP).
   - Then run `sudo bash scripts/pi_enable_services.sh --robot`.
   - So the IP is stored in a place the script never overwrites, and the script injects it into the service drop-in on every run.

4. **Optional:** If the script is run for robot and `/etc/serpent/base_pi_ip` does not exist, the script can leave BASE_PI_IP as the main-file default (192.168.100.1) or prompt the user to create the file; your choice.

Please implement the above in the repo: (1) modify `scripts/pi_enable_services.sh` to read `/etc/serpent/base_pi_ip` when PI_TYPE is robot and include BASE_PI_IP in the drop-in; (2) update the setup doc with the one-time step to create `/etc/serpent/base_pi_ip` on the Robot Pi. After this, re-running the enable script should never revert BASE_PI_IP.
```

---

## What was already changed in this repo

- **`scripts/pi_enable_services.sh`**  
  When enabling the **robot** service, the script now:
  - Checks for `/etc/serpent/base_pi_ip`.
  - If it exists, reads the value and adds `Environment="BASE_PI_IP=<value>"` to the same drop-in (psk.conf) that has User and SERPENT_PSK_HEX.
  - So re-running the script no longer reverts BASE_PI_IP; it keeps writing the value from the file.

- **`SETUP_SECOND_PI.md`**  
  Added a “Robot Pi – set Base Pi IP permanently” section: one-time create `/etc/serpent/base_pi_ip` with the Base Pi IP, then run the enable script.

If you prefer Claude to re-implement or adjust this, use the prompt above in a new chat and point Claude at the `pi_halow_bridge` repo.

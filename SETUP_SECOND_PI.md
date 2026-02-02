# Full Setup: Second Pi (Fresh / First-Time Use)

Use this guide to install the Pi HaLow Bridge on a **second Raspberry Pi** that has never been used (or is fresh).  
Assuming your **first Pi is the Base Pi** (operator station), this second Pi will be the **Robot Pi**.

---

## Part 1: Raspberry Pi OS First-Time Setup

### 1.1 Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Insert a microSD card and open Raspberry Pi Imager.
3. Choose:
   - **OS:** Raspberry Pi OS (64-bit) recommended, or Raspberry Pi OS Lite if no desktop needed.
   - **Storage:** Your microSD card.
4. Click the **gear icon** (Settings) and set:
   - **Hostname:** e.g. `robot-pi` (or leave default).
   - **Enable SSH:** Use password authentication (or add your public key).
   - **Set username and password:** e.g. username `serpentbase` (or `pi`), and a strong password.
   - **Configure Wi-Fi** (optional): if you want to use Wi-Fi for setup; HaLow will be used later for the bridge.
   - **Set locale:** Your timezone and keyboard.
5. Click **Save**, then **Write** and wait for the image to finish.

### 1.2 First Boot and Update

1. Insert the SD card into the second Pi and power it on.
2. Connect a monitor and keyboard, or use SSH once you know its IP.

**If using a monitor:**

- Log in with the username and password you set.
- Open a terminal and run:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

**If using SSH:**

- Find the Pi’s IP (router admin page, or `ping robot-pi.local` from another machine).
- From your computer:

```bash
ssh serpentbase@robot-pi.local
# or: ssh serpentbase@192.168.x.x
```

Then on the Pi:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Log in again after reboot.

---

## Part 2: Get the Code on the Second Pi

Use **one** of these methods.

### Option A: Clone from GitHub (easiest if repo is up to date)

On the second Pi:

```bash
cd ~
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE
```

If the repo name is different (e.g. `pi_halow_bridge`), use that folder name and `cd` into it.

### Option B: Copy from your first Pi (USB stick / SCP)

**On the first Pi (Base Pi):**

```bash
# Create a tarball (adjust path if your project lives elsewhere)
cd ~
tar czf pi_halow_bridge.tar.gz pi_halow_bridge
# Or if the folder is named PI-HALOW-BRIDGE:
# tar czf pi_halow_bridge.tar.gz PI-HALOW-BRIDGE
```

Copy `pi_halow_bridge.tar.gz` to a USB stick (or use `scp` to the second Pi).

**On the second Pi:**

```bash
cd ~
# If you copied the file via USB, it might be under /media/... or ~/Downloads
tar xzf pi_halow_bridge.tar.gz
cd pi_halow_bridge
# or: cd PI-HALOW-BRIDGE
```

### Option C: Copy from your Windows machine (SCP)

From PowerShell on Windows (adjust paths and IP):

```powershell
scp -r "c:\Serpent Dev\Serpent\Digital\App\Real Prototype\Pi to Pi communication\pi_halow_bridge" serpentbase@robot-pi.local:~/
```

Then on the second Pi:

```bash
cd ~/pi_halow_bridge
```

---

## Part 3: Use the Same PSK as the First Pi

The **Robot Pi** and **Base Pi** must use the **exact same** 64-character hex PSK.

**On the first Pi (Base Pi):**

```bash
sudo cat /etc/serpent/psk
```

Copy the full line (64 hex characters, no spaces/newlines in the key itself).

**On the second Pi (Robot Pi):**

Create the PSK file **before** running the install script (so the script sees it and skips generating a new one):

```bash
sudo mkdir -p /etc/serpent
sudo chmod 700 /etc/serpent
echo "PASTE_THE_64_CHAR_HEX_PSK_HERE" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk
```

Replace `PASTE_THE_64_CHAR_HEX_PSK_HERE` with the key you copied. Verify:

```bash
# Should show 65 (64 chars + newline) or 64 (file is root-only, so use sudo)
sudo wc -c /etc/serpent/psk
```

---

## Part 4: Install the Bridge (Robot Pi)

All commands below are on the **second Pi**, in the project directory (e.g. `~/pi_halow_bridge` or `~/PI-HALOW-BRIDGE`).

### 4.1 Go to project directory

```bash
cd ~/pi_halow_bridge
# or: cd ~/PI-HALOW-BRIDGE
```

Confirm the script exists:

```bash
ls scripts/pi_install.sh
ls robot_pi/
```

### 4.2 Run the install script (Robot Pi)

```bash
sudo bash scripts/pi_install.sh --robot
```

This will:

- Install system packages (Python, OpenCV, I2C tools, RPi.GPIO, etc.)
- Enable I2C (for sensors/actuators)
- Create a virtual environment and install Python dependencies
- Create `/var/log/serpent`
- Use the existing PSK in `/etc/serpent/psk` (if present)

If it asks to generate or enter a PSK, choose **enter existing** and paste the same PSK as on the Base Pi.

### 4.3 Enable and start the service

```bash
sudo bash scripts/pi_enable_services.sh --robot
```

This will:

- Install the systemd unit with the correct paths and user
- Set the PSK in a systemd drop-in
- Enable and start `serpent-robot-bridge`

### 4.4 Check status

```bash
sudo systemctl status serpent-robot-bridge
```

You should see `active (running)`.

View logs:

```bash
sudo journalctl -u serpent-robot-bridge -f
```

Press `Ctrl+C` to stop following.

---

## Part 5: Network (HaLow / IP)

For the two Pis to talk:

- **Base Pi:** e.g. `192.168.100.1`
- **Robot Pi:** e.g. `192.168.100.2`

Configure the HaLow interface (or your link) on each Pi so they are on the same subnet and can ping each other.

**From Base Pi:**

```bash
ping 192.168.100.2
```

**From Robot Pi:**

```bash
ping 192.168.100.1
```

If you use different IPs, set them via systemd or environment (e.g. `BASE_PI_IP` / `ROBOT_PI_IP`) so the bridge uses the correct addresses.

---

## Part 6: Verify End-to-End

**On Base Pi:**

```bash
curl http://localhost:5004/health
```

When the Robot Pi is connected, you should see something like `"video_connected": true` and `"status": "ok"`.

**Optional:** Open in a browser: `http://<base-pi-ip>:5004/video` for the MJPEG stream.

---

## Quick Command Summary (Second Pi Only)

```bash
# 1. First-time: update system (then reboot)
sudo apt update && sudo apt full-upgrade -y && sudo reboot

# 2. Get code (clone or copy – see Part 2)
cd ~
git clone https://github.com/Steyn555247/PI-HALOW-BRIDGE.git
cd PI-HALOW-BRIDGE

# 3. Copy PSK from first Pi, then on second Pi:
sudo mkdir -p /etc/serpent
echo "SAME_64_CHAR_PSK_AS_BASE_PI" | sudo tee /etc/serpent/psk
sudo chmod 600 /etc/serpent/psk

# 4. Install and enable (Robot Pi)
sudo bash scripts/pi_install.sh --robot
sudo bash scripts/pi_enable_services.sh --robot

# 5. Check
sudo systemctl status serpent-robot-bridge
sudo journalctl -u serpent-robot-bridge -f
```

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| "not a git repository" | Run all commands from inside the project folder (e.g. `~/pi_halow_bridge` or `~/PI-HALOW-BRIDGE`). |
| Service fails (status 217/USER) | Ensure the service runs as the same user you use to log in (e.g. `serpentbase`). The install script and service templates use `serpentbase` by default. |
| python3 no such file | Re-run `sudo bash scripts/pi_enable_services.sh --robot` from the project directory so paths and venv are correct. |
| **Python version conflict** (e.g. "requires python >= 3.7, <3.11" or "requires >3.9") | Robot Pi needs Python 3.10. See [Robot Pi: Python 3.10](#robot-pi-python-310) below. |
| PSK mismatch | Copy the exact PSK from the Base Pi again; both Pis must have the same 64-char hex key in `/etc/serpent/psk`. |
| No connection between Pis | Check HaLow/wifi IPs, firewall, and that both services are running. |

### Robot Pi: Python 3.10–3.12 (motoron does not support 3.13)

Robot Pi needs **Python 3.10, 3.11, or 3.12**. The **motoron** package (and some Adafruit deps) do not support Python 3.13 yet. If you see:

- `ERROR: Could not find a version that satisfies the requirement motoron>=1.1.0`
- `Requires-Python >=3.7,<3.11` or `>=3.9,<3.13` and your system has **Python 3.13** (e.g. Raspberry Pi OS Trixie)

do one of the following.

#### Option A: Use Raspberry Pi OS Bookworm (recommended)

**Bookworm** uses Python 3.11, which works with motoron. Reflash the SD card with **Raspberry Pi OS (64-bit) Bookworm** (not Trixie), then run the installer again. No need to install an extra Python.

#### Option B: Robot Pi on Trixie – install Python 3.12

If you want to keep **Raspberry Pi OS Trixie** (Python 3.13), install Python 3.12 and use it for the venv:

1. **Install build deps and Python 3.12:**
   ```bash
   sudo apt update
   sudo apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev \
     libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev
   cd /tmp
   wget https://www.python.org/ftp/python/3.12.7/Python-3.12.7.tgz
   tar -xf Python-3.12.7.tgz
   cd Python-3.12.7
   ./configure --enable-optimizations --prefix=/usr/local
   make -j$(nproc)
   sudo make altinstall
   ```
   Then check: `python3.12 --version` (should show 3.12.x).

2. **Remove the old venv and re-run the installer** (it will use `python3.12`):
   ```bash
   cd ~/PI-HALOW-BRIDGE
   rm -rf venv
   sudo bash scripts/pi_install.sh --robot
   sudo bash scripts/pi_enable_services.sh --robot
   ```

#### Option C: Python 3.10 / 3.11 from apt (Bookworm or older)

On **Bookworm** or older, Python 3.10 or 3.11 may be in the repos:

```bash
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev
# or: python3.11 python3.11-venv python3.11-dev
cd ~/PI-HALOW-BRIDGE
rm -rf venv
sudo bash scripts/pi_install.sh --robot
```

For more detail, see the main [README.md](README.md) and [QUICK_REFERENCE.md](QUICK_REFERENCE.md).

# Update Guide: Refactored Architecture

This guide helps you safely update an existing PI-HALOW-BRIDGE installation to the new refactored modular architecture.

## 🎯 What This Update Includes

- **Base Pi**: 801 LOC → 1,341 LOC (modular architecture with 7 clean modules)
- **Robot Pi**: 752 LOC → modular architecture
- **Performance**: Control failover 8s → <2s (75% improvement)
- **New Features**: Exponential backoff, circuit breakers, TCP keepalive, I2C multiplexer support
- **Safety**: All safety features preserved and enhanced

## 🚀 Quick Update (Automated)

### Prerequisites
- Existing PI-HALOW-BRIDGE installation
- Git repository initialized
- Internet connection to GitHub
- sudo access

### Steps

**On Robot Pi:**
```bash
cd /path/to/PI-HALOW-BRIDGE

# Fetch the update script
git fetch origin
git checkout backup/refactor-complete-2026-02-06

# Run the update
./scripts/update_to_refactored.sh robot
```

**On Base Pi:**
```bash
cd /path/to/PI-HALOW-BRIDGE

# Fetch the update script
git fetch origin
git checkout backup/refactor-complete-2026-02-06

# Run the update
./scripts/update_to_refactored.sh base
```

## 📋 What The Script Does

1. ✅ **Creates backup branch** - Your current state is saved
2. ✅ **Fetches refactored code** - Pulls from GitHub
3. ✅ **Updates dependencies** - Installs any new Python packages
4. ✅ **Fixes service config** - Updates WorkingDirectory paths
5. ✅ **Restarts service** - Applies the changes
6. ✅ **Verifies installation** - Tests imports and service status
7. ✅ **Provides rollback info** - Easy recovery if needed

## 🔍 Manual Update (Step by Step)

If you prefer manual control:

```bash
# 1. Navigate to project
cd /path/to/PI-HALOW-BRIDGE

# 2. Backup current state
git checkout -b backup-before-update-$(date +%Y%m%d)
git add -A
git commit -m "Backup before update"

# 3. Get refactored code
git fetch origin
git checkout backup/refactor-complete-2026-02-06
git pull origin backup/refactor-complete-2026-02-06

# 4. Update dependencies
source venv/bin/activate
pip install -r robot_pi/requirements.txt --upgrade  # or base_pi/requirements.txt
deactivate

# 5. Update service (if on Robot Pi and WorkingDirectory needs fixing)
# Check current WorkingDirectory:
grep "WorkingDirectory" robot_pi/serpent-robot-bridge.service

# If it shows .../robot_pi, update it:
sed -i "s|WorkingDirectory=.*/robot_pi|WorkingDirectory=$(pwd)|g" robot_pi/serpent-robot-bridge.service

# 6. Install updated service
sudo cp robot_pi/serpent-robot-bridge.service /etc/systemd/system/  # or base_pi service
sudo systemctl daemon-reload

# 7. Restart service
sudo systemctl restart serpent-robot-bridge  # or serpent-base-bridge

# 8. Verify
sudo systemctl status serpent-robot-bridge
sudo journalctl -u serpent-robot-bridge -f
```

## ⚠️ Important Notes

### Robot Pi Specific
- **E-STOP will engage during restart** (safety feature)
- You'll need to manually clear E-STOP after update
- Requires hardware access (I2C, GPIO, cameras)
- WorkingDirectory must point to project root (not robot_pi subdirectory)

### Base Pi Specific
- Service should continue working with minimal interruption
- WorkingDirectory should already be correct
- No hardware dependencies

### Both Devices
- **PSK must match** on both devices (`/etc/serpent/psk`)
- Network IPs may need adjustment:
  - Robot Pi: Check `BASE_PI_IP` in service file (default: 192.168.1.1)
  - Base Pi: Check `ROBOT_PI_IP` in service file (default: 192.168.1.2)
- Virtual environment must be in `PROJECT_ROOT/venv`

## 🔄 Rollback Procedure

If something goes wrong, you can easily rollback:

```bash
# 1. Switch back to your backup
git checkout backup-before-update-YYYYMMDD

# 2. Reinstall old service
sudo cp robot_pi/serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3. Restart with old code
sudo systemctl restart serpent-robot-bridge

# 4. Verify
sudo journalctl -u serpent-robot-bridge -f
```

## ✅ Post-Update Verification

### Check Service Status
```bash
sudo systemctl status serpent-robot-bridge
```
Should show: **Active: active (running)**

### Check Logs
```bash
sudo journalctl -u serpent-robot-bridge -n 50
```
Look for:
- "bridge_coordinator initialized"
- No import errors
- Successful connections (if other device is running)

### Verify Module Structure
```bash
source venv/bin/activate
python3 -c "from robot_pi.core import bridge_coordinator; print('✓ Success')"
deactivate
```
Should output: **✓ Success**

### Check Process
```bash
ps aux | grep bridge_coordinator
```
Should show: `python3 -m robot_pi.core.bridge_coordinator`

## 🐛 Troubleshooting

### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u serpent-robot-bridge -n 100
```

**Common issues:**
- Import errors → Check WorkingDirectory in service file
- PSK errors → Verify `/etc/serpent/psk` exists and matches other device
- Permission errors → Check service user/groups (should be serpentbase)

### Import Errors

```bash
# Verify Python path
source venv/bin/activate
python3 -c "import sys; print('\n'.join(sys.path))"

# Test imports
python3 -c "from robot_pi.core import bridge_coordinator"
python3 -c "from common import framing, constants"

deactivate
```

### Service File Path Issues

```bash
# Check service WorkingDirectory
systemctl cat serpent-robot-bridge | grep WorkingDirectory

# Should show project root, not subdirectory
# Correct: WorkingDirectory=/home/user/PI-HALOW-BRIDGE
# Wrong:   WorkingDirectory=/home/user/PI-HALOW-BRIDGE/robot_pi
```

## 📊 Architecture Changes

### Old Structure (Monolithic)
```
robot_pi/
└── halow_bridge.py (752 LOC - everything in one file)
```

### New Structure (Modular)
```
robot_pi/
├── core/
│   ├── bridge_coordinator.py  (400 LOC - main orchestrator)
│   ├── command_executor.py    (280 LOC - command routing)
│   └── watchdog_monitor.py    (160 LOC - safety monitoring)
├── control/
│   └── control_server.py      (320 LOC - TCP server)
├── telemetry/
│   └── telemetry_sender.py    (200 LOC - telemetry client)
└── sensors/
    └── sensor_reader.py       (enhanced with I2C mux)
```

### Base Pi Similar Refactoring
```
base_pi/
├── core/
│   ├── bridge_coordinator.py  (432 LOC)
│   ├── state_manager.py       (277 LOC)
│   ├── backend_client.py      (199 LOC)
│   └── watchdog_monitor.py    (113 LOC)
└── video/
    └── video_http_server.py   (299 LOC)
```

## 📚 Additional Documentation

After updating, see:
- **REFACTORING_STATUS.md** - Complete refactoring summary
- **REFACTORING_COMPLETE.md** - Detailed changes
- **PHASE5_COMPLETE.md** - Robot Pi refactoring details
- **README.md** - Updated usage guide

## 🆘 Getting Help

If you encounter issues:

1. **Check logs first:**
   ```bash
   sudo journalctl -u serpent-robot-bridge -f
   ```

2. **Verify your backup exists:**
   ```bash
   git branch | grep backup-before-update
   ```

3. **Test in simulation mode first** (if possible):
   ```bash
   export SIM_MODE=true
   sudo systemctl restart serpent-robot-bridge
   ```

4. **Rollback if needed** (see Rollback Procedure above)

## 📅 Update History

- **2026-02-06**: Initial refactored release
  - All 10 phases complete
  - Tested and verified on production hardware
  - 17 commits of improvements

---

**Ready to update?** Run the automated script:
```bash
./scripts/update_to_refactored.sh [robot|base]
```

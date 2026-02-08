# Telemetry Data Flow Fix - Implementation Guide

## Quick Summary
Dashboard is throttling 10 Hz sensor data to 1 Hz updates. Fix requires changing 2 configuration values in `dashboard/config.py`.

---

## IMMEDIATE FIX (5 minutes)

### File: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/config.py`

**Current Code (Lines 64-65)**:
```python
# Update Intervals
STATUS_UPDATE_INTERVAL = 1.0  # seconds - WebSocket push rate
STATUS_CACHE_TTL = 1.0  # seconds - Cache aggregated status
```

**Fixed Code**:
```python
# Update Intervals
STATUS_UPDATE_INTERVAL = 0.1  # seconds - WebSocket push rate (matches sensor rate: 10 Hz)
STATUS_CACHE_TTL = 0.05  # seconds - Cache aggregated status (refresh every 50ms)
```

**Why This Works**:
- Sensors send telemetry at 10 Hz (0.1s interval)
- Dashboard will now push updates at 10 Hz instead of 1 Hz
- Cache expires every 50ms instead of 1.0s, forcing fresh data

**Expected Results**:
- Dashboard IMU updates: 1 update/sec → 10 updates/sec (10x improvement)
- Dashboard barometer updates: 1 update/sec → 10 updates/sec (10x improvement)
- User experience: Smooth real-time display vs. jerky 1-second jumps

---

## SECONDARY FIX (Optional - prevents frontend performance issues)

### File: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/static/js/dashboard.js`

**Why**: 10 Hz DOM updates could cause performance issues on lower-end hardware. Add debouncing to render at human-comfortable rate while receiving at full rate.

**Add This Function** (near line 50, after `updateDashboard` function):

```javascript
// Debounce DOM updates to prevent excessive reflows
let lastRenderTime = 0;
const RENDER_DEBOUNCE_MS = 50;  // Render at most 20x/sec (still smooth)

function updateDashboardDebounced(status) {
    const now = Date.now();
    if (now - lastRenderTime >= RENDER_DEBOUNCE_MS) {
        updateDashboard(status);
        lastRenderTime = now;
    }
}
```

**Update WebSocket Handler** (Lines 36-38):

**FROM**:
```javascript
socket.on('status_update', function(data) {
    updateDashboard(data);
});
```

**TO**:
```javascript
socket.on('status_update', function(data) {
    updateDashboardDebounced(data);
});
```

**Result**: 
- Backend sends 10 Hz
- Frontend renders 20 Hz (debounced, smooth but not excessive)
- Browser stays responsive
- No visible performance difference vs. 10 Hz rendering

---

## VERIFICATION STEPS

### 1. Verify Configuration Changed
```bash
grep "STATUS_UPDATE_INTERVAL\|STATUS_CACHE_TTL" /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/config.py
```

Should show:
```
STATUS_UPDATE_INTERVAL = 0.1
STATUS_CACHE_TTL = 0.05
```

### 2. Restart Dashboard Service
```bash
sudo systemctl restart serpent-dashboard.service
# Or if running manually: kill previous process and restart
```

### 3. Monitor Dashboard Push Rate
Open terminal and watch for update frequency:
```bash
journalctl -u serpent-dashboard.service -f | grep -i "status\|update"
```

Should see 10 update messages per second (not 1).

### 4. Monitor Telemetry Reception on Base Pi
```bash
journalctl -u serpent-base-bridge.service -f | grep -i "telemetry"
```

Should show 10 telemetry messages per second consistently.

### 5. Browser Console Test
Open browser developer console (F12) and add this:

```javascript
// Add to browser console
let updateCount = 0;
let lastLogTime = Date.now();

const originalOn = socket.on;
socket.on = function(event, handler) {
    if (event === 'status_update') {
        return originalOn.call(this, event, function(data) {
            updateCount++;
            const now = Date.now();
            if (now - lastLogTime >= 1000) {
                console.log(`Received ${updateCount} updates in last second`);
                updateCount = 0;
                lastLogTime = now;
            }
            handler(data);
        });
    }
    return originalOn.apply(this, arguments);
};
```

Expected output: "Received 10 updates in last second" (not "Received 1 updates in last second")

### 6. Visual Test
1. Open dashboard in browser
2. Watch IMU accelerometer values (e.g., `imu-ax`, `imu-ay`, `imu-az`)
3. Gently move the robot
4. **BEFORE FIX**: Values jump suddenly once per second
5. **AFTER FIX**: Values change smoothly in real-time

---

## ADVANCED FIX OPTIONS (If needed later)

### Option A: Telemetry Buffer Direct Access (Best for Base Pi)

**File**: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/web_server.py`

For Base Pi dashboard, bypass aggregator cache entirely for sensor data:

```python
def status_update_worker():
    """Background worker that pushes status updates via WebSocket"""
    global status_update_running

    logger.info("Status update worker started")

    while status_update_running:
        try:
            # Get cached status (unchanged, slow path)
            status = status_aggregator.get_aggregated_status()

            # For Base Pi: Get fresh sensor data from telemetry buffer
            if config.DASHBOARD_ROLE == 'base_pi' and telemetry_buffer:
                latest_telemetry = telemetry_buffer.get_latest()
                if latest_telemetry:
                    # Inject fresh sensor data
                    status['sensors'] = {
                        'imu': status_aggregator._transform_imu_data(
                            latest_telemetry.get('imu', {})
                        ),
                        'barometer': latest_telemetry.get('barometer', {})
                    }

            # Emit to all connected clients
            socketio.emit('status_update', status, namespace='/ws/status')

            # Sleep until next update
            time.sleep(config.STATUS_UPDATE_INTERVAL)

        except Exception as e:
            logger.error(f"Status update worker error: {e}")
            time.sleep(1)

    logger.info("Status update worker stopped")
```

**Advantage**: Sensor data always from telemetry buffer (0 cache delay)
**Disadvantage**: Requires passing telemetry_buffer to web_server

### Option B: Split Fast/Slow Paths (Most Flexible)

**File**: `/home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/status_aggregator.py`

```python
def get_sensor_data_fresh() -> Dict:
    """Get fresh sensor data without caching"""
    if config.DASHBOARD_ROLE == 'base_pi':
        # Get from telemetry buffer if available
        # Return latest sensor data
        pass
    else:
        # Get from direct inspection or logs
        pass

def get_aggregated_status_cached() -> Dict:
    """Get slower-updating status with caching"""
    # Existing logic, unchanged
    pass

def get_aggregated_status() -> Dict:
    """Combined: fast sensors + cached status"""
    status = get_aggregated_status_cached()
    sensors = get_sensor_data_fresh()
    if sensors:
        status['sensors'] = sensors
    return status
```

**Advantage**: Clean separation of concerns
**Disadvantage**: More code changes

---

## TROUBLESHOOTING

### Issue: Dashboard still showing 1 Hz updates after restart

**Check 1**: Verify config actually changed
```bash
python3 -c "from dashboard import config; print(f'Interval: {config.STATUS_UPDATE_INTERVAL}, TTL: {config.STATUS_CACHE_TTL}')"
```

**Check 2**: Verify Python loaded new config (not cached)
```bash
# Stop any running dashboard processes
ps aux | grep dashboard.py

# Kill all instances
killall python3

# Wait 2 seconds, then restart
sleep 2
systemctl restart serpent-dashboard.service
```

**Check 3**: Verify telemetry is actually arriving at 10 Hz
```bash
journalctl -u serpent-base-bridge.service -f --lines=20 | head -30
# Should show rapid "Telemetry received" messages, not 1 per second
```

### Issue: Dashboard becomes unresponsive

**Likely cause**: CPU overload from too-frequent status aggregation

**Solution**:
1. Increase `STATUS_CACHE_TTL` back to 0.1s
2. Keep `STATUS_UPDATE_INTERVAL` at 0.1s
3. This gives partial improvement while reducing CPU

```python
STATUS_UPDATE_INTERVAL = 0.1  # Still 10 Hz push
STATUS_CACHE_TTL = 0.1        # Cache for 100ms instead of 50ms
```

### Issue: Frontend JavaScript errors after changes

**Likely cause**: Debouncing code has syntax error

**Solution**:
1. Check browser console (F12) for JavaScript errors
2. Verify function was added correctly
3. Clear browser cache: Ctrl+Shift+Delete, then reload

---

## EXPECTED PERFORMANCE IMPACT

### CPU Usage
- Dashboard web_server CPU: +30-50% (from more frequent aggregation)
- Browser CPU: +10-20% (from 20 Hz debounced rendering vs 1 Hz)
- Total system: +2-5% on Raspberry Pi

### Memory Usage
- No significant change (same objects, more frequent updates)

### Network Bandwidth
- WebSocket messages: 10x increase (10 updates/sec vs 1)
- Per message size: Same (~5-10 KB)
- Total bandwidth: +1.5 Mbps (from ~150 Kbps)

### Responsiveness
- Dashboard update latency: 100ms (was 1000ms)
- User experience: Dramatically improved (smooth vs. jumpy)

---

## ROLLBACK PLAN

If issues occur, revert with:

```bash
# Edit the file back
nano /home/robotpi/Desktop/PI-HALOW-BRIDGE/dashboard/config.py

# Change back to:
# STATUS_UPDATE_INTERVAL = 1.0
# STATUS_CACHE_TTL = 1.0

# Save and restart
systemctl restart serpent-dashboard.service
```

Or revert from git:
```bash
cd /home/robotpi/Desktop/PI-HALOW-BRIDGE
git checkout dashboard/config.py
systemctl restart serpent-dashboard.service
```

---

## DEPLOYMENT STEPS

1. **Backup current config**:
   ```bash
   cp dashboard/config.py dashboard/config.py.backup
   ```

2. **Make changes**:
   ```bash
   # Edit file and update two lines (64-65)
   nano dashboard/config.py
   ```

3. **Restart services**:
   ```bash
   systemctl restart serpent-dashboard.service
   ```

4. **Verify**:
   ```bash
   # Watch for 10 updates/sec
   journalctl -u serpent-dashboard.service -f | grep status_update
   ```

5. **Test in browser**:
   - Open http://base-pi:5006 (or robot-pi:5005)
   - Move robot, watch sensors update smoothly
   - No jumpy 1-second delays

6. **Monitor for issues**:
   ```bash
   # Leave this running for 1-2 hours
   journalctl -u serpent-dashboard.service -f
   ```

---

## TESTING CHECKLIST

- [ ] Config file shows new values (0.1 and 0.05)
- [ ] Dashboard service restarted
- [ ] Telemetry reception still at 10 Hz (verified in logs)
- [ ] Dashboard push rate now 10 Hz (verified in logs)
- [ ] Browser console shows 10 updates/sec
- [ ] IMU/barometer values update smoothly
- [ ] No "Service Unavailable" errors in browser
- [ ] Dashboard CPU usage acceptable (<50%)
- [ ] Dashboard memory stable
- [ ] All other dashboard features still working


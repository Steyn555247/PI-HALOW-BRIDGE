# Telemetry Data Flow Analysis: IMU and Barometer Update Delays

## Executive Summary

**PRIMARY ISSUE IDENTIFIED**: Dashboard configuration has `STATUS_UPDATE_INTERVAL = 1.0 second`, which creates a **10x bottleneck** despite sensors and network updating at 10 Hz (0.1s).

**ROOT CAUSE**: The dashboard's status aggregator caches data for 1.0 second, and the Flask WebSocket push rate is hardcoded to 1.0 second, throttling all data updates regardless of upstream speed.

**IMPACT**: Even though sensors read at 10 Hz and telemetry sends at 10 Hz, the dashboard only displays new data once per second maximum.

---

## Complete Data Flow Analysis

### Stage 1: Robot Pi Sensor Reading (10 Hz - 0.1s intervals)
**File**: `robot_pi/sensor_reader.py`

- **IMU (BNO055)** and **Barometer (BMP581)** are read **in parallel** using ThreadPoolExecutor
- `read_interval = 0.1` second (10 Hz)
- Both sensors are submitted concurrently to executor (lines 408-427)
- **Latency**: ~100-150ms per read cycle (parallel execution reduces sequential overhead)

**Status**: ✅ Excellent - reads at maximum speed, parallel processing optimal

---

### Stage 2: Robot Pi Telemetry Assembly and Transmission (10 Hz - 0.1s intervals)
**File**: `robot_pi/core/bridge_coordinator.py` (lines 276-337)

**Telemetry Sender Loop** collects data every 0.1 seconds:
- **Transmission Interval**: `TELEMETRY_INTERVAL = 0.1` second (10 Hz)
- Uses authenticated framing (SecureFramer)
- TCP connection with exponential backoff
- **JSON caching optimization** (phase 5): Reuses serialized JSON if data unchanged

**Status**: ✅ Excellent - transmits at 10 Hz over TCP, authenticated, robust

---

### Stage 3: Base Pi Telemetry Reception (10 Hz arrival rate)
**File**: `base_pi/telemetry_receiver.py`

- **Reception**: Authenticated frame validation (HMAC), timeout=5.0s
- **Callback**: Triggers `_on_telemetry_received()` in bridge coordinator
- **Rate**: Receives ~10 messages per second from Robot Pi

**Status**: ✅ Excellent - receiving at full 10 Hz rate

---

### Stage 4: Base Pi Telemetry Broadcasting via WebSocket
**File**: `base_pi/core/bridge_coordinator.py` (lines 201-240)

When telemetry arrives, the bridge coordinator immediately broadcasts:
- **WebSocket Broadcasting**: Happens IMMEDIATELY when telemetry arrives (10 Hz rate)
- Uses async/await for non-blocking broadcast
- JSON serialization + derived metrics added on-the-fly

**Status**: ✅ Excellent - WebSocket sends at full 10 Hz upstream

---

### Stage 5: Dashboard Status Aggregator (CRITICAL BOTTLENECK)
**File**: `dashboard/config.py` (lines 64-65)

```python
STATUS_UPDATE_INTERVAL = 1.0  # seconds - WebSocket push rate
STATUS_CACHE_TTL = 1.0       # seconds - Cache aggregated status
```

**The Problem**:
1. Status is cached for `1.0 second` (STATUS_CACHE_TTL)
2. Even if fresh data arrives at 10 Hz, the cached response is returned for up to 1.0s
3. New sensor data is **completely ignored** until the cache expires

**File**: `dashboard/web_server.py` (lines 73-94)

```python
def status_update_worker():
    while status_update_running:
        status = status_aggregator.get_aggregated_status()
        socketio.emit('status_update', status, namespace='/ws/status')
        time.sleep(config.STATUS_UPDATE_INTERVAL)  # ← WAITS 1.0 SECOND
```

**Double Throttling**:
- Dashboard waits `1.0 second` between sending updates (line 88)
- Even if it sent faster, the status aggregator would return cached data

**Status**: ❌ CRITICAL BOTTLENECK - 10x slowdown from 10 Hz to 1 Hz

---

### Stage 6: Dashboard Frontend WebSocket Reception
**File**: `dashboard/static/js/dashboard.js` (lines 36-38)

- Frontend receives updates at the rate provided by the backend (currently 1 Hz)
- Frontend renders IMU/barometer data via `updateSensors()` function

**Status**: ❌ Limited by upstream dashboard (1 Hz max)

---

## Data Source Analysis: Where Are IMU and Barometer Coming From?

### Robot Pi Dashboard (Dashboard running on Robot Pi)

Sensor data is extracted from **systemd journal logs**:
- Sensor data comes from bridge's **watchdog monitor** which logs it periodically
- Log parsing happens when cache expires (every 1.0 second)
- **Log Frequency**: Every 1.0 second (watchdog loop runs `time.sleep(1.0)`)

### Base Pi Dashboard (Dashboard running on Base Pi)

Sensor data comes from **two sources**:

1. **Primary**: Systemd journal logs from base bridge service
2. **Alternative** (if no base bridge logs): Falls back to robot bridge logs

The base bridge watchdog extracts data from telemetry buffer every 1.0 second:
- Telemetry buffer stores incoming telemetry from Robot Pi (10 Hz)
- Watchdog reads from buffer every 1.0 second to log
- Dashboard then reads logs when cache expires (every 1.0 second)

---

## The Complete Picture: Where Data Gets Stuck

```
Robot Pi Sensor Reading (10 Hz)
         ↓
   Sensor Reader thread (parallel)
         ↓
Robot Pi Telemetry Assembly (10 Hz)
         ↓
TCP transmission to Base Pi (10 Hz)
         ↓
Base Pi Telemetry Reception (10 Hz)
         ↓
WebSocket broadcast to dashboard (10 Hz) ← FAST
         ↓
Dashboard Aggregator Cache (EXPIRES EVERY 1.0s) ← BOTTLENECK
         ↓
Dashboard Status Update Thread (sleeps 1.0s) ← BOTTLENECK
         ↓
Frontend WebSocket receive (1 Hz max) ← LIMITED BY UPSTREAM
         ↓
Dashboard rendering (updates once per second)
```

---

## Key Findings

### Finding 1: Data IS Arriving at Dashboard at 10 Hz
The WebSocket server on Base Pi is receiving and forwarding telemetry at 10 Hz. The bottleneck is NOT in telemetry reception.

### Finding 2: Dashboard Aggregator Creates Artificial Delay
The status aggregator's 1.0s cache TTL + 1.0s sleep interval creates a 10x slowdown.

### Finding 3: Barometer Updates Are as Fast as IMU Updates
Both barometer and IMU are read in parallel with identical timing. The slowness is not a sensor-specific issue.

### Finding 4: Log Parsing is Secondary
Even on Robot Pi, sensor data comes from systemd logs (updated by watchdog every 1.0s), not directly from sensor reader. This adds another layer of 1.0s delay.

### Finding 5: Direct Inspection Available But Slow
Status aggregator has optional `_add_direct_robot_data()` which can import live sensor data directly. However, this is still called only when cache expires (every 1.0s).

---

## Recommendations to Fix Slow Updates

### Priority 1: Reduce STATUS_UPDATE_INTERVAL (Quick Fix - 5 minute implementation)

**File to modify**: `dashboard/config.py`

**Change**:
```python
# FROM:
STATUS_UPDATE_INTERVAL = 1.0  # seconds
STATUS_CACHE_TTL = 1.0

# TO:
STATUS_UPDATE_INTERVAL = 0.1  # seconds (10 Hz - matches sensor rate)
STATUS_CACHE_TTL = 0.05      # 50ms (refresh every half update cycle)
```

**Expected Impact**: Dashboard updates at 10 Hz instead of 1 Hz (10x improvement)

**Tradeoffs**:
- Higher CPU usage on dashboard (web server + status aggregator running more frequently)
- Higher WebSocket bandwidth (10x more messages to frontend)
- Frontend should debounce rendering updates to avoid excessive DOM manipulation

---

### Priority 2: Bypass Cache for High-Frequency Updates (Medium complexity)

**File to modify**: `dashboard/status_aggregator.py`

**Change**: Split sensor data from other status:
- Get sensor data without cache (always fresh)
- Get connection/health status with cache (slower path)
- Combine both in response

**Expected Impact**: Sensor data updates at 10 Hz, other data at 1 Hz

---

### Priority 3: Tap Telemetry Buffer Directly (Best - 45 minute implementation)

**File to modify**: `dashboard/web_server.py`

For Base Pi dashboard, bypass status_aggregator entirely for telemetry:
- Get cached status (unchanged, slow path)
- Get fresh sensor data from telemetry buffer (fast path)
- Merge both in response

**Expected Impact**: Base Pi dashboard gets real-time sensor data (10 Hz)

---

### Priority 4: Implement Progressive Enhancement in Frontend (Optional)

**File to modify**: `dashboard/static/js/dashboard.js`

- Create separate WebSocket for high-frequency sensor updates
- Update sensors directly without full page redraw
- Decouples sensor updates (10 Hz) from system status updates (1 Hz)

---

## Testing Strategy

To verify the fix works:

1. **Monitor telemetry arrival rate on Base Pi**:
   ```bash
   journalctl -u serpent-base-bridge.service -f | grep "Telemetry received"
   ```

2. **Monitor dashboard push rate**:
   ```bash
   journalctl -u serpent-dashboard.service -f | grep "status_update"
   ```

3. **Frontend console logging**:
   ```javascript
   socket.on('status_update', function(data) {
       console.log('Update received at:', new Date().toLocaleTimeString());
       updateDashboard(data);
   });
   ```

4. **Visual test**: Watch barometer/IMU values updating smoothly (10 Hz) vs. jumpy (1 Hz)

---

## Summary Table

| Stage | Component | Current Rate | Bottleneck | Status |
|-------|-----------|--------------|-----------|--------|
| 1 | Sensor Reading | 10 Hz | None | ✅ Good |
| 2 | Telemetry Sending | 10 Hz | None | ✅ Good |
| 3 | Telemetry Reception | 10 Hz | None | ✅ Good |
| 4 | WebSocket Broadcast | 10 Hz | None | ✅ Good |
| 5 | Dashboard Cache | 1 Hz | 1.0s TTL | ❌ **CRITICAL** |
| 5 | Dashboard Push | 1 Hz | 1.0s sleep | ❌ **CRITICAL** |
| 6 | Frontend Display | 1 Hz | Upstream | ❌ Limited |

---

## Recommendation Priority

**IMMEDIATE (Do First)**:
- Reduce `STATUS_UPDATE_INTERVAL` from 1.0s to 0.1s
- Reduce `STATUS_CACHE_TTL` from 1.0s to 0.05s
- This is a 3-line change with 10x improvement

**SHORT TERM (Week 1)**:
- Add frontend debouncing to prevent DOM thrashing
- Monitor CPU/memory impact on Raspberry Pi
- Fine-tune update intervals based on real hardware

**MEDIUM TERM (Week 2)**:
- Implement telemetry buffer direct access for sensor data
- Create separate fast/slow update paths
- Test on both Robot Pi and Base Pi dashboards

**LONG TERM (Future)**:
- Consider WebRTC or binary protocols for higher throughput
- Implement adaptive rate limiting based on client capability
- Add frontend performance metrics


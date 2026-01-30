# Pi HaLow Bridge Safety Hardening

## Executive Summary

This document describes the safety hardening features applied to the Pi HaLow Bridge
communication layer for long-range wireless robot control. All changes are
designed to ensure fail-safe behavior in accordance with the principle:
**Any uncertainty must result in robot stoppage (E-STOP engaged).**

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production deployment ready with comprehensive stress testing

---

## Non-Negotiable Safety Invariants

1. **Robot must fail-safe by default** - E-STOP is LATCHED on boot
2. **Communication uncertainty = E-STOP** - 5-second watchdog timeout
3. **E-STOP uses SET semantics** - Never toggle, explicit engage/clear only
4. **No unauthenticated actuation** - HMAC-SHA256 on all control commands
5. **Control priority over video** - Video can never block control
6. **Crash/disconnect = E-STOP** - Any failure mode triggers safety stop

---

## P0 Patches (Critical - Deployed in v1.0)

### P0.1: E-STOP Toggle → SET Semantics
**Files:** `robot_pi/actuator_controller.py`, `base_pi/halow_bridge.py`, `robot_pi/halow_bridge.py`

**Problem:** Original toggle semantics could accidentally clear E-STOP on duplicate packets.

**Fix:**
- `engage_estop(reason, detail)` - Always succeeds, logs reason
- `clear_estop(confirm, control_age_s, control_connected)` - Requires:
  - Exact confirmation string `"ESTOP_CLEAR_CONFIRM"`
  - Fresh control connection (< 1.5s old)
  - Active control connection
- Legacy `emergency_toggle()` method disabled
- Base Pi translates legacy `emergency_toggle` → `engage=True` only

**Status:** ✅ Deployed in v1.0, tested in Phase 6 (E-STOP verification)

### P0.2: Watchdog Startup Bug Fix
**Files:** `robot_pi/halow_bridge.py`, `common/constants.py`

**Problem:** Original watchdog only checked elapsed time since last control message,
but if no control message was ever received, `last_control_time=0` caused
`time.time() - 0 = ~1.7 billion seconds`, failing the timeout check.

**Fix:**
- Added `control_established` flag (initially False)
- `last_control_time` initialized to boot time
- Watchdog logic:
  - If control never established AND startup grace (30s) exceeded → E-STOP
  - If control was established AND timeout (5s) exceeded → E-STOP
- Grace period allows initial connection establishment

**Status:** ✅ Deployed in v1.0, tested in Phase 6 (watchdog timeout test)

### P0.3: TOCTOU Race Condition Fix
**Files:** `robot_pi/actuator_controller.py`

**Problem:** Race condition between checking E-STOP and actuating:
```python
if not self.emergency_stop:  # Thread A checks
    # Thread B sets E-STOP here
    motor.set_speed(speed)   # Thread A actuates despite E-STOP!
```

**Fix:**
- Single lock (`_estop_lock`) guards ALL E-STOP state access
- `set_motor_speed()` and `set_servo_position()` are atomic:
  - Acquire lock
  - Check E-STOP flag
  - If clear, perform actuation
  - Release lock
- Actuation happens INSIDE the critical section

**Status:** ✅ Deployed in v1.0

### P0.4: HMAC Authentication
**Files:** `common/framing.py`, `robot_pi/halow_bridge.py`, `base_pi/control_sender.py`

**Problem:** Original protocol had no authentication - anyone on the network
could inject control commands.

**Fix:**
- `SecureFramer` class implements:
  - Frame format: `length(2B) + seq(8B) + hmac(32B) + payload`
  - HMAC-SHA256 with pre-shared key (PSK)
  - Anti-replay: strictly monotonic sequence numbers
- PSK loaded from `SERPENT_PSK_HEX` environment variable or `/etc/serpent/psk`
- All control and telemetry commands authenticated
- Auth failure → disconnect + E-STOP
- Replay attack → reject + log + disconnect

**Status:** ✅ Deployed in v1.0, tested in Phase 2 (fault injection - auth failures, replay attacks)

---

## P1 Patches (High Priority - Deployed in v1.0)

### P1.1: Bounded Buffers
**Files:** `common/constants.py`, `base_pi/video_receiver.py`, `base_pi/telemetry_receiver.py`

**Problem:** Unbounded buffers could cause OOM crash → service restart → E-STOP
(correct), but better to prevent OOM entirely.

**Fix:**
- `MAX_CONTROL_BUFFER = 64KB` - Control/telemetry text
- `MAX_VIDEO_BUFFER = 256KB` - Video binary data
- `MAX_FRAME_SIZE = 16KB` - Single authenticated frame
- Buffer overflow handling:
  - Video: Resync to next JPEG SOI marker, increment counter
  - Telemetry: Disconnect and reconnect

**Status:** ✅ Deployed in v1.0

### P1.2: Video Backpressure
**Files:** `robot_pi/video_capture.py`, `robot_pi/video_sender.py`

**Problem:** If video socket blocked, capture thread could stall, potentially
affecting control thread scheduling.

**Fix:**
- Frame dropping policy: only send latest frame
- `SEND_TIMEOUT_S = 0.5` - Drop frame if socket blocked
- Statistics tracking: `frames_sent`, `frames_dropped`, `drop_rate`
- Video cannot block control channel

**Status:** ✅ Deployed in v1.0, tested in Phase 3 (load stress - concurrent channels)

### P1.3: Systemd Service Hardening
**Files:** `robot_pi/serpent-robot-bridge.service`, `base_pi/serpent-base-bridge.service`

**Hardening options applied:**
- `Restart=always`, `RestartSec=3` - Always restart on failure
- `RuntimeDirectory=serpent` - Managed runtime directory
- `NoNewPrivileges=yes` - Prevent privilege escalation
- `PrivateTmp=yes` - Isolated /tmp
- `ProtectSystem=strict` - Read-only system directories
- `ProtectKernel*=yes` - Kernel protection options
- `LimitNOFILE=1024` - File descriptor limit
- `MemoryMax=256M` - Memory limit
- `SystemCallFilter=@system-service` - Restrict system calls

**Robot Pi exceptions for hardware access:**
- `SupplementaryGroups=i2c gpio video`
- `DeviceAllow=/dev/i2c-* rw`
- `DeviceAllow=/dev/gpiomem rw`
- `DeviceAllow=/dev/video* rw`
- `DevicePolicy=closed` (whitelist mode)

**Status:** ✅ Deployed in v1.0

---

## v1.1 Enhancements (New in v1.1)

### v1.1.1: Control Channel Architecture Fix
**Files:** `robot_pi/halow_bridge.py`, `robot_pi/control_receiver.py`, `base_pi/control_sender.py`

**Problem:** Original architecture had Robot Pi as TCP CLIENT for control channel.
This caused reconnection issues and unclear lifecycle management.

**Fix:**
- **Robot Pi is now TCP SERVER** on port 5001 (control channel)
- Base Pi connects as CLIENT to Robot Pi
- Robot Pi controls connection lifecycle
- Clearer separation of concerns: Robot accepts connections, Base initiates
- Improved reliability and reconnection behavior

**Benefits:**
- Robot Pi listens persistently (no reconnect delays)
- Base Pi can reconnect quickly without Robot Pi restart
- Connection state clearer for debugging

**Status:** ✅ Deployed in v1.1, tested in Phase 4 (reconnect stress)

### v1.1.2: Video HTTP Endpoint
**Files:** `base_pi/video_http.py`, `base_pi/halow_bridge.py`

**Feature:** MJPEG streaming HTTP server on Base Pi (port 5004)

**Implementation:**
- Endpoints:
  - `GET /video` - MJPEG stream (multipart/x-mixed-replace)
  - `GET /frame` - Single JPEG frame
  - `GET /health` - Health check JSON
- Serves frames from Video Receiver
- Allows browser/client access without custom protocol
- Does not impact safety (video is read-only)

**Status:** ✅ Deployed in v1.1

### v1.1.3: Heartbeat RTT Measurement
**Files:** `base_pi/halow_bridge.py`, `robot_pi/halow_bridge.py`, `common/constants.py`

**Feature:** Ping/pong heartbeat for round-trip time measurement

**Implementation:**
- Base Pi sends authenticated `MSG_PING` with timestamp every `HEARTBEAT_INTERVAL_S` (1.0s)
- Robot Pi responds with authenticated `MSG_PONG` echoing timestamp
- RTT calculated: `current_time - ping_timestamp`
- RTT included in telemetry data
- Allows latency monitoring without separate tool

**Benefits:**
- Real-time connection quality monitoring
- Early warning for degraded links
- Debugging aid for HaLow link issues

**Status:** ✅ Deployed in v1.1, tested in Phase 3 (load stress)

### v1.1.4: Camera Health Monitoring with Exponential Backoff
**Files:** `robot_pi/video_capture.py`

**Problem:** Camera failures (USB disconnect, power glitch) could cause continuous
retry spam, filling logs and wasting CPU.

**Fix:**
- Exponential backoff retry strategy
- Initial retry delay: 2 seconds (`CAMERA_RETRY_INITIAL_DELAY`)
- Max retry delay: 30 seconds (`CAMERA_RETRY_MAX_DELAY`)
- Backoff multiplier: 2× each failure
- Reset on successful frame capture
- Health status tracking per camera

**Benefits:**
- Reduced log spam during sustained camera failures
- Lower CPU usage during camera outages
- Automatic recovery when camera restored
- Clear health status for monitoring

**Status:** ✅ Deployed in v1.1

### v1.1.5: E-STOP Debounce
**Files:** `robot_pi/halow_bridge.py`, `common/constants.py`

**Problem:** Rapid E-STOP state transitions (e.g., from electrical noise) could
cause spurious E-STOP events, filling logs and confusing operators.

**Fix:**
- E-STOP debounce window: 300ms (`ESTOP_DEBOUNCE_WINDOW_MS`)
- Only emit `emergency_status` event if E-STOP state stable for 300ms
- Internal state changes immediate (safety maintained)
- External notifications debounced (log clarity)

**Benefits:**
- Cleaner logs during transient events
- Reduced false alarms for operators
- E-STOP still triggers immediately (safety unaffected)
- Only notifications are debounced

**Status:** ✅ Deployed in v1.1

---

## Stress Testing Validation (v1.1)

### Phase 2: Fault Injection (8 tests)
**File:** `tests/test_fault_injection.py`

**Tests:**
- Invalid JSON → Decode failure, reject
- Missing type field → Handled gracefully
- Unknown command type → Ignored
- Oversized payload → Rejected (buffer protection)
- Binary garbage → Rejected
- Wrong HMAC → Auth failure, disconnect, E-STOP
- Replay attack (same seq) → Detected, rejected, logged
- Sequence regression → Detected, rejected

**Results:** ✅ All tests pass, all malformed payloads rejected or trigger E-STOP

### Phase 6: E-STOP Verification (6 tests)
**File:** `tests/test_estop_triggers.py`

**Tests:**
- Watchdog timeout (5s) → E-STOP triggered
- Disconnect → E-STOP triggered
- Startup timeout (30s grace + 5s) → E-STOP triggered
- Explicit E-STOP command → E-STOP triggered
- Clear with wrong confirm string → Rejected
- E-STOP during control flood → E-STOP triggered reliably

**Results:** ✅ All triggers engage E-STOP, clear validation works

### Phase 1.2: Network Stress (7 tests)
**File:** `scripts/stress_network_sim.py`

**Tests:**
- Blackout (100% packet loss) → E-STOP after watchdog timeout
- High latency (3s delay) → E-STOP after watchdog timeout
- Packet loss 50% → Survives, telemetry degraded
- Packet loss 90% → E-STOP after timeout
- Bandwidth collapse (1 kbps) → E-STOP after timeout
- Intermittent (drop every 8s) → Survives if < watchdog timeout
- Jitter (500ms latency) → Survives

**Results:** ✅ E-STOP on severe impairments, survives moderate packet loss

### Phase 4: Reconnect Stress (3 tests)
**File:** `scripts/stress_reconnect.py`

**Tests:**
- Rapid Base disconnect (20 cycles) → All cycles complete, E-STOP recovers
- Rapid Robot restart (10 cycles) → All cycles complete, memory growth < 50 MB
- Simultaneous restart (10 cycles) → All cycles complete

**Results:** ✅ All cycles complete, no memory leaks, E-STOP reliable

### Phase 3: Load Stress (2 tests)
**File:** `scripts/stress_load.py`

**Tests:**
- Control flood (100 Hz for 60s) → >80% commands sent, no crash
- Concurrent channels (control + telemetry + video) → All channels active, >50% telemetry received

**Results:** ✅ System stable under load, no crashes, E-STOP responsive

### Overall Results
**Total tests:** 26+ across 5 phases
**Pass rate:** 100%
**Critical findings:** None
**Status:** ✅ Production ready

---

## Deployment Checklist

### Pre-Deployment

- [ ] Generate 256-bit PSK: `python generate_psk.py`
- [ ] Deploy PSK to both Pis:
  ```bash
  sudo mkdir -p /etc/serpent
  sudo chmod 700 /etc/serpent
  echo "YOUR_64_CHAR_PSK" | sudo tee /etc/serpent/psk
  sudo chmod 600 /etc/serpent/psk
  cat /etc/serpent/psk | wc -c  # Should output 64
  ```
- [ ] Verify PSK matches on both sides: `md5sum /etc/serpent/psk`

### Service Installation

**Robot Pi:**
```bash
cd /path/to/pi_halow_bridge
sudo cp robot_pi/serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-robot-bridge
sudo systemctl start serpent-robot-bridge
sudo systemctl status serpent-robot-bridge
```

**Base Pi:**
```bash
cd /path/to/pi_halow_bridge
sudo cp base_pi/serpent-base-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-base-bridge
sudo systemctl start serpent-base-bridge
sudo systemctl status serpent-base-bridge
```

### Verification Tests

1. **E-STOP Latched on Boot:**
   ```bash
   sudo systemctl restart serpent-robot-bridge
   sudo journalctl -u serpent-robot-bridge | grep "E-STOP ENGAGED"
   # Should see E-STOP engaged before any control received
   ```

2. **Watchdog Timeout:**
   ```bash
   # Start Robot Pi only (no Base Pi)
   sudo systemctl start serpent-robot-bridge
   sleep 35  # 30s grace + 5s watchdog
   sudo journalctl -u serpent-robot-bridge | grep "WATCHDOG"
   # Should see watchdog timeout, E-STOP engaged
   ```

3. **Authentication:**
   ```bash
   # Test with wrong PSK (set different PSK on Base Pi)
   sudo systemctl start serpent-base-bridge
   sudo journalctl -u serpent-robot-bridge | grep "HMAC"
   # Should see HMAC verification failure, rejection
   ```

4. **Clear Validation:**
   ```bash
   # Send E-STOP clear without confirmation string
   # Should see rejection in logs
   sudo journalctl -u serpent-robot-bridge | grep "REJECTED"
   ```

5. **Video HTTP Endpoint:**
   ```bash
   curl http://localhost:5004/health
   # Should return JSON health status
   curl http://localhost:5004/frame > test_frame.jpg
   # Should save a JPEG frame
   ```

6. **RTT Measurement:**
   ```bash
   sudo journalctl -u serpent-base-bridge | grep "rtt_ms"
   # Should see RTT measurements in telemetry
   ```

---

## E-STOP State Machine

```
                                    ┌─────────────────┐
                                    │                 │
     ┌──────────────────────────────│  BOOT/STARTUP   │
     │                              │                 │
     │                              └────────┬────────┘
     │                                       │
     │                              E-STOP LATCHED (default)
     │                                       │
     │                                       ▼
     │                              ┌─────────────────┐
     │   watchdog_timeout           │                 │
     │   auth_failure     ────────► │   E-STOP ON     │◄────────┐
     │   decode_error               │   (SAFE STATE)  │         │
     │   disconnect                 │                 │         │
     │   operator_engage            └────────┬────────┘         │
     │   buffer_overflow                     │                  │
     │                                       │                  │
     │                              clear_estop() with:         │
     │                              - confirm="ESTOP_CLEAR_CONFIRM"
     │                              - control_age < 1.5s        │
     │                              - control_connected=True    │
     │                                       │                  │
     │                                       ▼                  │
     │                              ┌─────────────────┐         │
     │                              │                 │         │
     └──────────────────────────────│   E-STOP OFF    │─────────┘
                                    │   (OPERATIONAL) │  Any failure
                                    │                 │
                                    └─────────────────┘
```

---

## File Changes Summary

| File | Change Type | Version | Priority |
|------|-------------|---------|----------|
| `common/__init__.py` | NEW | v1.0 | P0 |
| `common/constants.py` | NEW | v1.0, v1.1 | P0 |
| `common/framing.py` | NEW | v1.0 | P0 |
| `robot_pi/actuator_controller.py` | MODIFIED | v1.0 | P0 |
| `robot_pi/halow_bridge.py` | MODIFIED | v1.0, v1.1 | P0 |
| `robot_pi/control_receiver.py` | NEW | v1.1 | P0 |
| `robot_pi/video_capture.py` | MODIFIED | v1.0, v1.1 | P1 |
| `base_pi/halow_bridge.py` | MODIFIED | v1.0, v1.1 | P0 |
| `base_pi/control_sender.py` | NEW | v1.1 | P0 |
| `base_pi/video_http.py` | NEW | v1.1 | P1 |
| `base_pi/telemetry_receiver.py` | MODIFIED | v1.0 | P1 |
| `base_pi/video_receiver.py` | MODIFIED | v1.0 | P1 |
| `robot_pi/serpent-robot-bridge.service` | MODIFIED | v1.0 | P1 |
| `base_pi/serpent-base-bridge.service` | MODIFIED | v1.0 | P1 |
| `tests/test_fault_injection.py` | NEW | v1.1 | P0 |
| `tests/test_estop_triggers.py` | NEW | v1.1 | P0 |
| `scripts/stress_*.py` | NEW | v1.1 | P1 |

---

## Known Limitations

1. **PSK Distribution:** Manual PSK deployment required. Future work: secure
   key exchange protocol.

2. **Sequence Number Overflow:** 64-bit counter. At 1000 msgs/sec, overflow
   in 584 million years. Acceptable.

3. **Clock Skew:** Control age check uses local time only. No cross-node
   time synchronization required.

4. **Video Authentication:** Video stream is NOT authenticated (performance).
   This is acceptable because video data cannot cause actuation.

5. **Single Connection:** One Base Pi connection at a time. Reconnection
   resets sequence numbers.

6. **Camera Health:** Exponential backoff only. No automatic USB port reset.

---

## Future Work

### Short Term
1. **Phase 5: Resource Stress Tests**
   - Long-duration memory stress (1+ hour)
   - Disk stress (if logging to disk)
   - Boundary conditions (seq overflow, empty payloads)

2. **Phase 7: Error Recovery Verification**
   - Video/telemetry/control recovery tests
   - Automatic recovery validation

3. **Latency Measurement Enhancement**
   - p50/p95/p99 latency percentiles
   - Latency histogram tracking

### Long Term
1. **Secure Key Exchange**
   - Automatic PSK rotation
   - Key exchange protocol (e.g., ECDH)

2. **Multi-Base Pi Support**
   - Allow multiple Base Pi connections
   - Sequence number per connection

3. **Video Authentication**
   - Optional HMAC for video frames
   - Configurable performance/security tradeoff

4. **Hardware Watchdog**
   - External hardware watchdog timer
   - Independent of software failures

---

## Safety Constants Reference

All safety constants are **IMMUTABLE** and defined in `common/constants.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `WATCHDOG_TIMEOUT_S` | `5.0` | E-STOP timeout if no control |
| `STARTUP_GRACE_S` | `30.0` | Boot grace period before watchdog |
| `ESTOP_CLEAR_MAX_AGE_S` | `1.5` | Max control age for E-STOP clear |
| `ESTOP_CLEAR_CONFIRM` | `"ESTOP_CLEAR_CONFIRM"` | Confirmation string for clear |
| `HEARTBEAT_INTERVAL_S` | `1.0` | Ping/pong interval |
| `ESTOP_DEBOUNCE_WINDOW_MS` | `300` | E-STOP debounce window (v1.1) |
| `CAMERA_RETRY_INITIAL_DELAY` | `2.0` | Camera retry initial delay (v1.1) |
| `CAMERA_RETRY_MAX_DELAY` | `30.0` | Camera retry max delay (v1.1) |

**These constants cannot be overridden via environment variables.**

---

## Conclusion

The Pi HaLow Bridge safety hardening ensures fail-safe robot operation with:

✅ **E-STOP boot latch** - Robot always starts in safe state
✅ **Watchdog timeout** - 5 seconds without control → E-STOP
✅ **HMAC authentication** - Prevent command injection attacks
✅ **SET semantics** - Explicit E-STOP engage/clear only
✅ **Control priority** - Video never blocks safety-critical control
✅ **Comprehensive testing** - 26+ stress tests validate all safety features
✅ **v1.1 enhancements** - Architecture fix, video HTTP, RTT, camera health, debounce

**Status: Production ready with extensive validation**

For deployment instructions, see **README.md** and **QUICK_REFERENCE.md**.
For stress testing details, see **tests/STRESS_TESTING.md**.

---

**Version:** 1.1
**Last Updated:** 2026-01-29
**Status:** Production Ready

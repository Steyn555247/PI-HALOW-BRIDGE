# Pi HaLow Bridge Safety Hardening

## Executive Summary

This document describes the safety hardening patches applied to the Pi HaLow Bridge
communication layer for Serpent Robotics rope-climbing robots. All changes are
designed to ensure fail-safe behavior in accordance with the principle:
**Any uncertainty must result in robot stoppage (E-STOP engaged).**

## Non-Negotiable Safety Invariants

1. **Robot must fail-safe by default** - E-STOP is LATCHED on boot
2. **Communication uncertainty = E-STOP** - 5-second watchdog timeout
3. **E-STOP uses SET semantics** - Never toggle, explicit engage/clear
4. **No unauthenticated actuation** - HMAC-SHA256 on all control commands
5. **Control priority over video** - Video can never block control
6. **Crash/disconnect = E-STOP** - Any failure mode triggers safety stop

---

## P0 Patches (Critical - Must Deploy)

### P0.1: E-STOP Toggle → SET Semantics
**Files:** `robot_pi/actuator_controller.py`, `base_pi/halow_bridge.py`

**Problem:** Original toggle semantics could accidentally clear E-STOP on duplicate packets.

**Fix:**
- `engage_estop(reason, detail)` - Always succeeds, logs reason
- `clear_estop(confirm, control_age_s, control_connected)` - Requires:
  - Exact confirmation string "CLEAR_ESTOP"
  - Fresh control connection (< 1.5s old)
  - Active control connection
- Legacy `clear_emergency_stop()` method DISABLED (raises RuntimeError)
- Base Pi translates legacy `emergency_toggle` → `engage=True` only

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

### P0.4: HMAC Authentication
**Files:** `common/framing.py`, `robot_pi/halow_bridge.py`, `base_pi/control_forwarder.py`

**Problem:** Original protocol had no authentication - anyone on the network
could inject control commands.

**Fix:**
- `SecureFramer` class implements:
  - Frame format: `length(2B) + seq(8B) + hmac(32B) + payload`
  - HMAC-SHA256 with pre-shared key (PSK)
  - Anti-replay: strictly monotonic sequence numbers
- PSK loaded from `SERPENT_PSK_HEX` environment variable
- All control commands authenticated; auth failure → disconnect + E-STOP

---

## P1 Patches (High Priority - Deploy Soon)

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

### P1.2: Video Backpressure
**Files:** `robot_pi/video_capture.py`

**Problem:** If video socket blocked, capture thread could stall, potentially
affecting control thread scheduling.

**Fix:**
- Frame dropping policy: only send latest frame
- `SEND_TIMEOUT_S = 0.5` - Drop frame if socket blocked
- Statistics tracking: `frames_sent`, `frames_dropped`, `drop_rate`
- Video cannot block control channel

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
- `DevicePolicy=closed` (robot only) - Whitelist device access
- `SystemCallFilter` - Restrict system calls

**Robot Pi exceptions for hardware access:**
- `SupplementaryGroups=i2c gpio video`
- `DeviceAllow=/dev/i2c-*, /dev/gpiomem, /dev/video*`

---

## P2 Patches (Medium Priority - Post-MVP)

### P2.1: Heartbeat RTT Measurement
**Files:** `base_pi/halow_bridge.py`, `common/constants.py`

Implemented ping/pong for round-trip time measurement:
- Base Pi sends `MSG_PING` with timestamp every `HEARTBEAT_INTERVAL_S`
- Robot Pi responds with `MSG_PONG`
- RTT tracked in `last_rtt_ms` for latency monitoring

### P2.2: Health Endpoint
**Files:** `base_pi/halow_bridge.py`

`get_health()` returns comprehensive status:
- Connection states (backend, control, telemetry, video)
- E-STOP state from Robot Pi
- Telemetry age
- PSK validity
- RTT measurement

### P2.3: Statistics Tracking
**Files:** All receiver/forwarder modules

Each module tracks operational statistics:
- `commands_sent`, `commands_failed`
- `frames_sent`, `frames_dropped`
- `messages_received`, `auth_failures`, `decode_errors`
- `buffer_overflows`

---

## Deployment Checklist

### Pre-Deployment
- [ ] Generate 256-bit PSK: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set `SERPENT_PSK_HEX` on both Base Pi and Robot Pi
- [ ] Verify PSK matches on both sides
- [ ] Create log directory: `sudo mkdir -p /var/log/serpent && sudo chown pi:pi /var/log/serpent`

### Service Installation
```bash
# Robot Pi
sudo cp serpent-robot-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-robot-bridge
sudo systemctl start serpent-robot-bridge

# Base Pi
sudo cp serpent-base-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable serpent-base-bridge
sudo systemctl start serpent-base-bridge
```

### PSK Configuration (secure method)
```bash
# Create drop-in override
sudo mkdir -p /etc/systemd/system/serpent-robot-bridge.service.d
sudo nano /etc/systemd/system/serpent-robot-bridge.service.d/psk.conf
# Add:
# [Service]
# Environment="SERPENT_PSK_HEX=<your-64-char-hex-key>"

sudo systemctl daemon-reload
sudo systemctl restart serpent-robot-bridge
```

### Verification Tests
1. **E-STOP Latched on Boot:**
   - Start robot service, verify E-STOP engaged before any control received

2. **Watchdog Timeout:**
   - Start robot without base, verify E-STOP remains after 30s grace + 5s timeout

3. **Authentication:**
   - Attempt control with wrong PSK, verify rejection and E-STOP

4. **Clear Validation:**
   - Attempt E-STOP clear without confirmation string, verify rejection
   - Attempt clear with stale control connection, verify rejection

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
     │                              - confirm="CLEAR_ESTOP"     │
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

| File | Change Type | Priority |
|------|-------------|----------|
| `common/__init__.py` | NEW | P0 |
| `common/constants.py` | NEW | P0 |
| `common/framing.py` | NEW | P0 |
| `robot_pi/actuator_controller.py` | MODIFIED | P0 |
| `robot_pi/halow_bridge.py` | MODIFIED | P0 |
| `base_pi/halow_bridge.py` | MODIFIED | P0 |
| `base_pi/control_forwarder.py` | MODIFIED | P0 |
| `base_pi/telemetry_receiver.py` | MODIFIED | P1 |
| `base_pi/video_receiver.py` | MODIFIED | P1 |
| `robot_pi/video_capture.py` | MODIFIED | P1 |
| `robot_pi/serpent-robot-bridge.service` | MODIFIED | P1 |
| `base_pi/serpent-base-bridge.service` | MODIFIED | P1 |

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

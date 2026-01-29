# Pi HaLow Bridge - Adversarial Audit Patch Plan

**Audit Date:** 2026-01-29
**Auditor Role:** Adversarial maintainer, safety reviewer, build engineer

---

## P0: Safety-Critical Issues

### P0.1: Configurable Safety Timeouts
**File:** `robot_pi/config.py:52`
**Issue:** `WATCHDOG_TIMEOUT` is env-configurable, allowing operators to accidentally set unsafe values (e.g., 60 seconds). Safety-critical constants should be immutable.
**Reproduction:** `WATCHDOG_TIMEOUT=60 python halow_bridge.py` - robot continues operating for 60s without control.
**Fix:** Remove env override for safety constants. Import from `common/constants.py` as single source of truth.
**Status:** WILL FIX

### P0.2: Missing RECONNECT_DELAY in Robot Config
**File:** `robot_pi/config.py`
**Issue:** `robot_pi/halow_bridge.py:194` references `config.RECONNECT_DELAY` but it doesn't exist in robot_pi/config.py.
**Reproduction:** Code will crash with AttributeError on first reconnect attempt.
**Fix:** Add `RECONNECT_DELAY` to robot_pi/config.py or import from constants.
**Status:** WILL FIX

### P0.3: Sequence Counter Not Thread-Safe
**File:** `common/framing.py:118-119`
**Issue:** `self.send_seq += 1` is not atomic. If create_frame called from multiple threads, sequence collision possible.
**Reproduction:** Call create_frame() from two threads simultaneously in tight loop.
**Fix:** Add lock to SecureFramer for send_seq increment, OR document single-thread requirement.
**Status:** WILL FIX (add lock)

### P0.4: Video Frame Rate Logic Bug
**File:** `robot_pi/video_capture.py:185-187`
**Issue:** After rate-limit sleep, `continue` skips to next iteration instead of capturing frame. Causes inefficiency and timing jitter.
**Reproduction:** Run video capture, observe unnecessary loop iterations.
**Fix:** Remove continue, let flow proceed to capture.
**Status:** WILL FIX

### P0.5: Heartbeat/Pong Not Implemented
**File:** `robot_pi/halow_bridge.py:372-378`, `base_pi/halow_bridge.py`
**Issue:** `_handle_ping` calculates timestamps but doesn't send pong. Base never gets RTT.
**Reproduction:** Check `last_rtt_ms` on base - always 0.
**Fix:** Robot sends pong in telemetry response, Base extracts RTT.
**Status:** WILL FIX (via telemetry, simpler than bidirectional pong)

---

## P1: Robustness Issues

### P1.1: V4L2 Linux-Only
**File:** `robot_pi/video_capture.py:66`
**Issue:** `cv2.CAP_V4L2` is Linux-specific. Won't work on Windows for simulation.
**Reproduction:** Run on Windows - VideoCapture fails.
**Fix:** Use V4L2 only on Linux, default backend on Windows. Add SIM_MODE with synthetic frames.
**Status:** WILL FIX

### P1.2: No SIM_MODE Support
**Files:** Multiple
**Issue:** Cannot run system without hardware (Motoron, GPIO, I2C sensors, cameras).
**Reproduction:** Run on Windows laptop - crashes.
**Fix:** Add SIM_MODE env var. Create mock implementations that record commanded values.
**Status:** WILL FIX

### P1.3: Socket Timeout During Graceful Shutdown
**File:** `robot_pi/halow_bridge.py`
**Issue:** Socket operations may block during shutdown, causing delayed cleanup.
**Reproduction:** Stop service while waiting for connection.
**Fix:** Ensure sockets have timeouts and shutdown flag is checked.
**Status:** WILL FIX (already partially handled)

### P1.4: Unicode Decode Without Boundary
**File:** `robot_pi/halow_bridge.py:283`
**Issue:** `payload.decode('utf-8')` could raise UnicodeDecodeError on malformed input. Currently caught by outer handler but should be explicit.
**Reproduction:** Send binary garbage as payload.
**Fix:** Already handled by except block at line 285. OK as-is.
**Status:** OK

### P1.5: Missing Video Health Check
**File:** `robot_pi/video_capture.py`
**Issue:** If camera disconnects mid-stream, no automatic recovery or notification.
**Reproduction:** Unplug USB camera during operation.
**Fix:** Add camera health check, attempt reinit on failure.
**Status:** WILL FIX (add recovery attempt)

---

## P2: Maintainability Issues

### P2.1: No Test Suite
**Issue:** Zero test coverage.
**Fix:** Add tests/ directory with framing, E-STOP, watchdog, buffer tests.
**Status:** WILL FIX

### P2.2: No Deployment Scripts
**Issue:** No one-click install/run for Windows or Pi.
**Fix:** Add scripts/ directory with run_sim.py, test_all.py, pi_install.sh, etc.
**Status:** WILL FIX

### P2.3: Incomplete README
**Issue:** README exists but doesn't cover full deployment workflow.
**Fix:** Rewrite comprehensive README.
**Status:** WILL FIX

### P2.4: Duplicate Config Logic
**Issue:** Config parsing similar between base_pi and robot_pi.
**Fix:** Low priority - keep separate for deployment simplicity.
**Status:** DEFER

---

## Implementation Order

1. P0.2 - Add missing RECONNECT_DELAY (blocking bug)
2. P0.1 - Lock down safety constants
3. P0.3 - Thread-safe sequence counter
4. P0.4 - Fix video rate limit logic
5. P0.5 - RTT via telemetry
6. P1.1 + P1.2 - Add SIM_MODE (enables testing)
7. P1.5 - Video health check
8. P2.1 - Test suite
9. P2.2 - Deployment scripts
10. P2.3 - README

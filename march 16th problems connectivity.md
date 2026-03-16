# March 16th — Connectivity & Motor Coasting Problems

**Date:** 2026-03-16
**Analyst:** Claude Code deep-dive
**Status:** Diagnosed, not yet fixed

---

## Overview

Two separate but related problems were identified:

1. **The Gap** — Control signal drops for 2-3 seconds during brief network interruptions
2. **The Coast** — During that gap, motors (especially chainsaw and hoist) continue running at their last commanded speed

These are caused by specific timeout values and gaps in the motor-stop coverage, not by a hardware or radio problem.

---

## Problem 1 — The 2-3 Second Signal Gap

### What happens

When the HaLow radio briefly drops (handoff, fade, spike), the TCP connection silently dies. The system doesn't notice immediately because of sequential timeouts:

```
Network drops (100-200ms)
  → Robot Pi socket read timeout fires at 1.0s       ← largest delay
  → Robot Pi closes client, goes back to accept()
  → Base Pi detects send failure, sleeps 0.5s         ← second delay
  → Base Pi retries connection
  → TCP 3-way handshake ~200ms
  → First valid authenticated command arrives
─────────────────────────────────────────────
TOTAL: ~1.7s best case, up to 3.0s with backoff jitter
```

### Root cause files and lines

| Cause | File | Value |
|---|---|---|
| Socket read timeout | `robot_pi/control/control_server.py` — `framer.read_frame_from_socket(timeout=1.0)` | 1.0s |
| Reconnect sleep | `base_pi/control_forwarder.py` — `time.sleep(self.reconnect_delay)` | 0.5s |
| TCP handshake | OS-level, not configurable | ~200ms |

### Why it feels longer than it is

The operator sends a command, gets no response, sends another, still nothing — by the time reconnection happens ~2s later, there is a queue of stale commands that may fire in the wrong order. The subjective experience is longer than the actual gap.

---

## Problem 2 — Motors Coast During the Gap

### What happens

During those 2-3 seconds, the robot is not receiving commands. The question is: what do the motors do?

| Motor | Function | Behaviour during loss | Why |
|---|---|---|---|
| 0, 1 | Claws | Stops after ~0.5s | Motor timeout loop covers these |
| 2, 3 | Chainsaw feed (up/down) | **Holds indefinitely** | Excluded from motor timeout loop |
| 4, 5 | Chainsaw on/off | **Ramp thread keeps sending keepalives every 100ms** | `ChainsawRamp._loop()` has no control-loss awareness |
| 6 | Hoist / ascender | **Runs forever, no hardware fallback** | Motoron board 3 has `disable_command_timeout()` explicitly called |
| 7 | Traverse | Holds ~1.5s then stops | Motoron hardware timeout fires (not disabled on this board) |

### The chainsaw ramp problem (motors 4-5)

`ChainsawRamp._loop()` in `command_executor.py` actively sends keepalive commands to the Motoron every 100ms to prevent the hardware timeout from triggering. This means during control loss, the ramp loop keeps the chainsaw running at its last target speed. It has no awareness that control has been lost.

### The hoist problem (motor 6)

`actuator_controller.py:277` explicitly calls `mc.disable_command_timeout()` on Motoron board 3. This was intentional (to prevent the ascender from stopping mid-climb during a slow command cycle), but with the software watchdog also disabled, there is now **no safety net at all** for motor 6 during control loss.

### Root cause files and lines

| Cause | File | Detail |
|---|---|---|
| Motor timeout covers claws only | `command_executor.py` — `_stop_all_motors()` | Only loops `range(2)` — motors 0-1 |
| Ramp keepalive unaware of loss | `command_executor.py` — `ChainsawRamp._loop()` | No `_last_input_time` check |
| Hoist hardware timeout disabled | `actuator_controller.py:277` | `mc.disable_command_timeout()` on board 3 |

---

## Problem 3 — All Watchdogs Are Disabled

Both safety watchdogs were intentionally disabled at some point. With them off, there is no automatic response to control loss at any level.

| Watchdog | File | Original behaviour | Current state |
|---|---|---|---|
| Robot Pi watchdog | `robot_pi/core/watchdog_monitor.py` | Auto E-STOP after 5s control loss | **Completely disabled** |
| Base Pi watchdog | `base_pi/core/watchdog_monitor.py` | Send E-STOP engage on telemetry timeout | **Completely disabled** |

These are not being re-enabled as part of this fix (the E-STOP latch is not wanted). The motor timeout loop is the replacement mechanism.

---

## Problem 4 — Overlapping / Conflicting Logic

These are not causing the coasting problem directly but create maintenance risk and unpredictable interactions.

### Double emergency deduplication

An E-STOP command from the operator passes through two independent dedup filters:
1. `BackendClient` — deduplicates emergency events from the backend
2. `CommandExecutor._handle_emergency_stop()` — 0.5s dedup window

A rapidly-toggled E-STOP can be silently swallowed at either layer. This is a separate bug to fix independently.

### Two control-time trackers

`ControlServer.last_control_time` and `CommandExecutor._last_input_time` both track "when did we last get a valid command." They are populated differently and used in different places. If the watchdog were ever re-enabled these could diverge and produce inconsistent behaviour.

### Motor stop scope split

`ActuatorController.engage_estop()` stops all motors (0-7) and latches.
`CommandExecutor._stop_all_motors()` stops only motors 0-1 and does not latch.
Both are named as "stop all" but cover completely different scopes. The split is not obvious from the names.

---

## The Design Goal

The fix must produce **soft coast** behaviour, not E-STOP behaviour:

- When control is lost, motors ramp to zero within ~0.5s
- No E-STOP latch — operator does not need to clear anything
- When control reconnects, the robot resumes normal operation immediately
- The chainsaw ramp must decelerate gracefully (not hard-cut to zero)

---

## Phase 1 — Four Targeted Fixes (Low Risk)

These four changes solve both the gap and the coasting problem with minimal surface area.

### Fix 1 — Reduce socket read timeout

**File:** `robot_pi/control/control_server.py`
**Change:** `framer.read_frame_from_socket(timeout=1.0)` → `timeout=0.25`
**Effect:** Robot Pi detects connection loss in 250ms instead of 1000ms
**Risk:** Low — if the radio drops packets for 250ms straight, control is genuinely lost

### Fix 2 — Reduce reconnect sleep

**File:** `base_pi/control_forwarder.py`
**Change:** `time.sleep(self.reconnect_delay)` where `reconnect_delay=0.5` → `0.1`
(Or set the default value in config/constructor)
**Effect:** Base Pi retries the connection 400ms sooner
**Risk:** Negligible — more aggressive retry on localhost has no downside

### Fix 3 — Extend motor timeout to all motors

**File:** `robot_pi/core/command_executor.py`
**Change:** `_stop_all_motors()` currently loops `range(2)`. Extend to cover all motors:
- Motors 2, 3, 7: direct `set_motor_speed(id, 0)` calls
- Motors 4, 5: call `ramp.set_target(0)` instead of direct zero command — lets the ramp decelerate naturally
- Motor 6: direct `set_motor_speed(6, 0)` — becomes the only safety net for the hoist

**Effect:** All motors soft-stop within 0.5s of control loss (the existing timeout threshold)
**Risk:** Low — the 0.5s threshold already works correctly for claws, extending scope doesn't change timing

### Fix 4 — Acknowledge hoist timeout disabled in config

**File:** `robot_pi/actuator_controller.py`
**Change:** No code change needed if Fix 3 is in place. Add a comment at line 277 explicitly documenting that the software motor timeout loop is the fallback:

```python
# Command timeout DISABLED for ascender board — software motor timeout
# loop in CommandExecutor is the safety fallback (stops motor 6 within 0.5s)
mc.disable_command_timeout()
```

**Effect:** Future engineers understand the dependency between these two systems
**Risk:** None (comment only)

### Phase 1 Expected Outcome

| Metric | Before | After |
|---|---|---|
| Gap duration | 2-3s | ~0.5-0.7s |
| Motor stop after loss | Never (hoist), ~1.5s (traverse), ramp keeps running (chainsaw) | All motors ≤0.5s |
| Resume after reconnect | Automatic | Automatic (unchanged) |
| E-STOP latch required | No | No (unchanged) |

**Test plan for Phase 1:**
1. Run robot, set chainsaw and hoist to active speeds
2. Manually kill the TCP connection on Base Pi
3. Confirm all motors stop within 0.5s
4. Restore TCP connection
5. Confirm robot accepts commands normally, no latch to clear

---

## Phase 2 — Heartbeat Miss Detection (Medium Complexity)

Phase 1 gets the gap from 2-3s down to ~0.5-0.7s. Phase 2 gets it below 200ms.

### What's already there

The framing layer already defines `MSG_PING`/`MSG_PONG`. Base Pi already sends pings at `HEARTBEAT_INTERVAL_S = 1.0s`. Robot Pi receives pongs in telemetry. The infrastructure is complete on the Base Pi side. The missing piece is Robot Pi using missed pings to infer control loss.

### The fix

Add a ping-miss check to the Robot Pi control loop: if no valid frame (including pings) has been received in `2 × HEARTBEAT_INTERVAL_S` (2.0s with current config, or less if heartbeat interval is reduced), treat it as control loss and call `_stop_all_motors_soft()`.

To make this useful, `HEARTBEAT_INTERVAL_S` should be reduced from 1.0s to 0.2s. Then the miss window becomes 0.4s, bringing detection well below Phase 1 levels.

**Files to change:**
- `common/constants.py` — `HEARTBEAT_INTERVAL_S = 1.0` → `0.2`
- `robot_pi/core/bridge_coordinator.py` — add heartbeat-miss check in `_control_receiver_loop`

### Phase 2 Expected Outcome

| Metric | After Phase 1 | After Phase 2 |
|---|---|---|
| Gap duration | ~0.5-0.7s | ~200ms |
| Detection mechanism | Socket read timeout | Heartbeat miss (more reliable) |
| Survives partial connectivity | No | Yes — detects when TCP stays open but packets aren't flowing |

**Note:** Phase 2 is genuinely useful but Phase 1 alone may be sufficient in practice. Do Phase 1 first and evaluate whether the remaining 0.5-0.7s gap is still noticeable before investing in Phase 2.

---

## Separate Issue — E-STOP Test Failures (8 Tests)

Not related to connectivity. The `tests/test_estop.py` expects E-STOP to be latched on construction (`_estop_engaged = True` with reason `"boot_default"`). The current `actuator_controller.py` initialises `_estop_engaged = False` with the comment "Boot E-STOP disabled." The tests and the implementation disagree. Fix separately when the E-STOP design decision is made.

---

## Separate Issue — Windows PermissionError in run_sim.py

`run_sim.py` does not set `STORAGE_ENABLED=false` in its `SIM_CONFIG`. The default `STORAGE_BASE_PATH` is `/media/serpentbase/SSK_SSD/serpent_recordings` (Linux SSD mount path). On Windows, `os.makedirs()` tries to create this at the drive root and raises `PermissionError`. Fix by adding `'STORAGE_ENABLED': 'false'` to `SIM_CONFIG` in `run_sim.py`. Fix separately from the connectivity work.

---

## File Reference

All files relevant to the Phase 1 and Phase 2 fixes:

```
robot_pi/control/control_server.py          — Fix 1 (read timeout)
base_pi/control_forwarder.py                — Fix 2 (reconnect sleep)
robot_pi/core/command_executor.py           — Fix 3 (motor timeout scope)
robot_pi/actuator_controller.py             — Fix 4 (comment on board 3)
common/constants.py                         — Phase 2 (HEARTBEAT_INTERVAL_S)
robot_pi/core/bridge_coordinator.py         — Phase 2 (heartbeat miss detection)
```

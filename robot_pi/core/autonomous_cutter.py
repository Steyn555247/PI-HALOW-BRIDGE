"""
Autonomous Chainsaw Cutter

State machine that autonomously feeds a chainsaw into a branch,
backs off when current is too high, and stops when it detects
the branch is cut (current drops suddenly after peaking).

Chainsaw ID mapping:
  CS1: on/off = Motor 5 (-speed), feed = Motor 2 (-down/+retract), current = sensor 1 (mux ch.7)
  CS2: on/off = Motor 4 (-speed), feed = Motor 3 (+down/-retract), current = sensor 2 (mux ch.6)
"""

import threading
import time
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class CuttingState(Enum):
    ADVANCING   = "advancing"
    BACKING_OFF = "backing_off"
    COMPLETE    = "complete"


class AutonomousCutter:
    """
    Autonomous chainsaw cutting controller (one chainsaw at a time).

    Manages on/off and feed motors to cut through a branch:
    - ADVANCING:   feeds chainsaw down into branch at low speed
    - BACKING_OFF: reverses quickly when current spikes (wood resistance)
    - COMPLETE:    breakthrough detected — stops all motors and exits

    Breakthrough is only triggered AFTER current has peaked at least once
    (prevents false trigger before the blade contacts wood).

    Thread safety: start()/stop()/is_running() may be called from any thread.
    The control loop runs in its own daemon thread.
    """

    def __init__(
        self,
        chainsaw_id,
        actuator_controller,
        sensor_reader,
        high_current,
        safe_current,
        idle_current,
        advance_speed,
        backoff_speed,
        breakthrough_confirm_s,
        loop_interval_s,
        onoff_speed=720,
        set_blade_speed=None,
        on_complete=None,
    ):
        """
        Args:
            chainsaw_id:             1 or 2
            actuator_controller:     ActuatorController instance
            sensor_reader:           SensorReader instance (reads latest_current_data)
            high_current:            Back off above this current (A)
            safe_current:            Re-advance below this current (A)
            idle_current:            Breakthrough threshold (A)
            advance_speed:           Feed motor advance speed (0–800)
            backoff_speed:           Feed motor backoff speed (0–800)
            breakthrough_confirm_s:  Time current must stay below idle to confirm cut (s)
            loop_interval_s:         Control loop sleep interval (s)
            onoff_speed:             On/off motor speed (0–800), default 720 (90%)
            set_blade_speed:         Optional callable(speed: int) to set the on/off motor
                                     speed (e.g. a ChainsawRamp.set_target). When provided,
                                     keepalive is handled externally by that callable.
                                     Falls back to direct set_motor_speed if None.
            on_complete:             Optional callback(chainsaw_id) on breakthrough
        """
        self.chainsaw_id          = chainsaw_id
        self.actuator_controller  = actuator_controller
        self.sensor_reader        = sensor_reader
        self.high_current         = high_current
        self.safe_current         = safe_current
        self.idle_current         = idle_current
        self.advance_speed        = advance_speed
        self.backoff_speed        = backoff_speed
        self.breakthrough_confirm_s = breakthrough_confirm_s
        self.loop_interval_s      = loop_interval_s
        self.onoff_speed          = onoff_speed
        self.set_blade_speed      = set_blade_speed
        self.on_complete          = on_complete

        # Motor / sensor assignment
        if chainsaw_id == 1:
            self.onoff_motor = 5      # Motor 5: use -speed
            self.feed_motor  = 2      # Motor 2: -speed=down, +speed=retract
            self.sensor_key  = 'cs1'
        else:
            self.onoff_motor = 4      # Motor 4: use -speed
            self.feed_motor  = 3      # Motor 3: +speed=down, -speed=retract
            self.sensor_key  = 'cs2'

        self._running = False
        self._thread: threading.Thread = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_onoff(self, speed: int):
        """
        Set the on/off motor speed, routing through the soft-start ramp
        when available, or directly through the actuator otherwise.
        """
        if self.set_blade_speed is not None:
            self.set_blade_speed(speed)
        else:
            self.actuator_controller.set_motor_speed(self.onoff_motor, speed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Turn on the chainsaw blade (via soft-start ramp) and launch the autonomous control loop."""
        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: starting "
            f"(high={self.high_current}A safe={self.safe_current}A "
            f"idle={self.idle_current}A advance={self.advance_speed} "
            f"backoff={self.backoff_speed})"
        )
        # Turn on chainsaw on/off motor via soft-start ramp (or direct if no ramp provided)
        self._set_onoff(-self.onoff_speed)

        self._running = True
        self._thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name=f"autocut-cs{self.chainsaw_id}",
        )
        self._thread.start()

    def stop(self):
        """Signal the control loop to exit and immediately stop all motors."""
        logger.info(f"AutonomousCutter CS{self.chainsaw_id}: stop requested")
        self._running = False
        # Stop motors immediately — don't wait for the thread
        self._stop_motors()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        """Return True while the control loop is active."""
        return self._running

    def _get_current(self) -> float:
        """
        Read current (A) from the external INA238 sensor via SensorReader.
        CS1 uses sensor 1 (mux ch.7); CS2 uses sensor 2 (mux ch.6).
        Returns 0.0 on error.
        """
        try:
            if self.chainsaw_id == 1:
                return self.sensor_reader.get_motor1_current()
            else:
                return self.sensor_reader.get_motor2_current()
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error reading current: {e}"
            )
            return 0.0

    def _set_feed(self, down: bool, speed: int):
        """
        Drive the feed motor.

        CS1 Motor 2: -speed = forward/down (advance),  +speed = retract
        CS2 Motor 3: +speed = down (advance),          -speed = retract
        """
        if self.chainsaw_id == 1:
            motor_speed = -speed if down else speed
        else:
            motor_speed = speed if down else -speed
        self.actuator_controller.set_motor_speed(self.feed_motor, motor_speed)

    def _stop_motors(self):
        """Stop feed motor immediately; ramp the on/off motor down via soft-stop."""
        try:
            self.actuator_controller.set_motor_speed(self.feed_motor, 0)
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error stopping feed motor: {e}"
            )
        try:
            self._set_onoff(0)
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error stopping on/off motor: {e}"
            )

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------

    def _control_loop(self):
        """
        Autonomous cutting state machine — runs in its own daemon thread.

        States
        ------
        ADVANCING
          Feed motor moves down at advance_speed.
          • current > high_current  → BACKING_OFF  (set has_peaked=True)
          • has_peaked and current < idle_current for ≥ breakthrough_confirm_s → COMPLETE

        BACKING_OFF
          Feed motor reverses at backoff_speed.
          • current < safe_current  → ADVANCING

        COMPLETE
          Clears _running flag; loop exits; motors are stopped.
          on_complete callback is fired if provided.
        """
        state             = CuttingState.ADVANCING
        has_peaked        = False   # True once current has exceeded high_current
        low_since         = None    # When current first dropped below idle_current
        last_backoff_time = None    # When we last left BACKING_OFF → used for grace period
        POST_BACKOFF_GRACE_S = 2.0  # Don't allow breakthrough until this many seconds after last backoff
        completed_naturally = False

        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: control loop started"
        )

        # Wait for the blade to reach full speed before engaging the feed
        # motor or monitoring current — avoids a false BACKING_OFF from the
        # startup current spike.
        STARTUP_DELAY_S = 1.5
        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: "
            f"startup delay {STARTUP_DELAY_S}s (blade spin-up)"
        )
        # Keepalive is handled by ChainsawRamp (10 Hz). Just wait here.
        deadline = time.time() + STARTUP_DELAY_S
        while self._running and time.time() < deadline:
            time.sleep(self.loop_interval_s)

        if not self._running:
            self._stop_motors()
            logger.info(
                f"AutonomousCutter CS{self.chainsaw_id}: stopped during startup delay"
            )
            return

        while self._running:
            current = self._get_current()

            if state == CuttingState.ADVANCING:
                self._set_feed(down=True, speed=self.advance_speed)

                if current > self.high_current:
                    has_peaked = True
                    low_since  = None
                    state      = CuttingState.BACKING_OFF
                    logger.info(
                        f"AutonomousCutter CS{self.chainsaw_id}: {current:.2f}A > "
                        f"{self.high_current}A → BACKING_OFF"
                    )

                elif has_peaked and current < self.idle_current:
                    # Only allow breakthrough detection after the post-backoff grace period.
                    # This prevents false COMPLETE when the feed re-advances after a backoff
                    # and is momentarily in air before contacting the wood again.
                    grace_expired = (
                        last_backoff_time is None or
                        time.time() - last_backoff_time >= POST_BACKOFF_GRACE_S
                    )
                    if not grace_expired:
                        # Still in grace period — don't start breakthrough timer
                        low_since = None
                    elif low_since is None:
                        low_since = time.time()
                        logger.debug(
                            f"AutonomousCutter CS{self.chainsaw_id}: potential "
                            f"breakthrough ({current:.2f}A), confirming…"
                        )
                    elif time.time() - low_since >= self.breakthrough_confirm_s:
                        logger.info(
                            f"AutonomousCutter CS{self.chainsaw_id}: BREAKTHROUGH "
                            f"confirmed ({current:.2f}A for "
                            f"≥{self.breakthrough_confirm_s}s)"
                        )
                        state = CuttingState.COMPLETE

                else:
                    # Current rose back above idle — reset confirmation timer
                    if low_since is not None:
                        logger.debug(
                            f"AutonomousCutter CS{self.chainsaw_id}: breakthrough "
                            f"timer reset ({current:.2f}A)"
                        )
                    low_since = None

            elif state == CuttingState.BACKING_OFF:
                self._set_feed(down=False, speed=self.backoff_speed)

                if current < self.safe_current:
                    state = CuttingState.ADVANCING
                    last_backoff_time = time.time()  # Start grace period for breakthrough detection
                    logger.info(
                        f"AutonomousCutter CS{self.chainsaw_id}: {current:.2f}A < "
                        f"{self.safe_current}A → ADVANCING (grace period {POST_BACKOFF_GRACE_S}s)"
                    )

            elif state == CuttingState.COMPLETE:
                # Retract feed slowly — blade (on/off motor) keeps running.
                # User can stop the blade manually after the cut is done.
                self._set_feed(down=False, speed=self.advance_speed)
                logger.info(
                    f"AutonomousCutter CS{self.chainsaw_id}: "
                    f"COMPLETE — retracting feed at speed {self.advance_speed}, blade stays on"
                )
                completed_naturally = True
                self._running = False   # Causes loop to exit on next iteration check

            time.sleep(self.loop_interval_s)

        # ---- loop has exited ----
        if completed_naturally:
            # Breakthrough detected — stop only the feed motor.
            # The blade (on/off motor) keeps running; user stops it manually.
            try:
                self.actuator_controller.set_motor_speed(self.feed_motor, 0)
            except Exception as e:
                logger.error(
                    f"AutonomousCutter CS{self.chainsaw_id}: error stopping feed motor: {e}"
                )
        else:
            # Manually stopped — stop everything immediately.
            self._stop_motors()

        if completed_naturally and self.on_complete:
            try:
                self.on_complete(self.chainsaw_id)
            except Exception as e:
                logger.error(
                    f"AutonomousCutter CS{self.chainsaw_id}: error in "
                    f"on_complete callback: {e}"
                )

        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: control loop ended "
            f"(state={state.value}, natural={completed_naturally})"
        )

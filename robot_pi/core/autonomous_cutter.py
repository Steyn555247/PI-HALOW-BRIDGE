"""
Autonomous Chainsaw Cutter

State machine that autonomously feeds a chainsaw into a branch,
backs off when current is too high, and stops when it detects
the branch is cut (current drops suddenly after peaking).

Chainsaw ID mapping:
  CS1: on/off = Motor 4 (-speed, direction swapped), feed = Motor 2 (+up, -down)
  CS2: on/off = Motor 5 (+speed),                   feed = Motor 3 (-up, +down swapped)
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
        self.on_complete          = on_complete

        # Motor / sensor assignment
        if chainsaw_id == 1:
            self.onoff_motor = 4      # Motor 4: direction swapped → use -speed
            self.feed_motor  = 2      # Motor 2: +speed=up, -speed=down
            self.sensor_key  = 'cs1'
        else:
            self.onoff_motor = 5      # Motor 5: normal → use +speed
            self.feed_motor  = 3      # Motor 3: -speed=up, +speed=down (swapped)
            self.sensor_key  = 'cs2'

        self._running = False
        self._thread: threading.Thread = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Turn on the chainsaw blade and launch the autonomous control loop."""
        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: starting "
            f"(high={self.high_current}A safe={self.safe_current}A "
            f"idle={self.idle_current}A advance={self.advance_speed} "
            f"backoff={self.backoff_speed})"
        )
        # Turn on chainsaw on/off motor
        if self.chainsaw_id == 1:
            self.actuator_controller.set_motor_speed(self.onoff_motor, -self.onoff_speed)
        else:
            self.actuator_controller.set_motor_speed(self.onoff_motor, self.onoff_speed)

        self._running = True
        self._thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name=f"autocut-cs{self.chainsaw_id}",
        )
        self._thread.start()

    def stop(self):
        """Signal the control loop to exit, wait for it, then stop all motors."""
        logger.info(f"AutonomousCutter CS{self.chainsaw_id}: stop requested")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        # Ensure motors are off regardless of how the thread exited
        self._stop_motors()

    def is_running(self) -> bool:
        """Return True while the control loop is active."""
        return self._running

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_current(self) -> float:
        """
        Read current (A) from the SensorReader's latest_current_data.
        Returns 0.0 if the sensor data is not yet available.
        """
        try:
            with self.sensor_reader.data_lock:
                sensor_data = self.sensor_reader.latest_current_data.get(
                    self.sensor_key, {}
                )
            return float(sensor_data.get('current', 0.0))
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error reading current: {e}"
            )
            return 0.0

    def _set_feed(self, down: bool, speed: int):
        """
        Drive the feed motor.

        CS1 Motor 2: +speed = up (retract),  -speed = down (advance)
        CS2 Motor 3: -speed = up (retract),  +speed = down (advance)  [direction swapped]
        """
        if self.chainsaw_id == 1:
            motor_speed = -speed if down else speed
        else:
            motor_speed = speed if down else -speed
        self.actuator_controller.set_motor_speed(self.feed_motor, motor_speed)

    def _stop_motors(self):
        """Stop both the feed motor and the on/off motor."""
        try:
            self.actuator_controller.set_motor_speed(self.feed_motor, 0)
            self.actuator_controller.set_motor_speed(self.onoff_motor, 0)
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error stopping motors: {e}"
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
        state           = CuttingState.ADVANCING
        has_peaked      = False   # True once current has exceeded high_current
        low_since       = None    # When current first dropped below idle_current
        completed_naturally = False

        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: control loop started"
        )

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
                    # Possible breakthrough — start / extend confirmation timer
                    if low_since is None:
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
                    logger.info(
                        f"AutonomousCutter CS{self.chainsaw_id}: {current:.2f}A < "
                        f"{self.safe_current}A → ADVANCING"
                    )

            elif state == CuttingState.COMPLETE:
                completed_naturally = True
                self._running = False   # Causes loop to exit on next iteration check

            time.sleep(self.loop_interval_s)

        # ---- loop has exited ----
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

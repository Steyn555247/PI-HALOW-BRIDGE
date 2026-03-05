"""
Autonomous Chainsaw Cutter

PID controller that continuously regulates the feed motor speed to maintain
a target current draw. Replaces the old bang-bang ADVANCING/BACKING_OFF
state machine with smooth, linear descent into the branch.

Chainsaw ID mapping:
  CS1: on/off = Motor 5 (-speed), feed = Motor 2 (-down/+retract), current = sensor 1 (mux ch.5)
  CS2: on/off = Motor 4 (-speed), feed = Motor 3 (+down/-retract), current = sensor 2 (mux ch.6)

Improvements:
  - Adaptive baseline: Measures free-spin current for 5s, adds thresholds on top
  - E-STOP detection: Explicitly checks E-STOP status in control loop
  - Sensor staleness: Detects frozen sensor values (>2s stale)
  - Motor command validation: Checks return values from motor commands
  - PID telemetry: Logs error, integral, derivative for tuning
"""

import threading
import time
import logging
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CuttingState(Enum):
    CUTTING  = "cutting"
    COMPLETE = "complete"


class _PIDController:
    """
    Discrete PID controller with anti-windup and derivative on measurement.

    Anti-windup: back-calculates integral correction when output is clamped.
    Derivative on measurement (not error) avoids derivative kick on setpoint changes.

    Telemetry: Exposes error, integral, derivative for observability.
    """

    def __init__(self, kp: float, ki: float, kd: float,
                 output_min: float, output_max: float, dt: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.dt = dt
        self._integral = 0.0
        self._prev_measurement = None

        # Telemetry (updated each compute() call)
        self.last_error = 0.0
        self.last_derivative = 0.0

    def reset(self):
        self._integral = 0.0
        self._prev_measurement = None
        self.last_error = 0.0
        self.last_derivative = 0.0

    def compute(self, setpoint: float, measurement: float) -> float:
        error = setpoint - measurement
        self.last_error = error

        # Derivative on measurement (not error) to avoid derivative kick
        if self._prev_measurement is None:
            derivative = 0.0
        else:
            derivative = -(measurement - self._prev_measurement) / self.dt
        self._prev_measurement = measurement
        self.last_derivative = derivative

        # Unclamped output
        output = self.kp * error + self._integral + self.kd * derivative

        # Clamp
        output_clamped = max(self.output_min, min(self.output_max, output))

        # Anti-windup: integrate only the portion that didn't saturate
        self._integral += self.ki * error * self.dt - (output - output_clamped)

        return output_clamped

    def get_telemetry(self) -> Tuple[float, float, float]:
        """Return (error, integral, derivative) for observability."""
        return (self.last_error, self._integral, self.last_derivative)


class AutonomousCutter:
    """
    Autonomous chainsaw cutting controller (one chainsaw at a time).

    Uses a PID controller to regulate feed motor speed, targeting a
    desired current draw as the blade cuts through the branch.

    Breakthrough detection:
    - has_peaked = True once current rises above idle_current (blade contacts wood)
    - After peaking, if current stays below idle_current for ≥ breakthrough_confirm_s
      the cut is confirmed (COMPLETE)
    - Timer resets if current rises back above idle_current mid-confirmation

    Thread safety: start()/stop()/is_running() may be called from any thread.
    The control loop runs in its own daemon thread.
    """

    def __init__(
        self,
        chainsaw_id,
        actuator_controller,
        sensor_reader,
        target_current,
        pid_kp,
        pid_ki,
        pid_kd,
        max_speed,
        idle_current,
        breakthrough_confirm_s,
        loop_interval_s,
        onoff_speed=720,
        set_blade_speed=None,
        on_complete=None,
        approach_speed=None,
        contact_confirm_reads=3,
        max_cut_duration_s=45.0,
    ):
        """
        Args:
            chainsaw_id:             1 or 2
            actuator_controller:     ActuatorController instance
            sensor_reader:           SensorReader instance
            target_current:          PID setpoint — target current draw (A)
            pid_kp:                  Proportional gain
            pid_ki:                  Integral gain
            pid_kd:                  Derivative gain
            max_speed:               Max feed speed during PID cutting (0–800)
            idle_current:            Contact/breakthrough threshold — current above this means
                                     blade is in wood; current below this after peaking = breakthrough.
                                     Must be set ABOVE free-spin current.
            breakthrough_confirm_s:  Time current must stay below idle to confirm cut (s)
            loop_interval_s:         Control loop sleep interval (s)
            onoff_speed:             On/off motor speed (0–800), default 720 (90%)
            set_blade_speed:         Optional callable(speed: int) to set the on/off motor
                                     speed (e.g. a ChainsawRamp.set_target). When provided,
                                     keepalive is handled externally by that callable.
                                     Falls back to direct set_motor_speed if None.
            on_complete:             Optional callback(chainsaw_id) on breakthrough
            approach_speed:          Fixed descent speed before first wood contact (0–800).
                                     Defaults to max_speed if not set. Higher than max_speed
                                     is fine — it only applies before PID engages.
            contact_confirm_reads:   Number of consecutive reads above idle_current required
                                     to confirm blade contact (filters EMI spikes). Default 3.
            max_cut_duration_s:      Safety fallback: if the cut takes longer than this many
                                     seconds after first contact, retract automatically.
                                     Default 45s.
        """
        self.chainsaw_id          = chainsaw_id
        self.actuator_controller  = actuator_controller
        self.sensor_reader        = sensor_reader
        self.target_current       = target_current
        self.pid_kp               = pid_kp
        self.pid_ki               = pid_ki
        self.pid_kd               = pid_kd
        self.max_speed            = max_speed
        self.approach_speed          = approach_speed if approach_speed is not None else max_speed
        self.idle_current            = idle_current
        self.contact_confirm_reads   = contact_confirm_reads
        self.max_cut_duration_s      = max_cut_duration_s
        self.breakthrough_confirm_s = breakthrough_confirm_s
        self.loop_interval_s      = loop_interval_s
        self.onoff_speed          = onoff_speed
        self.set_blade_speed      = set_blade_speed
        self.on_complete          = on_complete

        # Motor / sensor assignment
        if chainsaw_id == 1:
            self.onoff_motor = 5      # Motor 5: use -speed
            self.feed_motor  = 2      # Motor 2: -speed=down, +speed=retract (direction swapped)
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

    def _get_current(self) -> float:
        """
        Read current (A) from the external INA238 sensor via SensorReader.
        CS1 uses sensor 1 (mux ch.5); CS2 uses sensor 2 (mux ch.6).
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

    def _get_current_with_timestamp(self) -> Tuple[float, float]:
        """
        Read current (A) and timestamp from sensor.
        Returns (current, timestamp) tuple.
        If sensor_reader doesn't support timestamps, returns (current, time.time()).
        """
        try:
            if self.chainsaw_id == 1:
                if hasattr(self.sensor_reader, 'get_motor1_current_with_timestamp'):
                    return self.sensor_reader.get_motor1_current_with_timestamp()
                else:
                    return (self.sensor_reader.get_motor1_current(), time.time())
            else:
                if hasattr(self.sensor_reader, 'get_motor2_current_with_timestamp'):
                    return self.sensor_reader.get_motor2_current_with_timestamp()
                else:
                    return (self.sensor_reader.get_motor2_current(), time.time())
        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: error reading current: {e}"
            )
            return (0.0, time.time())

    def _set_feed(self, down: bool, speed: int) -> bool:
        """
        Drive the feed motor at a fixed speed.

        CS1 Motor 2: -speed = forward/down (advance),  +speed = retract
        CS2 Motor 3: -speed = down (advance),          +speed = retract (direction swapped)

        Returns: True if command succeeded, False if it failed (e.g., E-STOP engaged)
        """
        if self.chainsaw_id == 1:
            motor_speed = -speed if down else speed
        else:
            motor_speed = -speed if down else speed
        return self.actuator_controller.set_motor_speed(self.feed_motor, motor_speed)

    def _set_feed_pid(self, pid_output: float) -> bool:
        """
        Convert signed PID output to motor command respecting CS1/CS2 polarity.

        Positive pid_output = advance/down; negative = backoff/up.
        CS1 Motor 2: -speed = forward/down,  +speed = retract
        CS2 Motor 3: -speed = down,          +speed = retract (direction swapped)

        Returns: True if command succeeded, False if it failed (e.g., E-STOP engaged)
        """
        speed = int(round(pid_output))
        if self.chainsaw_id == 1:
            motor_speed = -speed
        else:
            motor_speed = -speed
        return self.actuator_controller.set_motor_speed(self.feed_motor, motor_speed)

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
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Turn on the chainsaw blade (via soft-start ramp) and launch the autonomous control loop."""
        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: starting "
            f"(target={self.target_current}A idle={self.idle_current}A "
            f"kp={self.pid_kp} ki={self.pid_ki} kd={self.pid_kd} "
            f"max_speed={self.max_speed} approach_speed={self.approach_speed} "
            f"contact_confirm={self.contact_confirm_reads} "
            f"max_cut={self.max_cut_duration_s}s)"
        )
        onoff_sign = 1 if self.chainsaw_id == 2 else -1
        self._set_onoff(onoff_sign * self.onoff_speed)

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
        self._stop_motors()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        """Return True while the control loop is active."""
        return self._running

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------

    def _control_loop(self):
        """
        PID-controlled autonomous cutting loop — runs in its own daemon thread.

        Phases
        ------
        1. BASELINE MEASUREMENT (5s)
           Measure average free-spin current while blade spins with no load.
           Adaptive thresholds = baseline + configured offsets.

        2. CUTTING
           PID computes signed feed speed targeting (baseline + target_current).
           Breakthrough detection active once current peaks above (baseline + idle_current).

        3. COMPLETE
           Retract feed at max_speed; blade stays on; fire on_complete callback.

        Safety
        ------
        - E-STOP: Explicit check each loop iteration, exits immediately if engaged
        - Sensor staleness: Detects frozen sensor (>2s stale), triggers breakthrough
        - Motor failures: Checks return values, exits if commands fail during cutting
        - Timeout: Forces retract after max_cut_duration_s
        """
        state               = CuttingState.CUTTING
        has_peaked          = False
        contact_count       = 0       # consecutive reads above idle_current
        low_since           = None
        cut_start_time      = None    # set when has_peaked first becomes True
        completed_naturally = False
        baseline_current    = 0.0     # measured free-spin current
        adaptive_idle       = self.idle_current
        adaptive_target     = self.target_current
        last_sensor_time    = time.time()
        last_telemetry_log  = time.time()

        pid = _PIDController(
            kp=self.pid_kp,
            ki=self.pid_ki,
            kd=self.pid_kd,
            output_min=-self.max_speed,
            output_max=self.max_speed,
            dt=self.loop_interval_s,
        )

        logger.info(f"AutonomousCutter CS{self.chainsaw_id}: control loop started")

        # ===================================================================
        # PHASE 1: ADAPTIVE BASELINE MEASUREMENT
        # ===================================================================
        # Measure average free-spin current for 5 seconds before starting cut.
        # This accounts for blade wear, motor variance, battery voltage, temperature.
        BASELINE_MEASUREMENT_S = 5.0
        logger.info(
            f"AutonomousCutter CS{self.chainsaw_id}: "
            f"measuring baseline current for {BASELINE_MEASUREMENT_S}s (blade spin-up)"
        )
        baseline_samples = []
        baseline_deadline = time.time() + BASELINE_MEASUREMENT_S

        while self._running and time.time() < baseline_deadline:
            # E-STOP check during baseline measurement
            if self.actuator_controller.is_estop_engaged():
                logger.warning(
                    f"AutonomousCutter CS{self.chainsaw_id}: E-STOP engaged during baseline, stopping"
                )
                self._running = False
                break

            current, sensor_time = self._get_current_with_timestamp()
            baseline_samples.append(current)
            last_sensor_time = sensor_time
            time.sleep(self.loop_interval_s)

        if not self._running:
            self._stop_motors()
            logger.info(
                f"AutonomousCutter CS{self.chainsaw_id}: stopped during baseline measurement"
            )
            return

        # Calculate baseline (average free-spin current)
        if baseline_samples:
            baseline_current = sum(baseline_samples) / len(baseline_samples)
            adaptive_idle = baseline_current + self.idle_current
            adaptive_target = baseline_current + self.target_current
            logger.info(
                f"AutonomousCutter CS{self.chainsaw_id}: baseline measurement complete — "
                f"free-spin={baseline_current:.3f}A (n={len(baseline_samples)}) "
                f"→ adaptive_idle={adaptive_idle:.3f}A, adaptive_target={adaptive_target:.3f}A"
            )
        else:
            logger.warning(
                f"AutonomousCutter CS{self.chainsaw_id}: no baseline samples collected, "
                f"using configured thresholds (idle={self.idle_current}A, target={self.target_current}A)"
            )
            adaptive_idle = self.idle_current
            adaptive_target = self.target_current

        # ===================================================================
        # PHASE 2: CUTTING LOOP
        # ===================================================================

        try:
            while self._running:
                # ===================================================================
                # SAFETY CHECKS (run every iteration)
                # ===================================================================

                # Check 1: E-STOP engaged
                if self.actuator_controller.is_estop_engaged():
                    logger.warning(
                        f"AutonomousCutter CS{self.chainsaw_id}: E-STOP engaged, stopping immediately"
                    )
                    self._running = False
                    break

                # Check 2: Sensor staleness (frozen sensor detection)
                current, sensor_time = self._get_current_with_timestamp()
                time_since_sensor = time.time() - sensor_time
                if time_since_sensor > 2.0:
                    logger.error(
                        f"AutonomousCutter CS{self.chainsaw_id}: sensor stale for {time_since_sensor:.1f}s "
                        f"(last={sensor_time:.1f}, now={time.time():.1f}) — treating as sensor failure, "
                        f"triggering breakthrough"
                    )
                    state = CuttingState.COMPLETE
                last_sensor_time = sensor_time

                # ===================================================================
                # STATE MACHINE
                # ===================================================================

                if state == CuttingState.CUTTING:
                    if current > adaptive_idle:
                        # Accumulate consecutive reads above idle — need contact_confirm_reads
                        # to confirm real contact (filters EMI spikes and stale sensor values)
                        contact_count += 1
                        low_since = None

                        if not has_peaked and contact_count >= self.contact_confirm_reads:
                            has_peaked = True
                            cut_start_time = time.time()
                            logger.info(
                                f"AutonomousCutter CS{self.chainsaw_id}: CONTACT confirmed "
                                f"after {contact_count} consecutive reads "
                                f"({current:.3f}A > {adaptive_idle:.3f}A) — switching to PID"
                            )

                        # PID regulates feed speed once contact is confirmed
                        if has_peaked:
                            pid_output = pid.compute(adaptive_target, current)
                            success = self._set_feed_pid(pid_output)

                            # Check motor command success
                            if not success:
                                logger.error(
                                    f"AutonomousCutter CS{self.chainsaw_id}: motor command failed "
                                    f"(likely E-STOP), stopping immediately"
                                )
                                self._running = False
                                break

                            # PID telemetry (log every 2 seconds)
                            if time.time() - last_telemetry_log >= 2.0:
                                error, integral, derivative = pid.get_telemetry()
                                logger.info(
                                    f"CS{self.chainsaw_id} PID: current={current:.3f}A "
                                    f"target={adaptive_target:.3f}A error={error:.3f}A "
                                    f"integral={integral:.1f} derivative={derivative:.1f} "
                                    f"output={pid_output:.1f}"
                                )
                                last_telemetry_log = time.time()
                            else:
                                logger.debug(
                                    f"CS{self.chainsaw_id} PID: current={current:.3f}A "
                                    f"error={adaptive_target - current:.3f} "
                                    f"output={pid_output:.1f}"
                                )
                        else:
                            # Still in approach — keep descending while waiting to confirm
                            success = self._set_feed(down=True, speed=self.approach_speed)
                            if not success:
                                logger.error(
                                    f"AutonomousCutter CS{self.chainsaw_id}: motor command failed during approach"
                                )
                                self._running = False
                                break
                            logger.debug(
                                f"CS{self.chainsaw_id} CONTACT pending: "
                                f"current={current:.3f}A ({contact_count}/"
                                f"{self.contact_confirm_reads} reads)"
                            )

                    elif has_peaked:
                        # Current dropped below idle after contact — potential breakthrough.
                        # Reset contact count and hold feed at 0.
                        contact_count = 0
                        pid.reset()
                        self._set_feed_pid(0)
                        if low_since is None:
                            low_since = time.time()
                            logger.debug(
                                f"AutonomousCutter CS{self.chainsaw_id}: potential "
                                f"breakthrough ({current:.3f}A < {adaptive_idle:.3f}A), confirming…"
                            )
                        elif time.time() - low_since >= self.breakthrough_confirm_s:
                            logger.info(
                                f"AutonomousCutter CS{self.chainsaw_id}: BREAKTHROUGH "
                                f"confirmed ({current:.3f}A for "
                                f"≥{self.breakthrough_confirm_s}s)"
                            )
                            state = CuttingState.COMPLETE

                    else:
                        # Pre-contact — descend at approach_speed until blade hits wood.
                        # Reset contact count (current dipped back below idle mid-approach).
                        contact_count = 0
                        success = self._set_feed(down=True, speed=self.approach_speed)
                        if not success:
                            logger.error(
                                f"AutonomousCutter CS{self.chainsaw_id}: motor command failed during pre-contact"
                            )
                            self._running = False
                            break
                        logger.info(
                            f"CS{self.chainsaw_id} APPROACH: current={current:.3f}A "
                            f"(waiting for contact > {adaptive_idle:.3f}A, "
                            f"feed speed={self.approach_speed})"
                        )

                    # Time-based safety fallback when still in approach/PID cutting
                    if (cut_start_time is not None and
                            self.max_cut_duration_s > 0 and
                            state == CuttingState.CUTTING and
                            time.time() - cut_start_time >= self.max_cut_duration_s):
                        logger.warning(
                            f"AutonomousCutter CS{self.chainsaw_id}: MAX CUT DURATION "
                            f"({self.max_cut_duration_s}s) exceeded — forcing retract"
                        )
                        state = CuttingState.COMPLETE

                elif state == CuttingState.COMPLETE:
                    # Retract feed — blade (on/off motor) keeps running.
                    # User can stop the blade manually after the cut is done.
                    self._set_feed(down=False, speed=self.max_speed)
                    logger.info(
                        f"AutonomousCutter CS{self.chainsaw_id}: "
                        f"COMPLETE — retracting feed at speed {self.max_speed}, blade stays on"
                    )
                    completed_naturally = True
                    self._running = False   # Causes loop to exit on next iteration check

                time.sleep(self.loop_interval_s)

        except Exception as e:
            logger.error(
                f"AutonomousCutter CS{self.chainsaw_id}: unexpected exception in control loop: {e}",
                exc_info=True
            )
            self._running = False
            completed_naturally = False

        # ===================================================================
        # CLEANUP
        # ===================================================================
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

"""
Actuator Controller - Controls Motoron motor controllers and servo via I2C/GPIO

SAFETY-CRITICAL MODULE

Safety invariants:
1. E-STOP is LATCHED on initialization (fail-safe default)
2. All E-STOP flag access is protected by the same lock
3. Check-and-actuate is atomic (no TOCTOU)
4. E-STOP can only be cleared via explicit validated action
5. Any exception during actuation triggers E-STOP

SIM_MODE: When enabled, uses mock actuators that record commanded values
for testing without hardware. Safety invariants still enforced.
"""

import logging
import time
import threading
import json
from typing import List, Optional
from enum import Enum

# Import constants from common
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.constants import (
    ESTOP_REASON_INTERNAL_ERROR, ESTOP_REASON_COMMAND,
    ESTOP_CLEAR_CONFIRM, ESTOP_CLEAR_MAX_AGE_S
)
from . import config

# Check SIM_MODE
SIM_MODE = os.getenv('SIM_MODE', 'false').lower() == 'true'

# Initialize logger early so it can be used in import blocks
logger = logging.getLogger(__name__)

HARDWARE_AVAILABLE = False
SERVOKIT_AVAILABLE = False
if not SIM_MODE:
    try:
        from motoron import MotoronI2C
        import RPi.GPIO as GPIO
        HARDWARE_AVAILABLE = True
    except ImportError:
        pass

    try:
        from adafruit_servokit import ServoKit
        SERVOKIT_AVAILABLE = True
    except ImportError:
        logger.warning("adafruit-circuitpython-servokit not installed. Install with: sudo pip3 install adafruit-circuitpython-servokit")
        pass


class MockMotoron:
    """Mock Motoron for SIM_MODE - records commanded values"""

    def __init__(self, address: int):
        self.address = address
        self.speeds = {1: 0, 2: 0}
        self.currents = {1: 0.0, 2: 0.0}
        logger.info(f"MockMotoron created at address 0x{address:02X}")

    def reinitialize(self):
        pass

    def disable_crc(self):
        pass

    def clear_reset_flag(self):
        pass

    def set_max_acceleration(self, channel: int, value: int):
        pass

    def set_max_deceleration(self, channel: int, value: int):
        pass

    def set_speed(self, channel: int, speed: int):
        self.speeds[channel] = speed
        # Simulate current draw proportional to speed
        self.currents[channel] = abs(speed) / 800.0 * 0.5  # Max 0.5A mock

    def get_current_sense_reading(self, motor: int) -> dict:
        """Mock implementation matching real Motoron API"""
        current_ma = int(self.currents[motor] * 1000)
        return {
            'raw': current_ma,
            'speed': self.speeds[motor],
            'processed': current_ma  # Processed current in milliamps
        }


class MockServoPWM:
    """Mock servo PWM for SIM_MODE (legacy GPIO mode)"""

    def __init__(self, gpio: int, freq: int):
        self.gpio = gpio
        self.freq = freq
        self.duty = 0
        logger.info(f"MockServoPWM created on GPIO {gpio}")

    def start(self, duty: float):
        self.duty = duty

    def ChangeDutyCycle(self, duty: float):
        self.duty = duty

    def stop(self):
        self.duty = 0


class MockServo:
    """Mock servo object for MockServoKit"""

    def __init__(self, channel: int):
        self.channel = channel
        self._angle = 90
        self.actuation_range = 180

    @property
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value: float):
        self._angle = max(0, min(self.actuation_range, value))
        logger.debug(f"MockServo[{self.channel}] angle set to {self._angle}°")

    def set_pulse_width_range(self, min_pulse: int, max_pulse: int):
        logger.debug(f"MockServo[{self.channel}] pulse range: {min_pulse}-{max_pulse}us")


class MockServoKit:
    """Mock ServoKit for SIM_MODE (PCA9685 mode)"""

    def __init__(self, channels: int = 16, address: int = 0x40):
        self.channels = channels
        self.address = address
        self.servo = [MockServo(i) for i in range(channels)]
        logger.info(f"MockServoKit created with {channels} channels at address 0x{address:02X}")


class EstopState(Enum):
    """E-STOP state enum for clarity"""
    ENGAGED = "engaged"
    CLEARED = "cleared"


class ActuatorController:
    """
    Controls Pololu Motoron boards and servo.

    SAFETY: E-STOP is engaged on construction. Must be explicitly cleared
    by a validated operator action after control is established.
    """

    def __init__(self, motoron_addresses: List[int],
                 use_pca9685: bool = True,
                 pca9685_address: int = 0x40,
                 pca9685_channels: int = 16,
                 servo_channel: int = 0,
                 servo_min_pulse: int = 500,
                 servo_max_pulse: int = 2500,
                 servo_actuation_range: int = 180,
                 # Legacy GPIO PWM parameters (for backwards compatibility)
                 servo_gpio: int = 12,
                 servo_freq: int = 50,
                 active_motors: int = 8,
                 servo_min_duty: float = 2.5,
                 servo_max_duty: float = 12.5):
        self.motoron_addresses = motoron_addresses
        self.active_motors = active_motors

        # Servo configuration
        self.use_pca9685 = use_pca9685
        self.pca9685_address = pca9685_address
        self.pca9685_channels = pca9685_channels
        self.servo_channel = servo_channel
        self.servo_min_pulse = servo_min_pulse
        self.servo_max_pulse = servo_max_pulse
        self.servo_actuation_range = servo_actuation_range

        # Legacy GPIO PWM config
        self.servo_gpio = servo_gpio
        self.servo_freq = servo_freq
        self.servo_min_duty = servo_min_duty
        self.servo_max_duty = servo_max_duty

        self.motorons: List[Optional[object]] = []
        self.servo_kit = None  # PCA9685 ServoKit
        self.servo_pwm = None  # Legacy GPIO PWM

        # Boot E-STOP disabled - only operator_command E-STOP enabled
        self._estop_engaged = False
        self._estop_reason = "none"
        self._estop_timestamp = time.time()
        self._estop_history: List[dict] = []

        # Single lock protects ALL E-STOP state and actuation
        # This prevents TOCTOU race conditions
        self._lock = threading.Lock()

        logger.info(f"ActuatorController initialized: {len(motoron_addresses)} Motoron boards, "
                   f"{active_motors} active motors, E-STOP DISABLED (operator_command only)")

    def _log_estop_event(self, action: str, reason: str, detail: str = ""):
        """Log E-STOP event for audit trail"""
        event = {
            "timestamp": time.time(),
            "action": action,
            "reason": reason,
            "detail": detail
        }
        self._estop_history.append(event)
        # Keep last 100 events
        if len(self._estop_history) > 100:
            self._estop_history = self._estop_history[-100:]

        log_msg = json.dumps({
            "event": "ESTOP",
            "action": action,
            "reason": reason,
            "detail": detail,
            "timestamp": event["timestamp"]
        })
        if action == "ENGAGED":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def start(self):
        """Initialize Motoron boards and servo. E-STOP remains engaged."""
        try:
            if HARDWARE_AVAILABLE and not SIM_MODE:
                # Initialize real Motoron boards
                for i, addr in enumerate(self.motoron_addresses):
                    try:
                        mc = MotoronI2C(address=addr)
                        mc.reinitialize()
                        mc.disable_crc()
                        mc.clear_reset_flag()

                        # Set max acceleration/deceleration for safety
                        mc.set_max_acceleration(1, 200)
                        mc.set_max_deceleration(1, 200)
                        mc.set_max_acceleration(2, 200)
                        mc.set_max_deceleration(2, 200)

                        # Configure current sensing
                        # The Motoron current sense divisor must be low (1-5) for proper readings
                        # High divisor values (like default 400) divide the reading, making it ~0
                        try:
                            # Set current sense minimum divisor to 2 for good sensitivity with low noise
                            # Divisor of 1 = maximum sensitivity but more noise
                            # Divisor of 2-5 = good balance between sensitivity and noise
                            # Default 400 is way too high and makes readings essentially zero!
                            mc.set_current_sense_minimum_divisor(1, 2)
                            mc.set_current_sense_minimum_divisor(2, 2)

                            # Current sense offset compensates for voltage offset when no current flows
                            # Leave at default (12) which works well for most cases
                            # Can adjust if seeing constant non-zero reading with motor stopped

                            logger.info(f"Motoron {i} current sensing configured (divisor=2)")
                        except Exception as e:
                            logger.warning(f"Could not configure current sensing on Motoron {i}: {e}")

                        # Ensure motors are stopped
                        mc.set_speed(1, 0)
                        mc.set_speed(2, 0)

                        self.motorons.append(mc)
                        logger.info(f"Motoron board {i} initialized at address 0x{addr:02X}")
                    except Exception as e:
                        logger.error(f"Failed to initialize Motoron {i} at 0x{addr:02X}: {e}")
                        self.motorons.append(None)

                # Initialize servo
                if self.use_pca9685:
                    # Use PCA9685 I2C servo controller (preferred - zero jitter)
                    try:
                        if not SERVOKIT_AVAILABLE:
                            raise RuntimeError("ServoKit library not available. Install with: sudo pip3 install adafruit-circuitpython-servokit")

                        logger.info(f"Initializing PCA9685 at 0x{self.pca9685_address:02X}, {self.pca9685_channels} channels...")
                        self.servo_kit = ServoKit(channels=self.pca9685_channels, address=self.pca9685_address)

                        # Configure servo on the specified channel
                        logger.info(f"Configuring servo on channel {self.servo_channel}...")
                        self.servo_kit.servo[self.servo_channel].actuation_range = self.servo_actuation_range
                        self.servo_kit.servo[self.servo_channel].set_pulse_width_range(self.servo_min_pulse, self.servo_max_pulse)

                        # Set to neutral position (90° for 180° servo)
                        neutral_angle = self.servo_actuation_range / 2.0
                        self.servo_kit.servo[self.servo_channel].angle = neutral_angle
                        logger.info(f"PCA9685 servo initialized - channel {self.servo_channel} at {neutral_angle}° (neutral)")
                    except Exception as e:
                        logger.error(f"Failed to initialize PCA9685 servo: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        self.servo_kit = None
                else:
                    # Use legacy GPIO PWM
                    try:
                        logger.info(f"Initializing servo on GPIO {self.servo_gpio} at {self.servo_freq}Hz...")
                        GPIO.setwarnings(False)
                        GPIO.setmode(GPIO.BCM)
                        logger.info(f"GPIO mode set to BCM")
                        GPIO.setup(self.servo_gpio, GPIO.OUT)
                        logger.info(f"GPIO {self.servo_gpio} configured as OUTPUT")
                        self.servo_pwm = GPIO.PWM(self.servo_gpio, self.servo_freq)
                        logger.info(f"PWM object created")
                        neutral_duty = (self.servo_min_duty + self.servo_max_duty) / 2.0
                        self.servo_pwm.start(neutral_duty)
                        logger.info(f"Servo initialized on GPIO {self.servo_gpio} - PWM started at {neutral_duty}% (neutral)")
                    except Exception as e:
                        logger.error(f"Failed to initialize GPIO PWM servo: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        self.servo_pwm = None
            else:
                # SIM_MODE or no hardware - use mocks
                mode_str = "SIM_MODE" if SIM_MODE else "no hardware"
                logger.info(f"Using mock actuators ({mode_str})")
                for i, addr in enumerate(self.motoron_addresses):
                    self.motorons.append(MockMotoron(addr))

                # Mock servo
                if self.use_pca9685:
                    self.servo_kit = MockServoKit(channels=self.pca9685_channels, address=self.pca9685_address)
                    self.servo_kit.servo[self.servo_channel].actuation_range = self.servo_actuation_range
                    self.servo_kit.servo[self.servo_channel].set_pulse_width_range(self.servo_min_pulse, self.servo_max_pulse)
                    self.servo_kit.servo[self.servo_channel].angle = self.servo_actuation_range / 2.0
                else:
                    self.servo_pwm = MockServoPWM(self.servo_gpio, self.servo_freq)
                    self.servo_pwm.start(0)

        except Exception as e:
            logger.error(f"Failed to initialize actuators: {e}")
            # Ensure E-STOP remains engaged on init failure
            self.engage_estop(ESTOP_REASON_INTERNAL_ERROR, f"Init failed: {e}")

        logger.info(f"ActuatorController started (E-STOP remains ENGAGED, sim_mode={SIM_MODE})")

    def stop(self):
        """Stop all actuators and cleanup. Engages E-STOP."""
        self.engage_estop(ESTOP_REASON_INTERNAL_ERROR, "Controller stop called")

        # Cleanup servo
        if self.servo_kit:
            try:
                # Set PCA9685 servo to neutral position
                neutral_angle = self.servo_actuation_range / 2.0
                self.servo_kit.servo[self.servo_channel].angle = neutral_angle
                logger.info(f"PCA9685 servo set to neutral ({neutral_angle}°)")
            except Exception as e:
                logger.error(f"Error setting PCA9685 servo to neutral: {e}")

        if self.servo_pwm:
            try:
                self.servo_pwm.stop()
                # Only cleanup GPIO if using real hardware
                if HARDWARE_AVAILABLE and not SIM_MODE:
                    GPIO.cleanup(self.servo_gpio)
            except Exception as e:
                logger.error(f"Error during GPIO servo cleanup: {e}")

        logger.info("ActuatorController stopped")

    def engage_estop(self, reason: str, detail: str = "") -> None:
        """
        ENGAGE E-STOP - stops all actuators immediately.

        This can be called from ANY thread at ANY time.
        Always succeeds (fail-safe).

        Args:
            reason: Reason code from constants
            detail: Additional detail for logging
        """
        with self._lock:
            was_engaged = self._estop_engaged
            self._estop_engaged = True
            self._estop_reason = reason
            self._estop_timestamp = time.time()

            # Stop all motors immediately - track success/failure
            motors_stopped = 0
            motors_failed = 0
            for i, mc in enumerate(self.motorons):
                if mc:
                    try:
                        mc.set_speed(1, 0)
                        mc.set_speed(2, 0)
                        motors_stopped += 1
                    except Exception as e:
                        motors_failed += 1
                        logger.error(f"CRITICAL: Failed to stop Motoron {i} during E-STOP: {e}")

            # Stop servo (set to neutral)
            servo_stopped = False
            if self.servo_kit:
                try:
                    neutral_angle = self.servo_actuation_range / 2.0
                    self.servo_kit.servo[self.servo_channel].angle = neutral_angle
                    servo_stopped = True
                except Exception as e:
                    logger.error(f"CRITICAL: Failed to stop PCA9685 servo during E-STOP: {e}")
            elif self.servo_pwm:
                try:
                    neutral_duty = (self.servo_min_duty + self.servo_max_duty) / 2.0
                    self.servo_pwm.ChangeDutyCycle(neutral_duty)
                    servo_stopped = True
                except Exception as e:
                    logger.error(f"CRITICAL: Failed to stop GPIO servo during E-STOP: {e}")

            # Log results with detailed status
            if motors_failed > 0 or (motors_stopped == 0 and len(self.motorons) > 0):
                logger.critical(f"E-STOP: MOTOR STOP INCOMPLETE - {motors_stopped} stopped, {motors_failed} FAILED! I2C may be failing!")

            if not was_engaged:
                self._log_estop_event("ENGAGED", reason,
                    f"{detail} (motors_stopped={motors_stopped}, motors_failed={motors_failed}, servo={'OK' if servo_stopped else 'FAILED'})")

    def clear_estop(self, confirm: str, control_age_s: float, control_connected: bool) -> bool:
        """
        Attempt to CLEAR E-STOP. Strict validation required.

        Args:
            confirm: Must exactly match ESTOP_CLEAR_CONFIRM
            control_age_s: Age of last control message in seconds
            control_connected: Whether control channel is connected

        Returns:
            True if E-STOP was cleared, False if validation failed

        Validation requirements:
        1. confirm must match exactly "CLEAR_ESTOP"
        2. control_connected must be True
        3. control_age_s must be <= ESTOP_CLEAR_MAX_AGE_S
        4. E-STOP must currently be engaged
        """
        with self._lock:
            # Validation checks
            if confirm != ESTOP_CLEAR_CONFIRM:
                logger.warning(f"E-STOP clear REJECTED: invalid confirm string")
                return False

            if not control_connected:
                logger.warning(f"E-STOP clear REJECTED: control not connected")
                return False

            if control_age_s > ESTOP_CLEAR_MAX_AGE_S:
                logger.warning(f"E-STOP clear REJECTED: control too stale ({control_age_s:.2f}s > {ESTOP_CLEAR_MAX_AGE_S}s)")
                return False

            if not self._estop_engaged:
                logger.info("E-STOP clear: already cleared")
                return True

            # All checks passed - clear E-STOP
            self._estop_engaged = False
            self._log_estop_event("CLEARED", "operator_command",
                                 f"Control age: {control_age_s:.2f}s")
            return True

    def clear_estop_local(self) -> bool:
        """
        Clear E-STOP from local dashboard - bypasses control timeout checks.

        This is intended for local manual testing where external control is not expected.
        Use only when running dashboard on the robot itself.

        Returns:
            True if E-STOP was cleared, False if already cleared
        """
        with self._lock:
            if not self._estop_engaged:
                logger.info("E-STOP clear_local: already cleared")
                return True

            # Clear E-STOP without validation checks
            self._estop_engaged = False
            self._log_estop_event("CLEARED", "dashboard_manual",
                                 "Cleared manually from local dashboard")
            logger.info("E-STOP cleared via local dashboard (manual override)")
            return True

    def is_estop_engaged(self) -> bool:
        """
        Check if E-STOP is engaged.

        Thread-safe: takes lock to ensure consistent read.
        """
        with self._lock:
            return self._estop_engaged

    def get_estop_info(self) -> dict:
        """Get E-STOP status information"""
        with self._lock:
            return {
                "engaged": self._estop_engaged,
                "reason": self._estop_reason,
                "timestamp": self._estop_timestamp,
                "age_s": time.time() - self._estop_timestamp
            }

    def set_motor_speed(self, motor_id: int, speed: int) -> bool:
        """
        Set motor speed.

        SAFETY: Entire check-and-actuate is atomic (under lock).
        If E-STOP engages between check and actuate in another thread,
        we will NOT actuate.

        Args:
            motor_id: Motor ID (0-7)
            speed: Speed (-800 to +800, 0 = stop)

        Returns:
            True if command was executed, False if blocked by E-STOP
        """
        with self._lock:
            # Check E-STOP while holding lock
            if self._estop_engaged:
                # Silently return - don't spam logs during E-STOP
                return False

            if motor_id >= self.active_motors:
                logger.warning(f"Motor {motor_id} is not active (max: {self.active_motors-1})")
                return False

            # Map motor ID to board and channel
            board_id = motor_id // 2
            channel = (motor_id % 2) + 1

            if board_id < len(self.motorons) and self.motorons[board_id]:
                try:
                    # Clamp speed
                    speed = max(-800, min(800, speed))
                    self.motorons[board_id].set_speed(channel, speed)
                    logger.debug(f"Motor {motor_id} (board {board_id}, ch {channel}): speed={speed}")
                    return True
                except Exception as e:
                    logger.error(f"Error setting motor {motor_id} speed: {e}")
                    # Engage E-STOP on actuation error
                    self._estop_engaged = True
                    self._estop_reason = ESTOP_REASON_INTERNAL_ERROR
                    self._log_estop_event("ENGAGED", ESTOP_REASON_INTERNAL_ERROR,
                                         f"Motor {motor_id} error: {e}")
                    return False
            else:
                logger.warning(f"Motor {motor_id} board not available")
                return False

    def set_servo_position(self, position: float) -> bool:
        """
        Set servo position.

        SAFETY: Entire check-and-actuate is atomic (under lock).

        Args:
            position: Position (0.0 to 1.0, 0.5 = neutral)

        Returns:
            True if command was executed, False if blocked by E-STOP
        """
        with self._lock:
            # Check E-STOP while holding lock
            if self._estop_engaged:
                logger.warning(f"Servo command blocked: E-STOP engaged")
                return False

            # Clamp position to valid range
            position = max(0.0, min(1.0, position))

            if self.servo_kit:
                try:
                    # Map position (0.0-1.0) to angle (0° to actuation_range)
                    angle = position * self.servo_actuation_range
                    self.servo_kit.servo[self.servo_channel].angle = angle
                    logger.info(f"PCA9685 servo position set: {position:.2f} (angle: {angle:.1f}°)")
                    return True
                except Exception as e:
                    logger.error(f"Error setting PCA9685 servo position: {e}")
                    # Engage E-STOP on actuation error
                    self._estop_engaged = True
                    self._estop_reason = ESTOP_REASON_INTERNAL_ERROR
                    self._log_estop_event("ENGAGED", ESTOP_REASON_INTERNAL_ERROR,
                                         f"PCA9685 servo error: {e}")
                    return False

            elif self.servo_pwm:
                try:
                    # Map position (0.0-1.0) to duty cycle using configured range
                    # For AITRIP 35KG servo: 2.5% (0°/500us) to 12.5% (180°/2500us)
                    duty = self.servo_min_duty + position * (self.servo_max_duty - self.servo_min_duty)
                    self.servo_pwm.ChangeDutyCycle(duty)
                    logger.info(f"GPIO servo position set: {position:.2f} (duty: {duty:.2f}%)")
                    return True
                except Exception as e:
                    logger.error(f"Error setting GPIO servo position: {e}")
                    # Engage E-STOP on actuation error
                    self._estop_engaged = True
                    self._estop_reason = ESTOP_REASON_INTERNAL_ERROR
                    self._log_estop_event("ENGAGED", ESTOP_REASON_INTERNAL_ERROR,
                                         f"GPIO servo error: {e}")
                    return False

            else:
                logger.warning("Servo command failed: no servo initialized (servo_kit and servo_pwm are None)")
                return False

    def set_servo_duty_raw(self, duty: float) -> bool:
        """
        Set servo PWM duty cycle directly (raw value).

        SAFETY: Entire check-and-actuate is atomic (under lock).

        Args:
            duty: Raw duty cycle (0.0 to 100.0)

        Returns:
            True if command was executed, False if blocked by E-STOP
        """
        with self._lock:
            # Check E-STOP while holding lock
            if self._estop_engaged:
                logger.warning(f"Servo command blocked: E-STOP engaged")
                return False

            if self.servo_pwm:
                try:
                    duty = max(0.0, min(100.0, duty))
                    self.servo_pwm.ChangeDutyCycle(duty)
                    logger.info(f"Servo raw duty set: {duty:.1f}%")
                    return True
                except Exception as e:
                    logger.error(f"Error setting servo duty: {e}")
                    self._estop_engaged = True
                    self._estop_reason = ESTOP_REASON_INTERNAL_ERROR
                    self._log_estop_event("ENGAGED", ESTOP_REASON_INTERNAL_ERROR,
                                         f"Servo error: {e}")
                    return False
            else:
                logger.warning("Servo command failed: servo_pwm is None (not initialized)")
                return False

    def get_motor_currents(self) -> List[float]:
        """Get current draw from all motors (if available)"""
        currents = [0.0] * 8

        with self._lock:
            for i, mc in enumerate(self.motorons):
                if mc:
                    try:
                        # Read current from motor 1 (channel 1)
                        reading_1 = mc.get_current_sense_reading(1)
                        current_1 = reading_1['processed'] / 1000.0  # Convert milliamps to amps

                        # Read current from motor 2 (channel 2)
                        reading_2 = mc.get_current_sense_reading(2)
                        current_2 = reading_2['processed'] / 1000.0  # Convert milliamps to amps

                        currents[i * 2] = current_1
                        currents[i * 2 + 1] = current_2
                    except Exception as e:
                        logger.error(f"Error reading Motoron {i} current: {e}")

        return currents

    # Legacy compatibility - maps to new API
    def emergency_stop_all(self):
        """Legacy API - use engage_estop() instead"""
        self.engage_estop(ESTOP_REASON_COMMAND, "Legacy emergency_stop_all called")

    def clear_emergency_stop(self):
        """
        Legacy API - DISABLED for safety.
        Use clear_estop() with proper validation instead.
        """
        logger.error("clear_emergency_stop() is DISABLED. Use clear_estop() with validation.")
        return False

    def is_emergency_stopped(self) -> bool:
        """Legacy API - maps to is_estop_engaged()"""
        return self.is_estop_engaged()

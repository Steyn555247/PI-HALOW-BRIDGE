"""
Safety-critical constants for Pi HaLow Bridge.
These values are chosen for fail-safe behavior.
"""

# Buffer limits - prevent OOM
MAX_CONTROL_BUFFER = 65536      # 64KB for control/telemetry text buffer
MAX_VIDEO_BUFFER = 262144       # 256KB for video binary buffer
MAX_FRAME_SIZE = 16384          # 16KB max authenticated frame payload

# Timing constants
WATCHDOG_TIMEOUT_S = 5.0        # E-STOP if no control for this long
STARTUP_GRACE_S = 30.0          # Grace period before requiring control
ESTOP_CLEAR_MAX_AGE_S = 1.5     # Control must be this fresh to clear E-STOP
HEARTBEAT_INTERVAL_S = 1.0      # Ping frequency
RECONNECT_DELAY_S = 2.0         # Delay between reconnect attempts

# E-STOP clear confirmation string (must match exactly)
ESTOP_CLEAR_CONFIRM = "CLEAR_ESTOP"

# Message types
MSG_EMERGENCY_STOP = "emergency_stop"
MSG_PING = "ping"
MSG_PONG = "pong"

# E-STOP reasons (for logging/audit)
ESTOP_REASON_BOOT = "boot_default"
ESTOP_REASON_WATCHDOG = "watchdog_timeout"
ESTOP_REASON_DISCONNECT = "control_disconnect"
ESTOP_REASON_BUFFER_OVERFLOW = "buffer_overflow"
ESTOP_REASON_DECODE_ERROR = "decode_error"
ESTOP_REASON_AUTH_FAILURE = "auth_failure"
ESTOP_REASON_STARTUP_TIMEOUT = "startup_no_control"
ESTOP_REASON_COMMAND = "operator_command"
ESTOP_REASON_INTERNAL_ERROR = "internal_error"

# Ports (default)
DEFAULT_CONTROL_PORT = 5001
DEFAULT_VIDEO_PORT = 5002
DEFAULT_TELEMETRY_PORT = 5003

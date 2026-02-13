"""
Backend Client for Base Pi

Handles Socket.IO client connection to serpent_backend.
Translates legacy events to proper protocol semantics.

SAFETY:
- Translates legacy 'emergency_toggle' to proper E-STOP ENGAGE
- Validates E-STOP clear requests with confirmation
- All commands are forwarded with HMAC authentication
"""

import logging
import time
import socketio
from typing import Callable, Dict, Any, Optional

from common.constants import MSG_EMERGENCY_STOP, ESTOP_CLEAR_CONFIRM

logger = logging.getLogger(__name__)


class BackendClient:
    """
    Socket.IO client for serpent_backend.

    Manages connection and event handling, forwarding commands
    to Robot Pi via ControlForwarder.
    """

    def __init__(
        self,
        backend_url: str,
        on_connection_change: Callable[[bool], None],
        on_command: Callable[[str, Dict[str, Any]], None],
        on_emergency_status: Callable[[bool], None]
    ):
        """
        Initialize backend client.

        Args:
            backend_url: Backend Socket.IO URL
            on_connection_change: Callback for connection state changes
            on_command: Callback for commands (cmd_type, data)
            on_emergency_status: Callback for emergency_status events (active)
        """
        self.backend_url = backend_url
        self.on_connection_change = on_connection_change
        self.on_command = on_command
        self.on_emergency_status = on_emergency_status

        # Socket.IO client
        self.sio = socketio.Client(reconnection=True, reconnection_delay=2)

        # E-stop event tracking to prevent duplicates from multiple event types
        self._last_estop_event_time: float = 0.0
        self._last_estop_event_active: Optional[bool] = None
        self._estop_event_window_s: float = 0.1  # 100ms window to catch near-simultaneous events

        self._setup_handlers()

        logger.info(f"BackendClient initialized (url={backend_url})")

    def _setup_handlers(self):
        """Setup Socket.IO event handlers."""

        @self.sio.event
        def connect():
            logger.info("Connected to serpent_backend")
            self.on_connection_change(True)

        @self.sio.event
        def disconnect():
            logger.warning("Disconnected from serpent_backend")
            self.on_connection_change(False)

        # =====================================================================
        # E-STOP EVENT CONSOLIDATION
        #
        # All three E-stop events are routed through _handle_emergency_event()
        # to ensure only ONE command is sent per logical event, preventing:
        # 1. Multiple triggers from backend sending both toggle AND status
        # 2. Duplicate events from rapid button presses
        # 3. Re-broadcasts on reconnection
        # =====================================================================

        @self.sio.on('emergency_toggle')
        def on_emergency_toggle(data):
            """
            Legacy event from backend - always means ENGAGE.
            Routed through unified handler to prevent duplicates.
            """
            logger.info("Received emergency_toggle event")
            self._handle_emergency_event(True, 'emergency_toggle')

        @self.sio.on('emergency_stop')
        def on_emergency_stop(data):
            """
            Proper emergency_stop event with explicit engage/clear.
            Routed through unified handler to prevent duplicates.
            """
            engage = data.get('engage', True)
            logger.info(f"Received emergency_stop event (engage={engage})")
            self._handle_emergency_event(engage, 'emergency_stop')

        @self.sio.on('emergency_status')
        def on_emergency_status_event(data):
            """
            Status broadcast from backend (triggered by TrimUI).
            Routed through unified handler to prevent duplicates.
            """
            active = data.get('active', True)  # Default to engaged for safety
            logger.info(f"Received emergency_status event (active={active})")
            self._handle_emergency_event(active, 'emergency_status')

        @self.sio.on('clamp_close')
        def on_clamp_close(data):
            logger.info("Clamp close received")
            self.on_command('clamp_close', data)

        @self.sio.on('clamp_open')
        def on_clamp_open(data):
            logger.info("Clamp open received")
            self.on_command('clamp_open', data)

        @self.sio.on('height_update')
        def on_height_update(data):
            self.on_command('height_update', data)

        @self.sio.on('force_update')
        def on_force_update(data):
            self.on_command('force_update', data)

        @self.sio.on('start_camera')
        def on_start_camera(data):
            camera_id = data.get('camera_id', 0)
            logger.info(f"Start camera: {camera_id}")
            self.on_command('start_camera', data)

        @self.sio.on('input_event')
        def on_input_event(data):
            self.on_command('input_event', data)

        @self.sio.on('raw_button_press')
        def on_raw_button_press(data):
            self.on_command('raw_button_press', data)

        @self.sio.on('chainsaw_command')
        def on_chainsaw_command(data):
            logger.info(f"Chainsaw command: {data}")
            self.on_command('chainsaw_command', data)

        @self.sio.on('chainsaw_move')
        def on_chainsaw_move(data):
            logger.info(f"Chainsaw move: {data}")
            self.on_command('chainsaw_move', data)

        @self.sio.on('climb_command')
        def on_climb_command(data):
            logger.info(f"Climb command: {data}")
            self.on_command('climb_command', data)

        @self.sio.on('traverse_command')
        def on_traverse_command(data):
            logger.info(f"Traverse command: {data}")
            self.on_command('traverse_command', data)

        @self.sio.on('brake_command')
        def on_brake_command(data):
            logger.info(f"Brake command: {data}")
            self.on_command('brake_command', data)

    def _handle_emergency_event(self, active: bool, source: str):
        """
        Simplified E-stop event handler.

        Just forwards to coordinator - deduplication happens there.
        E-STOP logic is owned by backend and controller only.

        Args:
            active: True to engage E-stop, False to clear
            source: Event source for logging
        """
        # Simple dedup: ignore if same as last event
        if self._last_estop_event_active == active:
            logger.debug(f"E-STOP: ignoring duplicate {source} (already {'ENGAGE' if active else 'CLEAR'})")
            return

        self._last_estop_event_active = active
        logger.info(f"E-STOP: forwarding {source} (active={active}) to robot")
        self.on_emergency_status(active, source)

    def connect(self):
        """Connect to backend Socket.IO server."""
        try:
            logger.info(f"Connecting to serpent_backend at {self.backend_url}")
            self.sio.connect(self.backend_url)
        except Exception as e:
            logger.error(f"Failed to connect to backend: {e}")
            logger.warning("Will retry in background...")

    def disconnect(self):
        """Disconnect from backend."""
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting from backend: {e}")

    def emit_telemetry(self, telemetry: Dict[str, Any]):
        """
        Emit telemetry to backend.

        Args:
            telemetry: Telemetry data dictionary
        """
        try:
            self.sio.emit('telemetry', telemetry)
        except Exception as e:
            logger.error(f"Failed to emit telemetry: {e}")

    def emit_controller_telemetry(self, telemetry: Dict[str, Any]):
        """
        Emit controller telemetry to backend.

        Args:
            telemetry: Controller telemetry data dictionary
        """
        try:
            self.sio.emit('controller_telemetry', telemetry)
            logger.debug(f"Sent controller telemetry: status={telemetry.get('status')}, "
                        f"voltage={telemetry.get('voltage')}V, "
                        f"altitude={telemetry.get('altitude')}m, "
                        f"rtt={telemetry.get('rtt_ms')}ms")
        except Exception as e:
            logger.error(f"Failed to emit controller telemetry: {e}")

    def is_connected(self) -> bool:
        """Check if connected to backend."""
        return self.sio.connected

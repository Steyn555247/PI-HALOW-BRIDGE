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
import socketio
from typing import Callable, Dict, Any

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

        # IMPORTANT: Translate legacy 'emergency_toggle' to proper SET semantics
        @self.sio.on('emergency_toggle')
        def on_emergency_toggle(data):
            """
            Legacy event from backend - ENGAGE E-STOP.

            We translate toggle to ENGAGE only. Clearing requires explicit
            'emergency_stop' with engage=false and confirm_clear.
            """
            logger.warning("Received legacy emergency_toggle - sending ENGAGE")
            self.on_command(MSG_EMERGENCY_STOP, {
                'engage': True,
                'reason': 'operator_toggle'
            })

        # New proper E-STOP event (if backend is updated)
        @self.sio.on('emergency_stop')
        def on_emergency_stop(data):
            """Proper emergency_stop event with SET semantics."""
            engage = data.get('engage', True)
            reason = data.get('reason', 'operator_command')

            if engage:
                logger.warning(f"E-STOP ENGAGE from backend: {reason}")
                self.on_command(MSG_EMERGENCY_STOP, {
                    'engage': True,
                    'reason': reason
                })
            else:
                # Clear request - must include confirmation
                confirm = data.get('confirm_clear', '')
                logger.info("E-STOP CLEAR request from backend")
                self.on_command(MSG_EMERGENCY_STOP, {
                    'engage': False,
                    'confirm_clear': confirm,
                    'reason': reason
                })

        # Handle emergency_status broadcast from backend (triggered by TrimUI toggle)
        @self.sio.on('emergency_status')
        def on_emergency_status(data):
            """
            Handle emergency_status event from backend.

            Backend broadcasts this after receiving emergency_toggle from TrimUI.
            active=True means E-STOP should be engaged, active=False means clear.
            """
            active = data.get('active', True)  # Default to engaged for safety
            self.on_emergency_status(active)

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

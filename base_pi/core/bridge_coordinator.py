"""
Bridge Coordinator for Base Pi

Main orchestrator that replaces the monolithic halow_bridge.py.

SAFETY:
- Translates legacy 'emergency_toggle' from backend to proper 'emergency_stop' SET semantics
- Watchdog only ENGAGES E-STOP (sends engage=true), never clears
- All control messages are authenticated with HMAC
- Heartbeat ping/pong for RTT measurement

REFACTORING:
Extracts 801-line monolith into modular components:
- StateManager: State tracking and health scoring
- BackendClient: Socket.IO client to serpent_backend
- WatchdogMonitor: Safety timeout monitoring
- VideoHTTPServer: MJPEG HTTP server
- ControlForwarder: Command forwarding (existing module)
- TelemetryReceiver: Telemetry receiving (existing module)
- VideoReceiver: Video receiving (existing module)

Result: ~200 LOC coordinator + clean component interfaces.
"""

import logging
import time
import signal
import sys
import os
import threading
from typing import Optional, Dict, Any

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Base pi imports
from base_pi import config
from base_pi.control_forwarder import ControlForwarder
from base_pi.telemetry_receiver import TelemetryReceiver
from base_pi.video_receiver import VideoReceiver
from base_pi.telemetry_buffer import TelemetryBuffer
from base_pi.telemetry_websocket import TelemetryWebSocketServer, run_websocket_server
from base_pi.telemetry_storage import TelemetryStorage
from base_pi.telemetry_controller import format_for_controller
from base_pi.video_recorder import VideoRecorder

# Common imports
from common.framing import SecureFramer
from common.constants import (
    MSG_EMERGENCY_STOP, MSG_PING,
    WATCHDOG_TIMEOUT_S, HEARTBEAT_INTERVAL_S, ESTOP_CLEAR_CONFIRM
)

# Extracted modules (relative imports)
from .state_manager import StateManager
from .backend_client import BackendClient
from .watchdog_monitor import WatchdogMonitor
from base_pi.video.video_http_server import VideoHTTPServer

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HaLowBridge:
    """
    Main bridge coordinator for Base Pi.

    Translates between serpent_backend (legacy events) and Robot Pi (authenticated protocol).
    """

    def __init__(self):
        """Initialize all bridge components."""
        # Initialize secure framing
        self.framer = SecureFramer(role="base_pi")
        if not self.framer.is_authenticated():
            logger.critical("NO VALID PSK - Cannot send authenticated commands to Robot Pi")

        # State manager
        self.state = StateManager(default_camera_id=config.DEFAULT_CAMERA_ID)

        # Components
        self.control_forwarder = ControlForwarder(
            robot_ip=config.ROBOT_PI_IP,
            control_port=config.CONTROL_PORT,
            reconnect_delay=config.RECONNECT_DELAY,
            framer=self.framer
        )

        self.telemetry_receiver = TelemetryReceiver(
            telemetry_port=config.TELEMETRY_PORT,
            on_telemetry=self._on_telemetry_received
        )

        self.video_receiver = None
        if config.VIDEO_ENABLED:
            self.video_receiver = VideoReceiver(
                video_port=config.VIDEO_PORT,
                buffer_size=config.VIDEO_BUFFER_SIZE
            )

        # Telemetry buffer for dashboard
        self.telemetry_buffer: Optional[TelemetryBuffer] = None
        if config.DASHBOARD_ENABLED:
            self.telemetry_buffer = TelemetryBuffer(max_samples=config.TELEMETRY_BUFFER_SIZE)
            logger.info(f"Telemetry buffer initialized (size: {config.TELEMETRY_BUFFER_SIZE})")

        # WebSocket server for dashboard
        self.websocket_server: Optional[TelemetryWebSocketServer] = None
        self.websocket_thread: Optional[threading.Thread] = None

        # Storage for telemetry and video
        self.telemetry_storage: Optional[TelemetryStorage] = None
        self.video_recorder: Optional[VideoRecorder] = None
        if config.STORAGE_ENABLED:
            # Initialize telemetry storage
            telemetry_path = os.path.join(config.STORAGE_BASE_PATH, 'telemetry')
            self.telemetry_storage = TelemetryStorage(
                base_path=telemetry_path,
                retention_days=config.TELEMETRY_RETENTION_DAYS
            )

            # Initialize video recorder if video is enabled
            if self.video_receiver:
                video_path = os.path.join(config.STORAGE_BASE_PATH, 'video')
                self.video_recorder = VideoRecorder(
                    base_path=video_path,
                    retention_days=config.VIDEO_RETENTION_DAYS,
                    rotation_minutes=config.VIDEO_ROTATION_MINUTES
                )

        # Backend client
        self.backend_client = BackendClient(
            backend_url=config.BACKEND_SOCKETIO_URL,
            on_connection_change=self._on_backend_connection_change,
            on_command=self._on_backend_command,
            on_emergency_status=self._on_emergency_status
        )

        # Watchdog monitor
        self.watchdog = WatchdogMonitor(
            on_estop_engage=self._send_estop_engage,
            get_last_telemetry_time=lambda: self.telemetry_receiver.get_last_telemetry_time(),
            status_interval=10.0
        )

        # Video HTTP server
        self.http_server: Optional[VideoHTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None

        # Heartbeat thread
        self.heartbeat_thread: Optional[threading.Thread] = None

        # Running flag
        self.running = False

        logger.info("HaLowBridge initialized (modular architecture)")

    def _on_backend_connection_change(self, connected: bool):
        """Handle backend connection state change."""
        self.state.set_backend_connected(connected)

    def _on_backend_command(self, cmd_type: str, data: Dict[str, Any]):
        """Handle command from backend."""
        # Update camera ID if start_camera command
        if cmd_type == 'start_camera':
            camera_id = data.get('camera_id', 0)
            self.state.set_camera_id(camera_id)

        # Forward command to Robot Pi
        self.control_forwarder.send_command(cmd_type, data)

    def _on_emergency_status(self, active: bool):
        """Handle emergency_status event from backend."""
        # Check debounce
        if self.state.should_debounce_emergency_status(active):
            return

        # Send E-STOP command
        if active:
            logger.warning("E-STOP ENGAGE from emergency_status")
            self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
                'engage': True,
                'reason': 'operator_toggle'
            })
        else:
            logger.info("E-STOP CLEAR from emergency_status")
            self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
                'engage': False,
                'confirm_clear': ESTOP_CLEAR_CONFIRM,
                'reason': 'operator_toggle'
            })

    def _send_estop_engage(self, cmd_type: str, data: Dict[str, Any]):
        """Send E-STOP engage command to Robot Pi."""
        self.control_forwarder.send_command(cmd_type, data)

    def _on_telemetry_received(self, telemetry: Dict[str, Any]):
        """Callback when telemetry is received from Robot Pi."""
        # Extract E-STOP state (both engaged flag and reason)
        estop_info = telemetry.get('estop', {})
        self.state.update_estop_state(
            estop_info.get('engaged'),
            estop_info.get('reason')
        )

        # Compute RTT from pong data if present
        pong = telemetry.get('pong')
        if pong:
            self.state.update_rtt(pong.get('ping_seq'), pong.get('ping_ts', time.time()))

        # Include RTT in telemetry for backend
        telemetry['rtt_ms'] = self.state.get_rtt()

        # Add to telemetry buffer
        if self.telemetry_buffer:
            self.telemetry_buffer.add_sample(telemetry)

        # Broadcast to WebSocket clients (dashboard)
        if self.websocket_server:
            self.websocket_server.broadcast_telemetry_sync(telemetry)

        # Store telemetry to database
        if self.telemetry_storage:
            self.telemetry_storage.write_telemetry(telemetry)

        # Forward full telemetry to backend via Socket.IO
        if self.state.is_backend_connected():
            self.backend_client.emit_telemetry(telemetry)

        # Rate-limited controller telemetry
        if self.state.should_send_controller_update(config.CONTROLLER_TELEMETRY_RATE_HZ):
            controller_data = format_for_controller(telemetry)
            if self.state.is_backend_connected():
                self.backend_client.emit_controller_telemetry(controller_data)
            else:
                logger.debug("Controller telemetry not sent - backend disconnected")

    def _heartbeat_loop(self):
        """Send periodic pings to Robot Pi for RTT measurement."""
        while self.running:
            try:
                if self.control_forwarder.is_connected():
                    ping_seq = self.state.get_next_ping_seq()
                    ping_time = time.time()
                    self.state.update_ping_sent(ping_seq, ping_time)

                    self.control_forwarder.send_command(MSG_PING, {
                        'ts': ping_time,
                        'seq': ping_seq
                    })

                time.sleep(HEARTBEAT_INTERVAL_S)

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                time.sleep(1.0)

    def _start_video_http_server(self):
        """Start the Video HTTP server in a background thread."""
        try:
            self.http_server = VideoHTTPServer(
                port=config.VIDEO_HTTP_PORT,
                video_receiver=self.video_receiver,
                telemetry_buffer=self.telemetry_buffer
            )
            self.http_server.start()

            self.http_thread = threading.Thread(
                target=self.http_server.serve_forever,
                daemon=True
            )
            self.http_thread.start()
        except Exception as e:
            logger.error(f"Failed to start Video HTTP server: {e}")

    def start(self):
        """Start the bridge."""
        self.running = True

        # Start components
        logger.info("Starting components...")

        self.control_forwarder.start()
        self.telemetry_receiver.start()

        if self.video_receiver:
            self.video_receiver.start()

        # Start telemetry storage
        if self.telemetry_storage:
            self.telemetry_storage.start()

        # Start video recorder
        if self.video_recorder and self.video_receiver:
            self.video_recorder.start_recording(self.video_receiver)

        # Start WebSocket server for dashboard
        if config.DASHBOARD_ENABLED and self.telemetry_buffer:
            self.websocket_server = TelemetryWebSocketServer(
                port=config.DASHBOARD_WS_PORT,
                buffer=self.telemetry_buffer
            )
            self.websocket_thread = threading.Thread(
                target=run_websocket_server,
                args=(self.websocket_server,),
                daemon=True
            )
            self.websocket_thread.start()
            logger.info(f"WebSocket server starting on port {config.DASHBOARD_WS_PORT}")

        # Start Video HTTP server for MJPEG streaming
        if config.VIDEO_HTTP_ENABLED:
            self._start_video_http_server()

        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        # Connect to backend
        self.backend_client.connect()

        logger.info("HaLowBridge started successfully")

        # Watchdog loop (runs in main thread)
        self._watchdog_loop()

    def _watchdog_loop(self):
        """Monitor connection health and trigger E-STOP if needed."""
        while self.running:
            try:
                time.sleep(1.0)

                # Check safety conditions
                self.watchdog.check_safety()

                # Log status periodically
                self.watchdog.log_status(
                    backend_connected=self.state.is_backend_connected(),
                    control_connected=self.control_forwarder.is_connected(),
                    telemetry_connected=self.telemetry_receiver.is_connected(),
                    video_connected=self.video_receiver.is_connected() if self.video_receiver else False,
                    robot_estop_state=self.state.get_estop_state(),
                    psk_valid=self.framer.is_authenticated(),
                    robot_estop_reason=self.state.get_estop_reason()
                )

            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")

    def stop(self):
        """Stop the bridge."""
        logger.info("Stopping HaLowBridge...")
        self.running = False

        # Disconnect from backend
        self.backend_client.disconnect()

        # Stop storage
        if self.telemetry_storage:
            self.telemetry_storage.stop()

        if self.video_recorder:
            self.video_recorder.stop_recording()

        # Stop Video HTTP server
        if self.http_server:
            self.http_server.shutdown()

        # Stop components
        self.control_forwarder.stop()
        self.telemetry_receiver.stop()

        if self.video_receiver:
            self.video_receiver.stop()

        logger.info("HaLowBridge stopped")

    def get_health(self) -> dict:
        """Get health status for monitoring."""
        last_telemetry_time = self.telemetry_receiver.get_last_telemetry_time()
        last_telemetry_age = None
        if last_telemetry_time > 0:
            last_telemetry_age = time.time() - last_telemetry_time

        return self.state.get_health_status(
            control_connected=self.control_forwarder.is_connected(),
            telemetry_connected=self.telemetry_receiver.is_connected(),
            video_connected=self.video_receiver.is_connected() if self.video_receiver else False,
            last_telemetry_age=last_telemetry_age,
            watchdog_timeout=WATCHDOG_TIMEOUT_S,
            psk_valid=self.framer.is_authenticated()
        )


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received")
    if bridge:
        bridge.stop()
    sys.exit(0)


# Global bridge instance
bridge: Optional[HaLowBridge] = None


def main():
    """Main entry point."""
    global bridge

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("SERPENT BASE PI BRIDGE STARTING (Modular Architecture)")
    logger.info("=" * 60)

    # Create and start bridge
    bridge = HaLowBridge()

    try:
        bridge.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if bridge:
            bridge.stop()
        sys.exit(1)


if __name__ == '__main__':
    main()

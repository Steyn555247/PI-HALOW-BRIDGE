"""
HaLow Bridge - Main coordinator for Base Pi

Integrates with serpent_backend to receive control and forward to Robot Pi.
Receives video and telemetry from Robot Pi.

SAFETY:
- Translates legacy 'emergency_toggle' from backend to proper 'emergency_stop' SET semantics
- Watchdog only ENGAGES E-STOP (sends engage=true), never clears
- All control messages are authenticated with HMAC
- Heartbeat ping/pong for RTT measurement
"""

import logging
import time
import signal
import sys
import os
import json
import socket
import threading
from typing import Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial

import socketio

# Add parent to path for common imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
from control_forwarder import ControlForwarder
from telemetry_receiver import TelemetryReceiver
from video_receiver import VideoReceiver
from telemetry_buffer import TelemetryBuffer
from telemetry_websocket import TelemetryWebSocketServer, run_websocket_server
from telemetry_storage import TelemetryStorage
from telemetry_controller import format_for_controller, should_send_update
from video_recorder import VideoRecorder
from telemetry_metrics import add_derived_metrics
from common.framing import SecureFramer
from common.constants import (
    MSG_EMERGENCY_STOP, MSG_PING, MSG_PONG,
    WATCHDOG_TIMEOUT_S, HEARTBEAT_INTERVAL_S, ESTOP_CLEAR_CONFIRM
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VideoHTTPHandler(BaseHTTPRequestHandler):
    """
    HTTP handler for MJPEG video streaming and telemetry API.

    Serves video frames from the VideoReceiver as an MJPEG stream.
    Also serves dashboard and telemetry API endpoints.
    """

    def __init__(self, video_receiver, telemetry_buffer, *args, **kwargs):
        self.video_receiver = video_receiver
        self.telemetry_buffer = telemetry_buffer
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Suppress default HTTP logging (too verbose)"""
        pass

    def do_GET(self):
        """Handle GET requests"""
        logger.debug(f"GET request: {self.path}")

        if self.path == '/video' or self.path == '/video.mjpeg':
            self._serve_mjpeg_stream()
        elif self.path == '/frame' or self.path == '/frame.jpg':
            self._serve_single_frame()
        elif self.path == '/health':
            self._serve_health()
        elif self.path == '/dashboard' or self.path == '/':
            self._serve_file('static/dashboard.html', 'text/html')
        elif self.path.startswith('/static/'):
            self._serve_static_file(self.path[8:])
        elif self.path == '/api/telemetry/latest':
            self._serve_telemetry_latest()
        elif self.path.startswith('/api/telemetry/history'):
            self._serve_telemetry_history()
        elif self.path == '/api/telemetry/stats':
            self._serve_telemetry_stats()
        else:
            logger.warning(f"404 Not Found: {self.path}")
            self.send_error(404, 'Not Found')

    def _serve_mjpeg_stream(self):
        """Serve MJPEG stream (multipart/x-mixed-replace)"""
        if not self.video_receiver:
            self.send_error(503, 'Video receiver not available')
            return

        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            last_frame_time = 0
            while True:
                # Only send if we have a new frame (check timestamp)
                current_time = self.video_receiver.last_frame_time
                if current_time > last_frame_time:
                    frame = self.video_receiver.get_frame()
                    if frame:
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame)}\r\n'.encode())
                        self.wfile.write(b'\r\n')
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                        last_frame_time = current_time
                else:
                    # Wait briefly for new frame (10ms = 100 FPS max check rate)
                    time.sleep(0.01)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected

    def _serve_single_frame(self):
        """Serve a single JPEG frame"""
        if not self.video_receiver:
            self.send_error(503, 'Video receiver not available')
            return

        frame = self.video_receiver.get_frame()
        if frame:
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', len(frame))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_error(503, 'No frame available')

    def _serve_health(self):
        """Serve health status"""
        connected = self.video_receiver.is_connected() if self.video_receiver else False
        stats = self.video_receiver.get_stats() if self.video_receiver else {}

        health = {
            'status': 'ok' if connected else 'degraded',
            'video_connected': connected,
            'frames_received': stats.get('frames_received', 0)
        }

        body = json.dumps(health).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath, content_type):
        """Serve a static file"""
        try:
            # Get the directory where this script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            full_path = os.path.join(script_dir, filepath)

            logger.debug(f"Attempting to serve file: {full_path}")

            if not os.path.exists(full_path):
                logger.error(f"File not found: {full_path}")
                self.send_error(404, f'File not found: {filepath}')
                return

            with open(full_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
            logger.debug(f"Successfully served file: {filepath}")
        except FileNotFoundError as e:
            logger.error(f"File not found: {filepath} - {e}")
            self.send_error(404, f'File not found: {filepath}')
        except Exception as e:
            logger.error(f"Error serving file {filepath}: {e}")
            self.send_error(500, 'Internal server error')

    def _serve_static_file(self, filepath):
        """Serve static files (CSS, JS, etc.)"""
        content_types = {
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.svg': 'image/svg+xml'
        }

        ext = os.path.splitext(filepath)[1]
        content_type = content_types.get(ext, 'application/octet-stream')
        self._serve_file(f'static/{filepath}', content_type)

    def _serve_telemetry_latest(self):
        """Serve latest telemetry data"""
        if not self.telemetry_buffer:
            self.send_error(503, 'Telemetry buffer not available')
            return

        latest = self.telemetry_buffer.get_latest()
        if latest:
            # Add derived metrics
            enhanced = add_derived_metrics(latest)
            body = json.dumps(enhanced).encode()
        else:
            body = json.dumps({'error': 'No telemetry data'}).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _serve_telemetry_history(self):
        """Serve telemetry history"""
        if not self.telemetry_buffer:
            self.send_error(503, 'Telemetry buffer not available')
            return

        # Parse query parameters
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        seconds = int(query.get('seconds', [60])[0])

        history = self.telemetry_buffer.get_history(seconds)
        body = json.dumps(history).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _serve_telemetry_stats(self):
        """Serve telemetry statistics"""
        if not self.telemetry_buffer:
            self.send_error(503, 'Telemetry buffer not available')
            return

        stats = self.telemetry_buffer.get_stats()
        body = json.dumps(stats).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)


class HaLowBridge:
    """
    Main bridge coordinator for Base Pi.

    Translates between serpent_backend (legacy events) and Robot Pi (authenticated protocol).
    """

    def __init__(self):
        # Initialize secure framing
        self.framer = SecureFramer(role="base_pi")
        if not self.framer.is_authenticated():
            logger.critical("NO VALID PSK - Cannot send authenticated commands to Robot Pi")

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

        # Socket.IO client to connect to serpent_backend
        self.sio = socketio.Client(reconnection=True, reconnection_delay=2)
        self.backend_connected = False

        # State tracking
        self.active_camera_id = config.DEFAULT_CAMERA_ID
        self.running = False
        self.last_robot_estop_state: Optional[bool] = None
        self.last_rtt_ms = 0
        self.last_controller_update = 0.0

        # Heartbeat state
        self.last_ping_time = 0
        self.last_ping_seq = 0
        self.heartbeat_thread: Optional[threading.Thread] = None

        # E-STOP debounce state (prevent rapid duplicate/oscillating events)
        self._last_emergency_status_time = 0.0
        self._last_emergency_status_active: Optional[bool] = None
        self._emergency_debounce_s = 0.3  # Ignore events within 300ms

        # Video HTTP server for MJPEG streaming
        self.http_server: Optional[HTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None

        self._setup_socketio_handlers()

        logger.info("HaLowBridge initialized")

    def _setup_socketio_handlers(self):
        """Setup Socket.IO event handlers for serpent_backend"""

        @self.sio.event
        def connect():
            logger.info("Connected to serpent_backend")
            self.backend_connected = True

        @self.sio.event
        def disconnect():
            logger.warning("Disconnected from serpent_backend")
            self.backend_connected = False

        # IMPORTANT: Translate legacy 'emergency_toggle' to proper SET semantics
        @self.sio.on('emergency_toggle')
        def on_emergency_toggle(data):
            """
            Legacy event from backend - ENGAGE E-STOP.

            We translate toggle to ENGAGE only. Clearing requires explicit
            'emergency_stop' with engage=false and confirm_clear.
            """
            logger.warning("Received legacy emergency_toggle - sending ENGAGE")
            self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
                'engage': True,
                'reason': 'operator_toggle'
            })

        # New proper E-STOP event (if backend is updated)
        @self.sio.on('emergency_stop')
        def on_emergency_stop(data):
            """Proper emergency_stop event with SET semantics"""
            engage = data.get('engage', True)
            reason = data.get('reason', 'operator_command')

            if engage:
                logger.warning(f"E-STOP ENGAGE from backend: {reason}")
                self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
                    'engage': True,
                    'reason': reason
                })
            else:
                # Clear request - must include confirmation
                confirm = data.get('confirm_clear', '')
                logger.info(f"E-STOP CLEAR request from backend")
                self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
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
            now = time.time()

            # Debounce: ignore rapid duplicate/oscillating events
            if (now - self._last_emergency_status_time) < self._emergency_debounce_s:
                if self._last_emergency_status_active == active:
                    logger.debug("E-STOP debounce: ignoring duplicate event")
                    return  # Duplicate, ignore
                # Different value in debounce window = oscillation, ignore
                logger.debug("E-STOP debounce: ignoring rapid toggle")
                return

            self._last_emergency_status_time = now
            self._last_emergency_status_active = active

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

        @self.sio.on('clamp_close')
        def on_clamp_close(data):
            logger.info("Clamp close received")
            self.control_forwarder.send_command('clamp_close', data)

        @self.sio.on('clamp_open')
        def on_clamp_open(data):
            logger.info("Clamp open received")
            self.control_forwarder.send_command('clamp_open', data)

        @self.sio.on('height_update')
        def on_height_update(data):
            self.control_forwarder.send_command('height_update', data)

        @self.sio.on('force_update')
        def on_force_update(data):
            self.control_forwarder.send_command('force_update', data)

        @self.sio.on('start_camera')
        def on_start_camera(data):
            camera_id = data.get('camera_id', 0)
            logger.info(f"Start camera: {camera_id}")
            self.active_camera_id = camera_id
            self.control_forwarder.send_command('start_camera', data)

        @self.sio.on('input_event')
        def on_input_event(data):
            self.control_forwarder.send_command('input_event', data)

        @self.sio.on('raw_button_press')
        def on_raw_button_press(data):
            self.control_forwarder.send_command('raw_button_press', data)

    def _on_telemetry_received(self, telemetry: Dict[str, Any]):
        """Callback when telemetry is received from Robot Pi"""
        # Extract E-STOP state for health endpoint
        estop_info = telemetry.get('estop', {})
        self.last_robot_estop_state = estop_info.get('engaged')

        # Compute RTT from pong data if present
        pong = telemetry.get('pong')
        if pong and pong.get('ping_seq') == self.last_ping_seq and self.last_ping_time > 0:
            # RTT = now - original ping timestamp
            now = time.time()
            rtt_ms = int((now - pong.get('ping_ts', now)) * 1000)
            if 0 <= rtt_ms < 10000:  # Sanity check: 0-10 second range
                self.last_rtt_ms = rtt_ms
                logger.debug(f"RTT measured: {rtt_ms}ms (ping_seq={pong.get('ping_seq')})")

        # Include RTT in telemetry for backend
        telemetry['rtt_ms'] = self.last_rtt_ms

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
        if self.backend_connected:
            try:
                self.sio.emit('telemetry', telemetry)
            except Exception as e:
                logger.error(f"Failed to forward telemetry: {e}")

        # Rate-limited controller telemetry (1 Hz)
        now = time.time()
        if should_send_update(self.last_controller_update, config.CONTROLLER_TELEMETRY_RATE_HZ):
            controller_data = format_for_controller(telemetry)
            if self.backend_connected:
                try:
                    self.sio.emit('controller_telemetry', controller_data)
                    logger.debug(f"Sent controller telemetry: status={controller_data.get('status')}, "
                                f"voltage={controller_data.get('voltage')}V, "
                                f"altitude={controller_data.get('altitude')}m, "
                                f"rtt={controller_data.get('rtt_ms')}ms")
                except Exception as e:
                    logger.error(f"Failed to send controller telemetry: {e}")
            else:
                logger.debug("Controller telemetry not sent - backend disconnected")
            self.last_controller_update = now

    def _heartbeat_loop(self):
        """Send periodic pings to Robot Pi for RTT measurement"""
        while self.running:
            try:
                if self.control_forwarder.is_connected():
                    self.last_ping_seq += 1
                    self.last_ping_time = time.time()
                    self.control_forwarder.send_command(MSG_PING, {
                        'ts': self.last_ping_time,
                        'seq': self.last_ping_seq
                    })

                time.sleep(HEARTBEAT_INTERVAL_S)

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                time.sleep(1.0)

    def _start_video_http_server(self):
        """Start the Video HTTP server in a background thread"""
        try:
            # Create handler with video_receiver and telemetry_buffer bound
            handler = partial(VideoHTTPHandler, self.video_receiver, self.telemetry_buffer)

            self.http_server = HTTPServer(('0.0.0.0', config.VIDEO_HTTP_PORT), handler)
            self.http_thread = threading.Thread(
                target=self.http_server.serve_forever,
                daemon=True
            )
            self.http_thread.start()
            logger.info(f"Video HTTP server started on port {config.VIDEO_HTTP_PORT}")
            logger.info(f"  MJPEG stream: http://localhost:{config.VIDEO_HTTP_PORT}/video")
            logger.info(f"  Single frame: http://localhost:{config.VIDEO_HTTP_PORT}/frame")
            logger.info(f"  Health check: http://localhost:{config.VIDEO_HTTP_PORT}/health")
            if config.DASHBOARD_ENABLED:
                logger.info(f"  Dashboard: http://localhost:{config.VIDEO_HTTP_PORT}/dashboard")
        except Exception as e:
            logger.error(f"Failed to start Video HTTP server: {e}")

    def start(self):
        """Start the bridge"""
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
        logger.info(f"Connecting to serpent_backend at {config.BACKEND_SOCKETIO_URL}")
        try:
            self.sio.connect(config.BACKEND_SOCKETIO_URL)
        except Exception as e:
            logger.error(f"Failed to connect to backend: {e}")
            logger.warning("Will retry in background...")

        logger.info("HaLowBridge started successfully")

        # Watchdog loop
        self._watchdog_loop()

    def _watchdog_loop(self):
        """
        Monitor connection health and trigger E-STOP if needed.

        SAFETY: Watchdog can only ENGAGE E-STOP, never clear it.
        """
        last_check = time.time()
        estop_sent_for_timeout = False

        while self.running:
            try:
                time.sleep(1.0)
                now = time.time()

                # Check telemetry timeout - indicates Robot Pi may be unreachable
                last_telemetry = self.telemetry_receiver.get_last_telemetry_time()
                if last_telemetry > 0:
                    telemetry_age = now - last_telemetry
                    if telemetry_age > WATCHDOG_TIMEOUT_S:
                        if not estop_sent_for_timeout:
                            logger.error(f"Telemetry timeout ({telemetry_age:.1f}s), sending E-STOP ENGAGE")
                            self.control_forwarder.send_command(MSG_EMERGENCY_STOP, {
                                'engage': True,
                                'reason': f'base_watchdog_telemetry_timeout_{telemetry_age:.0f}s'
                            })
                            estop_sent_for_timeout = True
                    else:
                        estop_sent_for_timeout = False

                # Log status every 10 seconds
                if now - last_check > 10.0:
                    control_status = "connected" if self.control_forwarder.is_connected() else "disconnected"
                    telemetry_status = "connected" if self.telemetry_receiver.is_connected() else "disconnected"
                    video_status = "N/A"
                    if self.video_receiver:
                        video_status = "connected" if self.video_receiver.is_connected() else "disconnected"

                    status = {
                        "event": "status",
                        "backend": "connected" if self.backend_connected else "disconnected",
                        "control": control_status,
                        "telemetry": telemetry_status,
                        "video": video_status,
                        "robot_estop": self.last_robot_estop_state,
                        "psk_valid": self.framer.is_authenticated()
                    }
                    logger.info(json.dumps(status))
                    last_check = now

            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")

    def stop(self):
        """Stop the bridge"""
        logger.info("Stopping HaLowBridge...")
        self.running = False

        # Disconnect from backend
        if self.backend_connected:
            try:
                self.sio.disconnect()
            except:
                pass

        # Stop storage
        if self.telemetry_storage:
            self.telemetry_storage.stop()

        if self.video_recorder:
            self.video_recorder.stop_recording()

        # Stop Video HTTP server
        if self.http_server:
            try:
                self.http_server.shutdown()
                logger.info("Video HTTP server stopped")
            except Exception as e:
                logger.error(f"Error stopping HTTP server: {e}")

        # Stop components
        self.control_forwarder.stop()
        self.telemetry_receiver.stop()

        if self.video_receiver:
            self.video_receiver.stop()

        logger.info("HaLowBridge stopped")

    def get_health(self) -> dict:
        """Get health status for monitoring"""
        return {
            'status': 'ok' if self._is_healthy() else 'degraded',
            'backend_connected': self.backend_connected,
            'control_connected': self.control_forwarder.is_connected(),
            'telemetry_connected': self.telemetry_receiver.is_connected(),
            'video_connected': self.video_receiver.is_connected() if self.video_receiver else None,
            'robot_estop_engaged': self.last_robot_estop_state,
            'last_telemetry_age_s': time.time() - self.telemetry_receiver.get_last_telemetry_time()
                if self.telemetry_receiver.get_last_telemetry_time() > 0 else None,
            'psk_valid': self.framer.is_authenticated(),
            'last_rtt_ms': self.last_rtt_ms
        }

    def _is_healthy(self) -> bool:
        """Check if system is healthy"""
        if not self.control_forwarder.is_connected():
            return False
        if not self.telemetry_receiver.is_connected():
            return False
        last_telem = self.telemetry_receiver.get_last_telemetry_time()
        if last_telem > 0 and time.time() - last_telem > WATCHDOG_TIMEOUT_S:
            return False
        return True

    def get_video_frame(self) -> Optional[bytes]:
        """Get current video frame"""
        if self.video_receiver:
            return self.video_receiver.get_frame()
        return None

    def get_video_stream(self):
        """Get video frame generator for MJPEG streaming"""
        if self.video_receiver:
            return self.video_receiver.get_frame_generator()
        return None


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutdown signal received")
    if bridge:
        bridge.stop()
    sys.exit(0)


# Global bridge instance
bridge: Optional[HaLowBridge] = None


def main():
    """Main entry point"""
    global bridge

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("SERPENT BASE PI BRIDGE STARTING")
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

"""
Video HTTP Server for Base Pi

Serves MJPEG video streaming and telemetry API endpoints.

Endpoints:
- /video, /video.mjpeg: MJPEG stream
- /frame, /frame.jpg: Single JPEG frame
- /health: Health status JSON
- /dashboard, /: Dashboard HTML
- /static/*: Static files (CSS, JS)
- /api/telemetry/latest: Latest telemetry JSON
- /api/telemetry/history: Historical telemetry JSON
- /api/telemetry/stats: Telemetry statistics JSON
"""

import logging
import time
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from functools import partial
from typing import Optional
from urllib.parse import urlparse, parse_qs

from base_pi.telemetry_metrics import add_derived_metrics

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
        """Suppress default HTTP logging (too verbose)."""
        pass

    def do_GET(self):
        """Handle GET requests."""
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
        """Serve MJPEG stream (multipart/x-mixed-replace)."""
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
        """Serve a single JPEG frame."""
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
        """Serve health status."""
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
        """Serve a static file."""
        try:
            # Get the base_pi directory
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        """Serve static files (CSS, JS, etc.)."""
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
        """Serve latest telemetry data."""
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
        """Serve telemetry history."""
        if not self.telemetry_buffer:
            self.send_error(503, 'Telemetry buffer not available')
            return

        # Parse query parameters
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
        """Serve telemetry statistics."""
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


class VideoHTTPServer:
    """
    Video HTTP server manager.

    Manages HTTP server lifecycle for video streaming and API endpoints.
    """

    def __init__(self, port: int, video_receiver, telemetry_buffer):
        """
        Initialize video HTTP server.

        Args:
            port: HTTP server port
            video_receiver: VideoReceiver instance
            telemetry_buffer: TelemetryBuffer instance
        """
        self.port = port
        self.video_receiver = video_receiver
        self.telemetry_buffer = telemetry_buffer
        self.server: Optional[HTTPServer] = None

        logger.info(f"VideoHTTPServer initialized (port={port})")

    def start(self):
        """Start the HTTP server."""
        try:
            # Create handler with video_receiver and telemetry_buffer bound
            handler = partial(VideoHTTPHandler, self.video_receiver, self.telemetry_buffer)

            self.server = HTTPServer(('0.0.0.0', self.port), handler)
            logger.info(f"Video HTTP server started on port {self.port}")
            logger.info(f"  MJPEG stream: http://localhost:{self.port}/video")
            logger.info(f"  Single frame: http://localhost:{self.port}/frame")
            logger.info(f"  Health check: http://localhost:{self.port}/health")
            logger.info(f"  Dashboard: http://localhost:{self.port}/dashboard")
        except Exception as e:
            logger.error(f"Failed to start Video HTTP server: {e}")
            raise

    def serve_forever(self):
        """Run the server forever (blocking)."""
        if self.server:
            self.server.serve_forever()

    def shutdown(self):
        """Shutdown the HTTP server."""
        if self.server:
            try:
                self.server.shutdown()
                logger.info("Video HTTP server stopped")
            except Exception as e:
                logger.error(f"Error stopping HTTP server: {e}")

"""
Dashboard Web Server

Flask application with REST API and WebSocket real-time updates.
"""

import logging
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import threading
import time

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dashboard import config
from dashboard import status_aggregator
from dashboard import log_parser
from dashboard import diagnostics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'serpent-dashboard-secret-key'
CORS(app)

# Create SocketIO instance
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Background thread for status updates
status_update_thread = None
status_update_running = False


def status_update_worker():
    """Background worker that pushes status updates via WebSocket"""
    global status_update_running

    logger.info("Status update worker started")

    while status_update_running:
        try:
            # Get current status
            status = status_aggregator.get_aggregated_status()

            # Emit to all connected clients
            socketio.emit('status_update', status, namespace='/ws/status')

            # Sleep until next update
            time.sleep(config.STATUS_UPDATE_INTERVAL)

        except Exception as e:
            logger.error(f"Status update worker error: {e}")
            time.sleep(1)

    logger.info("Status update worker stopped")


def start_status_updates():
    """Start the background status update thread"""
    global status_update_thread, status_update_running

    if status_update_thread is None or not status_update_thread.is_alive():
        status_update_running = True
        status_update_thread = threading.Thread(target=status_update_worker, daemon=True)
        status_update_thread.start()
        logger.info("Status update thread started")


def stop_status_updates():
    """Stop the background status update thread"""
    global status_update_running
    status_update_running = False
    logger.info("Status update thread stopping")


# ============================================================================
# Web Page Routes
# ============================================================================

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html',
                          role=config.DASHBOARD_ROLE,
                          video_url=config.VIDEO_STREAM_URL)


@app.route('/logs')
def logs_page():
    """Log viewer page"""
    return render_template('logs.html', role=config.DASHBOARD_ROLE)


@app.route('/diagnostics')
def diagnostics_page():
    """Diagnostics page"""
    return render_template('diagnostics.html',
                          role=config.DASHBOARD_ROLE,
                          service_control_enabled=config.ENABLE_SERVICE_CONTROL)


# ============================================================================
# API Routes
# ============================================================================

@app.route('/api/status')
def api_status():
    """Get current aggregated system status"""
    try:
        status = status_aggregator.get_aggregated_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs')
def api_logs():
    """Get filtered logs from systemd journal"""
    try:
        # Get query parameters
        service = request.args.get('service', 'robot')
        lines = min(int(request.args.get('lines', 100)), config.MAX_LOG_LINES)
        level = request.args.get('level')  # Optional filter

        # Determine service name
        if service == 'robot':
            service_name = config.ROBOT_BRIDGE_SERVICE
        elif service == 'base':
            service_name = config.BASE_BRIDGE_SERVICE
        elif service == 'backend':
            service_name = config.BACKEND_SERVICE
        else:
            return jsonify({'error': 'Invalid service name'}), 400

        # Parse logs
        logs = log_parser.parse_recent_logs(service_name, lines=lines, level=level)

        return jsonify({
            'service': service,
            'lines': len(logs),
            'logs': logs
        })

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/network')
def api_diagnostics_network():
    """Run network connectivity tests"""
    try:
        # Test connection to robot and base Pi
        robot_result = diagnostics.test_network_connectivity(
            config.ROBOT_PI_IP,
            [config.CONTROL_PORT, config.VIDEO_PORT, config.TELEMETRY_PORT]
        )

        base_result = diagnostics.test_network_connectivity(
            config.BASE_PI_IP,
            [config.BACKEND_VIDEO_PORT]
        )

        return jsonify({
            'robot_pi': robot_result,
            'base_pi': base_result
        })

    except Exception as e:
        logger.error(f"Network diagnostics failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/cameras')
def api_diagnostics_cameras():
    """Scan for available cameras"""
    try:
        cameras = diagnostics.scan_cameras()
        return jsonify({'cameras': cameras})
    except Exception as e:
        logger.error(f"Camera scan failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/services')
def api_diagnostics_services():
    """Check status of all services"""
    try:
        services = {}

        # Check robot bridge
        services['robot_bridge'] = diagnostics.check_service_status(
            config.ROBOT_BRIDGE_SERVICE
        )

        # Check base bridge
        services['base_bridge'] = diagnostics.check_service_status(
            config.BASE_BRIDGE_SERVICE
        )

        # Check backend
        services['backend'] = diagnostics.check_service_status(
            config.BACKEND_SERVICE
        )

        return jsonify({'services': services})

    except Exception as e:
        logger.error(f"Service check failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/resources')
def api_diagnostics_resources():
    """Get system resource usage"""
    try:
        resources = diagnostics.get_system_resources()
        return jsonify(resources)
    except Exception as e:
        logger.error(f"Resource check failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/issues')
def api_diagnostics_issues():
    """Detect issues and get suggestions"""
    try:
        status = status_aggregator.get_aggregated_status()
        issues = diagnostics.detect_issues(status)
        return jsonify({'issues': issues})
    except Exception as e:
        logger.error(f"Issue detection failed: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics/restart_service', methods=['POST'])
def api_restart_service():
    """Restart a systemd service"""
    try:
        data = request.get_json()
        service_name = data.get('service')

        if not service_name:
            return jsonify({'error': 'Service name required'}), 400

        success, message = diagnostics.restart_service(service_name)

        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': message}), 500

    except Exception as e:
        logger.error(f"Service restart failed: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# WebSocket Events
# ============================================================================

@socketio.on('connect', namespace='/ws/status')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to status updates'})


@socketio.on('disconnect', namespace='/ws/status')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on('request_status', namespace='/ws/status')
def handle_status_request():
    """Handle manual status request"""
    try:
        status = status_aggregator.get_aggregated_status()
        emit('status_update', status)
    except Exception as e:
        logger.error(f"Failed to send status: {e}")
        emit('error', {'message': str(e)})


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    logger.info(f"Starting SERPENT Dashboard ({config.DASHBOARD_ROLE}) on port {config.DASHBOARD_PORT}")
    logger.info(f"Direct inspection: {config.ENABLE_DIRECT_INSPECTION}")
    logger.info(f"Service control: {config.ENABLE_SERVICE_CONTROL}")

    # Start background status updates
    start_status_updates()

    try:
        # Run Flask-SocketIO server
        socketio.run(
            app,
            host='0.0.0.0',
            port=config.DASHBOARD_PORT,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )
    finally:
        stop_status_updates()

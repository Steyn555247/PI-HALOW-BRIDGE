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

# Import actuator controller for direct control (when enabled)
actuator_controller = None
if config.ENABLE_DIRECT_INSPECTION and config.DASHBOARD_ROLE == 'robot_pi':
    try:
        sys.path.insert(0, str(project_root / 'robot_pi'))
        import config as robot_config
        from actuator_controller import ActuatorController

        # Create a local actuator controller instance for dashboard use
        actuator_controller = ActuatorController(
            motoron_addresses=robot_config.MOTORON_ADDRESSES,
            servo_gpio=robot_config.SERVO_GPIO_PIN,
            servo_freq=robot_config.SERVO_FREQ,
            active_motors=robot_config.ACTIVE_MOTORS
        )
        actuator_controller.start()
        logger.info("Direct robot control enabled - actuator controller initialized")
    except Exception as e:
        logger.warning(f"Could not initialize actuator controller for direct control: {e}")
        actuator_controller = None

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
    """Check status of services relevant to this Pi's role"""
    try:
        services = {}

        for svc in config.ROLE_SERVICES.get(config.DASHBOARD_ROLE, []):
            # Derive a short key from the service name
            key = svc.replace('serpent-', '').replace('.service', '').replace('-', '_')
            services[key] = diagnostics.check_service_status(svc)

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


@app.route('/api/motor/set', methods=['POST'])
def api_motor_set():
    """Set motor speed (direct control - robot Pi only)"""
    try:
        # Check if running on robot Pi with direct access
        if config.DASHBOARD_ROLE != 'robot_pi':
            return jsonify({'error': 'Motor control only available on robot Pi'}), 403

        # Get parameters
        data = request.get_json()
        motor_id = data.get('motor_id')
        speed = data.get('speed')

        if motor_id is None or speed is None:
            return jsonify({'error': 'motor_id and speed required'}), 400

        # Validate parameters
        try:
            motor_id = int(motor_id)
            speed = int(speed)
        except (ValueError, TypeError):
            return jsonify({'error': 'motor_id and speed must be integers'}), 400

        if motor_id < 0 or motor_id > 7:
            return jsonify({'error': 'motor_id must be 0-7'}), 400

        if speed < -800 or speed > 800:
            return jsonify({'error': 'speed must be -800 to +800'}), 400

        # Check if actuator controller is available
        if actuator_controller is None:
            return jsonify({'error': 'Actuator controller not initialized'}), 503

        # Try to set motor speed
        success = actuator_controller.set_motor_speed(motor_id, speed)

        # Get current e-stop status
        estop_info = actuator_controller.get_estop_info()

        return jsonify({
            'success': success,
            'motor_id': motor_id,
            'speed': speed,
            'estop_engaged': estop_info['engaged'],
            'estop_reason': estop_info['reason'],
            'message': 'Motor command sent' if success else 'E-STOP engaged - motor blocked'
        })

    except Exception as e:
        logger.error(f"Motor control failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/estop/clear', methods=['POST'])
def api_estop_clear():
    """Clear E-STOP (local manual override - robot Pi only)"""
    try:
        # Check if running on robot Pi with direct access
        if config.DASHBOARD_ROLE != 'robot_pi':
            return jsonify({'error': 'E-STOP control only available on robot Pi'}), 403

        # Check if actuator controller is available
        if actuator_controller is None:
            return jsonify({'error': 'Actuator controller not initialized'}), 503

        # Clear e-stop using local method (bypasses control checks)
        success = actuator_controller.clear_estop_local()

        # Get updated e-stop status
        estop_info = actuator_controller.get_estop_info()

        return jsonify({
            'success': success,
            'estop_engaged': estop_info['engaged'],
            'estop_reason': estop_info['reason'],
            'message': 'E-STOP cleared successfully' if success else 'E-STOP already cleared'
        })

    except Exception as e:
        logger.error(f"E-STOP clear failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/estop/engage', methods=['POST'])
def api_estop_engage():
    """Engage E-STOP (emergency stop - robot Pi only)"""
    try:
        # Check if running on robot Pi with direct access
        if config.DASHBOARD_ROLE != 'robot_pi':
            return jsonify({'error': 'E-STOP control only available on robot Pi'}), 403

        # Check if actuator controller is available
        if actuator_controller is None:
            return jsonify({'error': 'Actuator controller not initialized'}), 503

        # Engage e-stop
        actuator_controller.engage_estop("operator_command", "Engaged from dashboard")

        # Get updated e-stop status
        estop_info = actuator_controller.get_estop_info()

        return jsonify({
            'success': True,
            'estop_engaged': estop_info['engaged'],
            'estop_reason': estop_info['reason'],
            'message': 'E-STOP engaged'
        })

    except Exception as e:
        logger.error(f"E-STOP engage failed: {e}", exc_info=True)
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

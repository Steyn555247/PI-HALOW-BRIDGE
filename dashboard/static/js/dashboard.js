// SERPENT Dashboard JavaScript

// WebSocket connection
let socket = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;

// Connect to WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/status`;

    socket = io(wsUrl, {
        transports: ['websocket', 'polling']
    });

    socket.on('connect', function() {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
    });

    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, 2000);
        }
    });

    socket.on('status_update', function(data) {
        updateDashboard(data);
    });

    socket.on('error', function(error) {
        console.error('WebSocket error:', error);
    });
}

// Update dashboard with new status data
function updateDashboard(status) {
    // Update connection status
    updateConnections(status.connections);

    // Update E-STOP status
    updateEstop(status.estop);

    // Update sensors
    updateSensors(status.sensors);

    // Update actuators (motors/servo)
    updateActuators(status.actuators);

    // Update video stats
    updateVideoStats(status.video);

    // Update health
    updateHealth(status.health, status.timestamp);

    // Update issues
    updateIssues(status);
}

// Update connection indicators
function updateConnections(connections) {
    if (!connections) return;

    // Control
    if (connections.control !== undefined) {
        updateStatusIndicator('status-control', connections.control);

        if (connections.control_age_ms !== undefined) {
            const age = connections.control_age_ms;
            document.getElementById('status-control-age').textContent =
                age > 0 ? `(${age}ms old)` : '';
        }
    }

    // Telemetry
    if (connections.telemetry !== undefined) {
        updateStatusIndicator('status-telemetry', connections.telemetry);
    }

    // Video
    if (connections.video !== undefined) {
        updateStatusIndicator('status-video', connections.video);
    }

    // Backend
    if (connections.backend !== undefined) {
        updateStatusIndicator('status-backend', connections.backend);
    }
}

// Update status indicator element
function updateStatusIndicator(elementId, status) {
    const element = document.getElementById(elementId);
    if (!element) return;

    // Remove existing status classes
    element.classList.remove('status-connected', 'status-disconnected', 'status-unknown', 'status-warning');

    // Add appropriate class and text
    if (status === 'connected' || status === true) {
        element.classList.add('status-connected');
        element.textContent = 'Connected';
    } else if (status === 'disconnected' || status === false) {
        element.classList.add('status-disconnected');
        element.textContent = 'Disconnected';
    } else {
        element.classList.add('status-unknown');
        element.textContent = 'Unknown';
    }
}

// Update E-STOP status
function updateEstop(estop) {
    if (!estop) return;

    const card = document.getElementById('estop-card');
    const engagedBadge = document.getElementById('estop-engaged');
    const reasonSpan = document.getElementById('estop-reason');
    const ageSpan = document.getElementById('estop-age');

    if (estop.engaged) {
        card.classList.remove('estop-cleared');
        card.classList.add('estop-engaged');
        engagedBadge.className = 'badge bg-danger';
        engagedBadge.textContent = 'ENGAGED';

        reasonSpan.textContent = `Reason: ${estop.reason || 'unknown'}`;

        if (estop.age_s !== undefined) {
            ageSpan.textContent = `(${estop.age_s.toFixed(1)}s ago)`;
        }
    } else {
        card.classList.remove('estop-engaged');
        card.classList.add('estop-cleared');
        engagedBadge.className = 'badge bg-success';
        engagedBadge.textContent = 'Cleared';

        reasonSpan.textContent = '';
        ageSpan.textContent = '';
    }
}

// Update sensor displays
function updateSensors(sensors) {
    if (!sensors) return;

    // IMU
    if (sensors.imu) {
        const imu = sensors.imu;
        if (imu.accel) {
            setText('imu-ax', imu.accel.x?.toFixed(2));
            setText('imu-ay', imu.accel.y?.toFixed(2));
            setText('imu-az', imu.accel.z?.toFixed(2));
        }
        if (imu.gyro) {
            setText('imu-gx', imu.gyro.x?.toFixed(2));
            setText('imu-gy', imu.gyro.y?.toFixed(2));
            setText('imu-gz', imu.gyro.z?.toFixed(2));
        }
        if (imu.quaternion) {
            setText('imu-qw', imu.quaternion.w?.toFixed(3));
            setText('imu-qx', imu.quaternion.x?.toFixed(3));
            setText('imu-qy', imu.quaternion.y?.toFixed(3));
            setText('imu-qz', imu.quaternion.z?.toFixed(3));
        }
    }

    // Barometer
    if (sensors.barometer) {
        const baro = sensors.barometer;
        setText('baro-pressure', baro.pressure?.toFixed(1));
        setText('baro-temp', baro.temperature?.toFixed(1));
        setText('baro-alt', baro.altitude?.toFixed(1));
    }
}

// Update actuator displays (motors, servo)
function updateActuators(actuators) {
    if (!actuators) return;

    // Motor currents
    if (actuators.motor_currents) {
        const maxCurrent = 3.0; // Assume 3A max for visualization
        for (let i = 0; i < 8; i++) {
            const current = actuators.motor_currents[i];
            if (current !== undefined) {
                const percent = Math.min((Math.abs(current) / maxCurrent) * 100, 100);
                const bar = document.getElementById(`motor-${i+1}`);
                const val = document.getElementById(`motor-${i+1}-val`);

                if (bar) {
                    bar.style.width = `${percent}%`;

                    // Color based on current level
                    if (percent > 80) {
                        bar.className = 'progress-bar bg-danger';
                    } else if (percent > 50) {
                        bar.className = 'progress-bar bg-warning';
                    } else {
                        bar.className = 'progress-bar bg-success';
                    }
                }

                if (val) {
                    val.textContent = `${current.toFixed(2)} A`;
                }
            }
        }
    }

    // Servo position
    if (actuators.servo_position !== undefined) {
        const position = actuators.servo_position;
        const percent = position * 100;

        const bar = document.getElementById('servo-position');
        const val = document.getElementById('servo-val');

        if (bar) {
            bar.style.width = `${percent}%`;
        }
        if (val) {
            val.textContent = position.toFixed(2);
        }
    }
}

// Update video statistics
function updateVideoStats(video) {
    if (!video) return;

    setText('video-frames-sent', video.frames_sent);
    setText('video-frames-dropped', video.frames_dropped);

    if (video.drop_rate !== undefined) {
        const dropRatePercent = (video.drop_rate * 100).toFixed(1);
        const elem = document.getElementById('video-drop-rate');
        if (elem) {
            elem.textContent = dropRatePercent;

            // Color-code based on drop rate
            if (video.drop_rate > 0.1) {
                elem.style.color = 'red';
                elem.style.fontWeight = 'bold';
            } else if (video.drop_rate > 0.05) {
                elem.style.color = 'orange';
            } else {
                elem.style.color = 'inherit';
            }
        }
    }

    setText('video-errors', video.camera_errors);
    setText('video-active-camera', video.active_camera);
}

// Update health indicators
function updateHealth(health, timestamp) {
    if (!health) return;

    setText('health-uptime', health.uptime_s);
    setText('health-psk', health.psk_valid ? 'Yes' : 'No');

    if (timestamp) {
        const date = new Date(timestamp * 1000);
        setText('health-timestamp', date.toLocaleTimeString());
    }
}

// Update issues display
function updateIssues(status) {
    // Fetch issues from API
    fetch('/api/diagnostics/issues')
        .then(response => response.json())
        .then(data => {
            displayIssues(data.issues);
        })
        .catch(error => {
            console.error('Failed to fetch issues:', error);
        });
}

// Display issues
function displayIssues(issues) {
    const container = document.getElementById('issues-container');
    if (!container) return;

    if (!issues || issues.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = '<h5 class="mt-3">Detected Issues</h5>';

    for (const issue of issues) {
        const severityClass = `issue-${issue.severity}`;
        const alertClass = issue.severity === 'critical' ? 'alert-danger' :
                          issue.severity === 'warning' ? 'alert-warning' : 'alert-info';

        html += `<div class="alert ${alertClass} issue-alert ${severityClass}">`;
        html += `<strong>${issue.title}</strong><br>`;
        html += `<small>${issue.description}</small>`;
        html += `<div class="issue-suggestion"><em>💡 ${issue.suggestion}</em></div>`;
        html += '</div>';
    }

    container.innerHTML = html;
}

// Helper: Set text content safely
function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value !== undefined && value !== null ? value : '--';
    }
}

// ============================================================================
// Motor Control Functions
// ============================================================================

// Set motor speed
function setMotor(motorId, speed) {
    fetch('/api/motor/set', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            motor_id: motorId,
            speed: speed
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`Motor ${motorId} set to speed ${speed}`);
        } else {
            console.warn(`Motor command failed: ${data.message}`);
            if (data.estop_engaged) {
                alert(`Motor command blocked: E-STOP is engaged (${data.estop_reason})`);
            }
        }
    })
    .catch(error => {
        console.error('Motor control error:', error);
        alert('Failed to send motor command: ' + error);
    });
}

// Clear E-STOP
function clearEstop() {
    if (!confirm('Are you sure you want to clear the E-STOP?\n\nEnsure all safety checks are complete before proceeding.')) {
        return;
    }

    fetch('/api/estop/clear', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('E-STOP cleared successfully');
            alert('E-STOP cleared. Motors are now enabled.');
        } else {
            console.warn('E-STOP clear failed:', data.message);
            alert('Failed to clear E-STOP: ' + data.message);
        }
    })
    .catch(error => {
        console.error('E-STOP clear error:', error);
        alert('Failed to clear E-STOP: ' + error);
    });
}

// Engage E-STOP (Emergency Stop)
function engageEstop() {
    fetch('/api/estop/engage', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('E-STOP engaged successfully');
            alert('E-STOP ENGAGED. All motors stopped.');
        } else {
            console.warn('E-STOP engage failed:', data.message);
        }
    })
    .catch(error => {
        console.error('E-STOP engage error:', error);
        alert('Failed to engage E-STOP: ' + error);
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard initializing...');

    // Connect WebSocket for real-time updates
    connectWebSocket();

    // Also fetch initial status via REST API
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            updateDashboard(data);
        })
        .catch(error => {
            console.error('Failed to fetch initial status:', error);
        });
});

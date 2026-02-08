// SERPENT Connectivity Dashboard JavaScript

// Dashboard role - check if defined globally, otherwise default to 'base_pi'
// (This makes the dashboard work even if the template doesn't set DASHBOARD_ROLE)
if (typeof DASHBOARD_ROLE === 'undefined') {
    window.DASHBOARD_ROLE = 'base_pi';
}

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

    socket.on('input_event', function(data) {
        updateControllerInput(data);
    });

    socket.on('error', function(error) {
        console.error('WebSocket error:', error);
    });
}

// Update dashboard with new status data
function updateDashboard(status) {
    // Update data flow overview badges
    updateDataFlowOverview(status.connections);

    // Update channel detail cards
    updateChannelDetails(status.data_flow, status.connections);

    // Update overall status banner
    updateOverallStatus(status.connections);

    // Update E-STOP status (UNCHANGED)
    updateEstop(status.estop);

    // Update health sidebar
    updateHealth(status.health, status.timestamp);

    // Update sensors (collapsed section)
    updateSensors(status.sensors);

    // Update motor currents
    updateMotorCurrents(status.actuators);

    // Update issues
    updateIssues(status);
}

// ============================================================================
// Badge / State Helpers
// ============================================================================

/**
 * Update a state badge element with consistent green/red/gray styling.
 * @param {string} badgeId - Element ID of the badge span
 * @param {string} state  - 'connected' | 'disconnected' | 'unknown'
 */
function updateBadge(badgeId, state) {
    const el = document.getElementById(badgeId);
    if (!el) return;

    el.classList.remove('connected', 'disconnected', 'unknown');

    if (state === 'connected') {
        el.classList.add('connected');
        el.textContent = 'connected';
    } else if (state === 'disconnected') {
        el.classList.add('disconnected');
        el.textContent = 'disconnected';
    } else {
        el.classList.add('unknown');
        el.textContent = 'unknown';
    }
}

/**
 * Update a channel card's left-border colour class.
 */
function updateCardColor(cardId, state) {
    const el = document.getElementById(cardId);
    if (!el) return;

    el.classList.remove('ok', 'error', 'unknown');

    if (state === 'connected') {
        el.classList.add('ok');
    } else if (state === 'disconnected') {
        el.classList.add('error');
    } else {
        el.classList.add('unknown');
    }
}

/**
 * Update a data-flow-channel pill in the overview diagram.
 */
function updateFlowPill(pillId, connected) {
    const el = document.getElementById(pillId);
    if (!el) return;

    el.classList.remove('connected', 'disconnected', 'unknown');

    if (connected === true) {
        el.classList.add('connected');
    } else if (connected === false) {
        el.classList.add('disconnected');
    } else {
        el.classList.add('unknown');
    }
}

// ============================================================================
// Data Flow Overview
// ============================================================================

function updateDataFlowOverview(connections) {
    if (!connections) return;

    const controlState = (connections.control || {}).state;
    const telemetryState = (connections.telemetry || {}).state;
    const videoState = (connections.video || {}).state;

    updateFlowPill('df-control', controlState === 'connected' ? true : controlState === 'disconnected' ? false : null);
    updateFlowPill('df-telemetry', telemetryState === 'connected' ? true : telemetryState === 'disconnected' ? false : null);
    updateFlowPill('df-video', videoState === 'connected' ? true : videoState === 'disconnected' ? false : null);
}

// ============================================================================
// Channel Detail Cards
// ============================================================================

function updateChannelDetails(dataFlow, connections) {
    if (!connections) return;
    dataFlow = dataFlow || {};

    // --- Control ---
    const controlConn = connections.control || {};
    const controlState = controlConn.state || 'unknown';
    updateCardColor('card-control', controlState);
    updateBadge('badge-control', controlState);
    setText('ctrl-state', controlState);

    // Robot Pi extras
    if (DASHBOARD_ROLE === 'robot_pi') {
        const ctrlFlow = dataFlow.control_rx || {};
        setText('ctrl-established', ctrlFlow.established ? 'Yes' : 'No');
        setText('ctrl-age', ctrlFlow.age_ms !== undefined ? ctrlFlow.age_ms + ' ms' : '--');
        setText('ctrl-seq', ctrlFlow.seq !== undefined ? ctrlFlow.seq : '--');
    }

    // --- Telemetry ---
    const telemConn = connections.telemetry || {};
    const telemState = telemConn.state || 'unknown';
    updateCardColor('card-telemetry', telemState);
    updateBadge('badge-telemetry', telemState);
    setText('telem-state', telemState);

    // Base Pi extras
    if (DASHBOARD_ROLE === 'base_pi') {
        const telemFlow = dataFlow.telemetry_rx || {};
        setText('telem-rtt', telemFlow.rtt_ms !== undefined ? telemFlow.rtt_ms + ' ms' : '--');
    }

    // --- Video ---
    const videoConn = connections.video || {};
    const videoState = videoConn.state || 'unknown';
    updateCardColor('card-video', videoState);
    updateBadge('badge-video', videoState);
    setText('video-state', videoState);

    // Robot Pi extras
    if (DASHBOARD_ROLE === 'robot_pi') {
        const videoFlow = dataFlow.video_tx || {};
        setText('video-frames-sent', videoFlow.frames_sent !== undefined ? videoFlow.frames_sent : '--');
        setText('video-frames-dropped', videoFlow.frames_dropped !== undefined ? videoFlow.frames_dropped : '--');
        if (videoFlow.drop_rate !== undefined) {
            const pct = (videoFlow.drop_rate * 100).toFixed(1) + '%';
            const el = document.getElementById('video-drop-rate');
            if (el) {
                el.textContent = pct;
                el.style.color = videoFlow.drop_rate > 0.1 ? 'red' : videoFlow.drop_rate > 0.05 ? 'orange' : 'inherit';
            }
        } else {
            setText('video-drop-rate', '--');
        }
    }
}

// ============================================================================
// Overall Status Banner
// ============================================================================

function updateOverallStatus(connections) {
    const el = document.getElementById('overall-status');
    if (!el || !connections) return;

    const states = ['control', 'telemetry', 'video']
        .map(ch => (connections[ch] || {}).state || 'unknown');

    const connected = states.filter(s => s === 'connected').length;
    const disconnected = states.filter(s => s === 'disconnected').length;

    el.classList.remove('healthy', 'degraded', 'down');

    if (connected === states.length) {
        el.classList.add('healthy');
        el.textContent = 'All channels connected';
    } else if (disconnected === states.length) {
        el.classList.add('down');
        el.textContent = 'All channels disconnected';
    } else {
        el.classList.add('degraded');
        el.textContent = `${connected}/${states.length} channels connected`;
    }
}

// ============================================================================
// E-STOP (UNCHANGED)
// ============================================================================

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

// ============================================================================
// Health Sidebar
// ============================================================================

function updateHealth(health, timestamp) {
    if (!health) return;

    setText('health-psk', health.psk_valid ? 'Yes' : 'No');

    if (health.uptime_s !== undefined) {
        const s = health.uptime_s;
        if (s >= 3600) {
            setText('health-uptime', Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm');
        } else if (s >= 60) {
            setText('health-uptime', Math.floor(s / 60) + 'm ' + (s % 60) + 's');
        } else {
            setText('health-uptime', s + 's');
        }
    }

    if (timestamp) {
        const date = new Date(timestamp * 1000);
        setText('health-timestamp', date.toLocaleTimeString());
    }

    if (health.watchdog_disabled !== undefined) {
        const el = document.getElementById('health-watchdog');
        if (el) {
            el.textContent = health.watchdog_disabled ? 'DISABLED' : 'Active';
            el.style.color = health.watchdog_disabled ? 'orange' : 'inherit';
        }
    }
}

// ============================================================================
// Sensors (collapsed section - same data)
// ============================================================================

function updateSensors(sensors) {
    if (!sensors) return;

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

    if (sensors.barometer) {
        const baro = sensors.barometer;
        setText('baro-pressure', baro.pressure?.toFixed(1));
        setText('baro-temp', baro.temperature?.toFixed(1));
        setText('baro-alt', baro.altitude?.toFixed(1));
    }
}

// ============================================================================
// Motor Currents
// ============================================================================

function updateMotorCurrents(actuators) {
    if (!actuators || !actuators.motor_currents) {
        // No motor current data - show dashes
        for (let i = 0; i < 8; i++) {
            setText(`motor-${i}-current`, '-- A');
        }
        setText('motor-total-current', '-- A');
        return;
    }

    const currents = actuators.motor_currents;
    let total = 0.0;

    // Update individual motor currents
    for (let i = 0; i < 8; i++) {
        const current = currents[i] || 0.0;
        total += current;

        // Color code based on current level
        const element = document.getElementById(`motor-${i}-current`);
        if (element) {
            element.textContent = `${current.toFixed(3)} A`;

            // Update badge color based on current level
            element.classList.remove('bg-secondary', 'bg-success', 'bg-warning', 'bg-danger');
            if (current < 0.01) {
                element.classList.add('bg-secondary');  // Off/idle
            } else if (current < 0.5) {
                element.classList.add('bg-success');   // Low current
            } else if (current < 1.5) {
                element.classList.add('bg-warning');   // Medium current
            } else {
                element.classList.add('bg-danger');    // High current
            }
        }
    }

    // Update total current
    const totalElement = document.getElementById('motor-total-current');
    if (totalElement) {
        totalElement.textContent = `${total.toFixed(3)} A`;
    }
}

// ============================================================================
// Issues
// ============================================================================

function updateIssues(status) {
    fetch('/api/diagnostics/issues')
        .then(response => response.json())
        .then(data => {
            displayIssues(data.issues);
        })
        .catch(error => {
            console.error('Failed to fetch issues:', error);
        });
}

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
        html += `<div class="issue-suggestion"><em>${issue.suggestion}</em></div>`;
        html += '</div>';
    }

    container.innerHTML = html;
}

// ============================================================================
// Controller Input Display
// ============================================================================

// Button state tracking for auto-release
const buttonStates = {};
const buttonReleaseTimers = {};

function updateControllerInput(data) {
    if (!data || data.type !== 'button') return;

    const index = data.index;
    const pressed = data.value === 1;

    const buttonEl = document.getElementById(`btn-${index}`);
    if (!buttonEl) return;

    // Clear any existing release timer
    if (buttonReleaseTimers[index]) {
        clearTimeout(buttonReleaseTimers[index]);
        delete buttonReleaseTimers[index];
    }

    if (pressed) {
        // Button pressed - highlight green
        buttonEl.classList.add('pressed');
        buttonStates[index] = true;

        // Auto-release after 300ms if no release event received
        buttonReleaseTimers[index] = setTimeout(() => {
            buttonEl.classList.remove('pressed');
            buttonStates[index] = false;
            delete buttonReleaseTimers[index];
        }, 300);
    } else {
        // Button released - remove highlight
        buttonEl.classList.remove('pressed');
        buttonStates[index] = false;
    }
}

// ============================================================================
// Helpers
// ============================================================================

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value !== undefined && value !== null ? value : '--';
    }
}

// ============================================================================
// Motor Control Functions (UNCHANGED)
// ============================================================================

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

// ============================================================================
// Initialize
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Connectivity Dashboard initializing...');

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

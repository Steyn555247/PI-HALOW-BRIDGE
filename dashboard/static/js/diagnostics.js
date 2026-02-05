// SERPENT Diagnostics JavaScript

// Check for issues
document.getElementById('check-issues-btn').addEventListener('click', function() {
    const button = this;
    const display = document.getElementById('issues-display');

    button.disabled = true;
    button.textContent = 'Checking...';
    display.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Detecting issues...';

    fetch('/api/diagnostics/issues')
        .then(response => response.json())
        .then(data => {
            displayIssues(data.issues);
        })
        .catch(error => {
            display.innerHTML = `<div class="text-danger">Failed to check issues: ${error.message}</div>`;
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Check for Issues';
        });
});

function displayIssues(issues) {
    const display = document.getElementById('issues-display');

    if (!issues || issues.length === 0) {
        display.innerHTML = '<div class="alert alert-success">✓ No issues detected</div>';
        return;
    }

    let html = '';
    for (const issue of issues) {
        const alertClass = issue.severity === 'critical' ? 'alert-danger' :
                          issue.severity === 'warning' ? 'alert-warning' : 'alert-info';

        html += `<div class="alert ${alertClass}">`;
        html += `<strong>${issue.title}</strong><br>`;
        html += `<small>${issue.description}</small><br>`;
        html += `<em class="text-muted">💡 ${issue.suggestion}</em>`;
        html += '</div>';
    }

    display.innerHTML = html;
}

// Network tests
document.getElementById('network-test-btn').addEventListener('click', function() {
    const button = this;
    const display = document.getElementById('network-results');

    button.disabled = true;
    button.textContent = 'Testing...';
    display.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Running network tests...';

    fetch('/api/diagnostics/network')
        .then(response => response.json())
        .then(data => {
            displayNetworkResults(data);
        })
        .catch(error => {
            display.innerHTML = `<div class="text-danger">Failed to run tests: ${error.message}</div>`;
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Run Network Tests';
        });
});

function displayNetworkResults(data) {
    const display = document.getElementById('network-results');
    let html = '';

    // Robot Pi results
    html += '<h6>Robot Pi (192.168.1.20)</h6>';
    html += displayHostResults(data.robot_pi);

    // Base Pi results
    html += '<h6 class="mt-3">Base Pi (192.168.1.10)</h6>';
    html += displayHostResults(data.base_pi);

    display.innerHTML = html;
}

function displayHostResults(hostData) {
    let html = '<div class="diagnostic-result">';

    // Ping result
    if (hostData.ping) {
        html += `<div class="success">✓ Ping: Success`;
        if (hostData.rtt_ms) {
            html += ` (${hostData.rtt_ms.toFixed(1)}ms)`;
        }
        html += '</div>';
    } else {
        html += '<div class="failure">✗ Ping: Failed</div>';
    }

    // Port results
    html += '<div class="mt-2"><strong>Ports:</strong></div>';
    for (const [port, reachable] of Object.entries(hostData.ports)) {
        const className = reachable ? 'success' : 'failure';
        const icon = reachable ? '✓' : '✗';
        html += `<div class="${className}">${icon} Port ${port}: ${reachable ? 'Open' : 'Closed/Filtered'}</div>`;
    }

    html += '</div>';
    return html;
}

// Camera scan
document.getElementById('camera-scan-btn').addEventListener('click', function() {
    const button = this;
    const display = document.getElementById('camera-results');

    button.disabled = true;
    button.textContent = 'Scanning...';
    display.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Scanning cameras...';

    fetch('/api/diagnostics/cameras')
        .then(response => response.json())
        .then(data => {
            displayCameraResults(data.cameras);
        })
        .catch(error => {
            display.innerHTML = `<div class="text-danger">Failed to scan cameras: ${error.message}</div>`;
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Scan Cameras';
        });
});

function displayCameraResults(cameras) {
    const display = document.getElementById('camera-results');

    if (!cameras || cameras.length === 0) {
        display.innerHTML = '<div class="text-warning">No camera devices found</div>';
        return;
    }

    let html = '';
    for (const camera of cameras) {
        const className = camera.openable ? 'success' : 'failure';

        html += `<div class="diagnostic-result ${className}">`;
        html += `<strong>${camera.device}</strong><br>`;
        html += `Exists: ${camera.exists ? '✓' : '✗'}<br>`;
        html += `Readable: ${camera.readable ? '✓' : '✗'}<br>`;
        html += `Openable: ${camera.openable ? '✓' : '✗'}<br>`;

        if (camera.info && Object.keys(camera.info).length > 0) {
            html += `<small>Resolution: ${camera.info.width}x${camera.info.height} @ ${camera.info.fps}fps</small>`;
        }

        html += '</div>';
    }

    display.innerHTML = html;
}

// Service status check
document.getElementById('service-check-btn').addEventListener('click', function() {
    const button = this;
    const display = document.getElementById('service-results');

    button.disabled = true;
    button.textContent = 'Checking...';
    display.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Checking services...';

    fetch('/api/diagnostics/services')
        .then(response => response.json())
        .then(data => {
            displayServiceResults(data.services);
        })
        .catch(error => {
            display.innerHTML = `<div class="text-danger">Failed to check services: ${error.message}</div>`;
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Check Services';
        });
});

function displayServiceResults(services) {
    const display = document.getElementById('service-results');
    let html = '';

    for (const [name, status] of Object.entries(services)) {
        const className = status.active ? 'success' : 'failure';
        const icon = status.active ? '✓' : '✗';

        html += `<div class="diagnostic-result ${className}">`;
        html += `<strong>${name}</strong><br>`;
        html += `${icon} State: ${status.state}<br>`;
        html += `Enabled: ${status.enabled ? 'Yes' : 'No'}`;
        html += '</div>';
    }

    display.innerHTML = html;
}

// System resources check
document.getElementById('resources-check-btn').addEventListener('click', function() {
    const button = this;
    const display = document.getElementById('resources-results');

    button.disabled = true;
    button.textContent = 'Checking...';
    display.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> Checking resources...';

    fetch('/api/diagnostics/resources')
        .then(response => response.json())
        .then(data => {
            displayResourceResults(data);
        })
        .catch(error => {
            display.innerHTML = `<div class="text-danger">Failed to check resources: ${error.message}</div>`;
        })
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Check Resources';
        });
});

function displayResourceResults(resources) {
    const display = document.getElementById('resources-results');
    let html = '<div class="diagnostic-result">';

    // CPU
    if (resources.cpu_percent !== undefined) {
        const cpuClass = resources.cpu_percent > 80 ? 'failure' : resources.cpu_percent > 60 ? 'warning' : 'success';
        html += `<div class="${cpuClass}">CPU: ${resources.cpu_percent.toFixed(1)}%</div>`;
    }

    // Memory
    if (resources.memory_percent !== undefined) {
        const memClass = resources.memory_percent > 90 ? 'failure' : resources.memory_percent > 75 ? 'warning' : 'success';
        html += `<div class="${memClass}">Memory: ${resources.memory_percent.toFixed(1)}%</div>`;
    }

    // Disk
    if (resources.disk_percent !== undefined) {
        const diskClass = resources.disk_percent > 90 ? 'failure' : resources.disk_percent > 75 ? 'warning' : 'success';
        html += `<div class="${diskClass}">Disk: ${resources.disk_percent.toFixed(1)}%</div>`;
    }

    // Temperature
    if (resources.temperature_c !== undefined) {
        const tempClass = resources.temperature_c > 80 ? 'failure' : resources.temperature_c > 70 ? 'warning' : 'success';
        html += `<div class="${tempClass}">Temperature: ${resources.temperature_c.toFixed(1)}°C</div>`;
    }

    html += '</div>';
    display.innerHTML = html;
}

// Service restart function (if enabled)
function restartService(serviceName) {
    if (!confirm(`Are you sure you want to restart ${serviceName}?`)) {
        return;
    }

    const button = event.target;
    button.disabled = true;
    button.textContent = 'Restarting...';

    fetch('/api/diagnostics/restart_service', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ service: serviceName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Success: ${data.message}`);
        } else {
            alert(`Failed: ${data.message}`);
        }
    })
    .catch(error => {
        alert(`Error: ${error.message}`);
    })
    .finally(() => {
        button.disabled = false;
        button.textContent = `Restart ${serviceName.replace('.service', '')}`;
    });
}

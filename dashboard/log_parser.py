"""
Log Parser

Parses structured JSON logs from systemd journal using journalctl.
Extracts status events and general logs from bridge services.
"""

import json
import subprocess
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def parse_recent_logs(service_name: str, lines: int = 50, level: Optional[str] = None) -> List[Dict]:
    """
    Parse recent logs from systemd journal.

    Args:
        service_name: Systemd service name (e.g., 'serpent-robot-bridge')
        lines: Number of recent log lines to retrieve
        level: Optional log level filter ('INFO', 'WARNING', 'ERROR', 'CRITICAL')

    Returns:
        List of log entry dictionaries with keys:
        - timestamp: ISO 8601 timestamp string
        - level: Log level string
        - message: Log message
        - json_data: Parsed JSON if message contains JSON
    """
    try:
        cmd = [
            'journalctl',
            '-u', service_name,
            '--no-pager',
            '-n', str(lines),
            '-o', 'json'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            logger.warning(f"journalctl failed for {service_name}: {result.stderr}")
            return []

        logs = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            try:
                entry = json.loads(line)
                log_entry = _parse_journal_entry(entry)

                # Apply level filter if specified
                if level and log_entry['level'] != level:
                    continue

                logs.append(log_entry)

            except json.JSONDecodeError:
                continue

        return logs

    except subprocess.TimeoutExpired:
        logger.error(f"journalctl timed out for {service_name}")
        return []
    except Exception as e:
        logger.error(f"Failed to parse logs for {service_name}: {e}")
        return []


def _parse_journal_entry(entry: Dict) -> Dict:
    """
    Parse a single journalctl JSON entry.

    Args:
        entry: Raw journalctl JSON entry

    Returns:
        Simplified log entry dictionary
    """
    message = entry.get('MESSAGE', '')
    timestamp = entry.get('__REALTIME_TIMESTAMP', '')

    # Convert microsecond timestamp to ISO 8601
    if timestamp:
        try:
            from datetime import datetime
            ts_sec = int(timestamp) / 1000000
            dt = datetime.fromtimestamp(ts_sec)
            timestamp = dt.isoformat()
        except:
            pass

    # Extract log level
    priority = entry.get('PRIORITY', '6')  # Default to INFO
    level_map = {
        '0': 'EMERGENCY',
        '1': 'ALERT',
        '2': 'CRITICAL',
        '3': 'ERROR',
        '4': 'WARNING',
        '5': 'NOTICE',
        '6': 'INFO',
        '7': 'DEBUG'
    }
    level = level_map.get(str(priority), 'INFO')

    # Try to parse JSON from message
    json_data = None
    try:
        # Check if message contains JSON
        if '{' in message and '}' in message:
            # Extract JSON portion (may have prefix text)
            json_start = message.index('{')
            json_str = message[json_start:]
            json_data = json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        pass

    return {
        'timestamp': timestamp,
        'level': level,
        'message': message,
        'json_data': json_data
    }


def get_latest_status_event(service_name: str) -> Optional[Dict]:
    """
    Get the most recent status event JSON from logs.

    Args:
        service_name: Systemd service name

    Returns:
        Status event dictionary or None if not found
    """
    logs = parse_recent_logs(service_name, lines=50)

    # Search backwards for most recent status event
    for log in reversed(logs):
        if log['json_data'] and log['json_data'].get('event') == 'status':
            return log['json_data']

    return None


def get_all_status_events(service_name: str, lines: int = 50) -> List[Dict]:
    """
    Get all status events from recent logs.

    Args:
        service_name: Systemd service name
        lines: Number of log lines to search

    Returns:
        List of status event dictionaries with timestamps
    """
    logs = parse_recent_logs(service_name, lines=lines)

    status_events = []
    for log in logs:
        if log['json_data'] and log['json_data'].get('event') == 'status':
            event = log['json_data'].copy()
            event['log_timestamp'] = log['timestamp']
            status_events.append(event)

    return status_events

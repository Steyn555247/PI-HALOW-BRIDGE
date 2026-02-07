"""
Logging Configuration Utilities

Provides centralized logging setup with role-based formatting.

Created for Phase 1 foundation utilities.
"""

import logging
import sys
from typing import Optional


def setup_logging(role: str, level: str = "INFO", log_file: Optional[str] = None):
    """
    Configure logging with role-based formatting.

    Args:
        role: Role identifier (e.g., "base_pi", "robot_pi")
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging (default None = console only)
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter with role prefix
    formatter = logging.Formatter(
        f'%(asctime)s - [{role}] %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            logging.info(f"Logging to file: {log_file}")
        except (OSError, PermissionError) as e:
            logging.error(f"Failed to create log file {log_file}: {e}")

    logging.info(f"Logging configured: role={role}, level={level}")

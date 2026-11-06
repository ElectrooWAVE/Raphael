"""Logging utility for Raphael scripts and modules.

Configures formatted dual logging to standard console and to
`logs/<script_name>_<timestamp>.log`.
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def setup_logger(script_name: str, log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """Set up and return a logger that writes to both console and a timestamped file.

    Args:
        script_name: Name of the script/process invoking the logger.
        log_dir: Directory path where log files will be saved.
        level: Logging verbosity level.

    Returns:
        logging.Logger instance configured with console and file handlers.
    """
    logger = logging.getLogger(script_name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if logger was already initialized
    if logger.handlers:
        return logger

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_script_name = Path(script_name).stem
    log_file = Path(log_dir) / f"{clean_script_name}_{timestamp}.log"

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info(f"Initialized logger for '{clean_script_name}'. Log file: {log_file}")
    return logger

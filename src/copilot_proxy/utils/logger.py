"""Logging setup using loguru."""

import sys
from typing import Optional

from loguru import logger as loguru_logger


def setup_logger(verbose: bool = False, show_token: bool = False) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable verbose logging
        show_token: Show token values in logs
    """
    # Remove default handler
    loguru_logger.remove()

    # Add stdout handler with appropriate level
    level = "DEBUG" if verbose else "INFO"

    log_format = (
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    loguru_logger.add(
        sys.stdout,
        format=log_format,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Store config
    loguru_logger.show_token = show_token


def get_logger(name: str) -> "loguru_logger":
    """Get logger instance with name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return loguru_logger.bind(name=name)


# Export main logger
logger = loguru_logger

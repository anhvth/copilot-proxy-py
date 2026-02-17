"""Configuration module."""

from .settings import Settings, get_settings, settings
from .paths import get_github_token_path, get_copilot_data_dir, PROJECT_ROOT, DATA_DIR
from .constants import (
    GITHUB_API_BASE,
    GITHUB_TOKEN_ENDPOINT,
    COPILOT_API_ENDPOINTS,
    DEFAULT_HEADERS,
    COPILOT_HEADERS_BASE,
)

__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "get_github_token_path",
    "get_copilot_data_dir",
    "PROJECT_ROOT",
    "DATA_DIR",
    "GITHUB_API_BASE",
    "GITHUB_TOKEN_ENDPOINT",
    "COPILOT_API_ENDPOINTS",
    "DEFAULT_HEADERS",
    "COPILOT_HEADERS_BASE",
]

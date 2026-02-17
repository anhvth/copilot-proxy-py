"""Path constants and utilities."""

import os
from pathlib import Path

# Project root is parent of src
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Data directory (shared with TypeScript version)
# Can be overridden via COPILOT_DATA_DIR environment variable for Docker
DATA_DIR = Path(os.environ.get("COPILOT_DATA_DIR", PROJECT_ROOT.parent / "copilot-data"))
GITHUB_TOKEN_FILE = DATA_DIR / "github_token"

# Cache directory for request/response logs
CACHE_DIR = PROJECT_ROOT / ".cache"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_github_token_path() -> Path:
    """Get path to GitHub token file."""
    return GITHUB_TOKEN_FILE


def get_copilot_data_dir() -> Path:
    """Get copilot-data directory."""
    return DATA_DIR

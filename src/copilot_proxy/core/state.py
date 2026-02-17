"""Global application state management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AppState:
    """Global application state."""

    # Authentication
    github_token: Optional[str] = None
    copilot_token: Optional[str] = None
    copilot_token_expires_at: Optional[datetime] = None

    # Configuration
    account_type: str = "individual"
    models_cache: Optional[dict] = None
    vscode_version: str = "1.96.0"
    editor_plugin_version: str = "copilot-chat/0.26.7"

    # Rate limiting
    manual_approve: bool = False
    rate_limit_seconds: Optional[int] = None
    rate_limit_wait: bool = False
    last_request_timestamp: Optional[datetime] = None

    # Server state
    is_running: bool = False
    refresh_scheduled: bool = False


# Global state instance
_state = AppState()


def get_state() -> AppState:
    """Get global application state."""
    return _state


def update_state(**kwargs) -> None:
    """Update global state with new values."""
    for key, value in kwargs.items():
        if hasattr(_state, key):
            setattr(_state, key, value)
        else:
            raise AttributeError(f"AppState has no attribute '{key}'")

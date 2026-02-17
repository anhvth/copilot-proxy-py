"""Configuration and settings for the proxy."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

from .paths import CACHE_DIR


class Settings(BaseSettings):
    """Application settings."""

    # Server
    port: int = 4242
    host: str = "0.0.0.0"
    verbose: bool = False

    # Copilot API
    account_type: str = "individual"  # individual, business, enterprise
    vscode_version: str = "1.96.0"
    editor_plugin_version: str = "copilot-chat/0.26.7"

    # Rate limiting
    rate_limit_seconds: Optional[int] = None
    rate_limit_wait: bool = False

    # Manual approval
    manual_approve: bool = False

    # Request/response logging
    cache_dir: Path = CACHE_DIR

    # Debugging
    show_token: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Get settings instance."""
    return Settings()


settings = get_settings()

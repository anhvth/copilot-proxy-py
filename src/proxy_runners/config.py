#!/usr/bin/env python3
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


DEFAULT_CONFIG: dict = {
    "server": {
        "host": "0.0.0.0",
        "port": 4343,
    },
    "routes": {
        "gh_copilot_prefix": "gh-copilot",
        "zai_prefix": "zai",
    },
    "providers": {
        "copilot": {
            "openai_upstream": "https://api.githubcopilot.com",
            "anthropic_upstream": "https://api.anthropic.com",
            "cache_dir": ".cache/copilot",
            "github_token": "",
        },
        "zai": {
            "openai_upstream": "https://api.z.ai/api/coding/paas/v4",
            "anthropic_upstream": "https://api.z.ai/api/anthropic",
            "cache_dir": ".cache/Z_AI",
            "api_key": "",
            "glm_version": "glm-4.5",
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | None = None) -> dict:
    load_dotenv()
    path = Path(
        config_path
        or os.environ.get("PROXY_CONFIG_FILE")
        or (Path.cwd() / "config.yaml")
    )
    merged = dict(DEFAULT_CONFIG)
    if path.exists():
        loaded = yaml.safe_load(path.read_text()) or {}
        if not isinstance(loaded, dict):
            raise RuntimeError(f"Invalid config structure in {path}")
        merged = _deep_merge(merged, loaded)
    return merged

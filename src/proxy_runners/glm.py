#!/usr/bin/env python3
import os
from pathlib import Path

from fastapi import Request

from .base import BaseCachingProxy


class GLMProxy(BaseCachingProxy):
    def __init__(self, settings: dict | None = None) -> None:
        settings = settings or {}
        super().__init__(
            title="Z.AI Caching Proxy",
            openai_upstream=os.environ.get(
                "Z_AI_OPENAI_URL",
                os.environ.get(
                    "OPENAI_UPSTREAM",
                    os.environ.get("GLM_UPSTREAM_BASE", settings.get("openai_upstream", "https://api.z.ai/api/coding/paas/v4")),
                ),
            ),
            anthropic_upstream=os.environ.get(
                "ANTHROPIC_UPSTREAM",
                os.environ.get("ANTHROPIC_UPSTREAM_BASE", settings.get("anthropic_upstream", "https://api.z.ai/api/anthropic")),
            ),
            cache_dir=Path(settings.get("cache_dir", ".cache/Z_AI")),
            logger_name="glm_proxy",
        )
        self.glm_version = os.environ.get("Z_AI_GLM_VERSION", str(settings.get("glm_version", "glm-4.5"))).strip()
        self.api_key = os.environ.get("Z_AI_API_KEY", str(settings.get("api_key", ""))).strip()

    async def provider_headers(self, request: Request, headers: dict[str, str]) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("Missing Z_AI_API_KEY. Add it to .env and restart.")
        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

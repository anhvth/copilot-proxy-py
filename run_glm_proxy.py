#!/usr/bin/env python3
import os
from pathlib import Path

import uvicorn
from fastapi import Request

from proxy_base import BaseCachingProxy


class GLMProxy(BaseCachingProxy):
    def __init__(self) -> None:
        super().__init__(
            title="Z.AI Caching Proxy",
            openai_upstream=os.environ.get(
                "Z_AI_OPENAI_URL",
                os.environ.get("OPENAI_UPSTREAM", "https://api.z.ai/api/coding/paas/v4"),
            ),
            anthropic_upstream=os.environ.get("ANTHROPIC_UPSTREAM", "https://api.z.ai/api/anthropic"),
            cache_dir=Path(".cache/Z_AI"),
            logger_name="glm_proxy",
        )
        self.api_key = os.environ.get("Z_AI_API_KEY", "").strip()

    async def provider_headers(self, request: Request, headers: dict[str, str]) -> dict[str, str]:
        if self.api_key:
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


proxy = GLMProxy()
app = proxy.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4343)

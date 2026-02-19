#!/usr/bin/env python3
import json
import os
from pathlib import Path

from fastapi import Request

from .base import BaseCachingProxy, ProxyAuthError


class CopilotProxy(BaseCachingProxy):
    def __init__(self, settings: dict | None = None) -> None:
        settings = settings or {}
        super().__init__(
            title="Copilot Caching Proxy",
            openai_upstream=os.environ.get("OPENAI_UPSTREAM", settings.get("openai_upstream", "https://api.githubcopilot.com")),
            anthropic_upstream=os.environ.get("ANTHROPIC_UPSTREAM", settings.get("anthropic_upstream", "https://api.anthropic.com")),
            cache_dir=Path(settings.get("cache_dir", ".cache/copilot")),
            logger_name="copilot_proxy",
        )
        self.github_token = os.environ.get("GITHUB_TOKEN", str(settings.get("github_token", ""))).strip()

    async def _ensure_copilot_token(self) -> str:
        github_token = self.github_token
        if not github_token:
            raise ProxyAuthError(
                401,
                {
                    "error": {
                        "message": "Missing GITHUB_TOKEN. Add it to .env and restart.",
                        "type": "authentication_error",
                    }
                },
            )

        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/json",
            "User-Agent": "copilot-proxy",
        }
        async with self.client.stream(
            "GET", "https://api.github.com/copilot_internal/v2/token", headers=headers
        ) as resp:
            payload = await resp.aread()
            if resp.status_code != 200:
                raise ProxyAuthError(
                    401,
                    {
                        "error": {
                            "message": (
                                f"GitHub token exchange failed ({resp.status_code}): "
                                f"{payload.decode(errors='ignore')}"
                            ),
                            "type": "authentication_error",
                        }
                    },
                )
        data = json.loads(payload)
        token = data.get("token")
        if not token:
            raise ProxyAuthError(
                401,
                {
                    "error": {
                        "message": "No Copilot token in GitHub response",
                        "type": "authentication_error",
                    }
                },
            )
        return token

    async def provider_headers(self, request: Request, headers: dict[str, str]) -> dict[str, str]:
        token = await self._ensure_copilot_token()
        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        headers["Authorization"] = f"Bearer {token}"
        headers.update(
            {
                "copilot-integration-id": "vscode-chat",
                "editor-version": "vscode/1.96.0",
                "editor-plugin-version": "copilot-chat/0.26.7",
                "user-agent": "GitHubCopilotChat/0.26.7",
                "openai-intent": "conversation-panel",
                "x-github-api-version": "2025-04-01",
            }
        )
        return headers

#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import Request

from .base import BaseCachingProxy
from .copilot import CopilotProxy
from .config import load_config
from .glm import GLMProxy


class UnifiedProxyGateway(BaseCachingProxy):
    """Single endpoint gateway that routes by URL prefix."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or load_config()
        self._ensure_required_credentials()
        providers = self.config.get("providers", {})
        self.gh_copilot_prefix = str(self.config.get("routes", {}).get("gh_copilot_prefix", "gh-copilot")).strip("/")
        self.zai_prefix = str(self.config.get("routes", {}).get("zai_prefix", "zai")).strip("/")
        self.gh_copilot = CopilotProxy(settings=providers.get("copilot", {}))
        self.zai = GLMProxy(settings=providers.get("zai", {}))
        super().__init__(
            title="Unified AI Proxy Gateway",
            openai_upstream="https://unused.local",
            anthropic_upstream="https://unused.local",
            cache_dir=Path(".cache/unified"),
            logger_name="unified_proxy",
        )
        self._log_startup()

    def _ensure_required_credentials(self) -> None:
        self._ensure_github_token()
        self._ensure_env_secret(
            "Z_AI_API_KEY",
            "Z.AI API key",
        )

    def _ensure_github_token(self) -> None:
        current = os.environ.get("GITHUB_TOKEN", "").strip()
        if current:
            return
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Missing required secret GITHUB_TOKEN. Run `gh auth login`, then restart."
            )

        print("Missing GITHUB_TOKEN.")
        answer = input("Run `gh auth login` now? [Y/n]: ").strip().lower()
        if answer in {"n", "no"}:
            raise RuntimeError("GITHUB_TOKEN is required. Aborted by user.")

        try:
            login_env = os.environ.copy()
            login_env.pop("GITHUB_TOKEN", None)
            login_env.pop("GH_TOKEN", None)
            login = subprocess.run(["gh", "auth", "login"], check=False, env=login_env)
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI (`gh`) is not installed. Install it, run `gh auth login`, then restart."
            ) from None

        if login.returncode != 0:
            raise RuntimeError("`gh auth login` did not complete successfully.")

        token = self._read_gh_token()
        if not token:
            raise RuntimeError(
                "Could not read token from `gh auth token`. Please run `gh auth login` and retry."
            )

        self._upsert_env_file("GITHUB_TOKEN", token)
        os.environ["GITHUB_TOKEN"] = token
        print("Saved GITHUB_TOKEN to .env")

    @staticmethod
    def _read_gh_token() -> str:
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI (`gh`) is not installed. Install it, run `gh auth login`, then restart."
            ) from None

        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _ensure_env_secret(self, key: str, label: str) -> None:
        current = os.environ.get(key, "").strip()
        if current:
            return
        if sys.stdin.isatty():
            print(f"Missing {key}.")
            entered = input(f"Enter {label}: ").strip()
            if entered:
                self._upsert_env_file(key, entered)
                os.environ[key] = entered
                print(f"Saved {key} to .env")
                return
        raise RuntimeError(
            f"Missing required secret {key}. Add it to .env, e.g. {key}=<value>, then restart."
        )

    @staticmethod
    def _upsert_env_file(key: str, value: str) -> None:
        env_path = Path.cwd() / ".env"
        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()
        updated = False
        for idx, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[idx] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        env_path.write_text("\n".join(lines).rstrip() + "\n")

    def _log_startup(self) -> None:
        self.logger.info("=" * 50)
        self.logger.info("Unified AI Proxy Gateway")
        self.logger.info("=" * 50)
        self.logger.info(f"GitHub Copilot: /{self.gh_copilot_prefix}/{{openai,anthropic}}/{{path}}")
        self.logger.info(f"Z.AI:            /{self.zai_prefix}/{{openai,anthropic}}/{{path}}")
        self.logger.info(f"Cache directory:  {self.cache_dir}")
        self.logger.info("=" * 50)

    def _register_routes(self) -> None:
        @self.app.get("/health")
        async def health():
            return {
                "status": "ok",
                "routes": [
                    f"/{self.gh_copilot_prefix}/openai/{{path}}",
                    f"/{self.gh_copilot_prefix}/anthropic/{{path}}",
                    f"/{self.zai_prefix}/openai/{{path}}",
                    f"/{self.zai_prefix}/anthropic/{{path}}",
                ],
            }

        @self.app.api_route(f"/{self.gh_copilot_prefix}/openai/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def gh_copilot_openai(request: Request, path: str):
            normalized_path = path[3:] if path.startswith("v1/") else path
            return await self.gh_copilot._proxy(request, normalized_path, self.gh_copilot.openai_upstream)

        @self.app.api_route(f"/{self.gh_copilot_prefix}/anthropic/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def gh_copilot_anthropic(request: Request, path: str):
            return await self.gh_copilot._proxy(request, path, self.gh_copilot.anthropic_upstream)

        @self.app.api_route(f"/{self.zai_prefix}/openai/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def zai_openai(request: Request, path: str):
            normalized_path = path[3:] if path.startswith("v1/") else path
            return await self.zai._proxy(request, normalized_path, self.zai.openai_upstream)

        @self.app.api_route(f"/{self.zai_prefix}/anthropic/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def zai_anthropic(request: Request, path: str):
            return await self.zai._proxy(request, path, self.zai.anthropic_upstream)

def main() -> None:
    _cfg = load_config()
    gateway = UnifiedProxyGateway(config=_cfg)
    app = gateway.app
    server = _cfg.get("server", {})
    uvicorn.run(app, host=str(server.get("host", "0.0.0.0")), port=int(server.get("port", 4343)))


if __name__ == "__main__":
    main()

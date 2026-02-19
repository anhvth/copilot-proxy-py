#!/usr/bin/env python3
import json
import logging
import sys
from pathlib import Path

import uvicorn

from src.proxy_runners.config import load_config
from src.proxy_runners.unified import UnifiedProxyGateway


def _build_endpoints(host: str, port: int, gh_prefix: str, zai_prefix: str) -> dict[str, str]:
    base_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    base = f"http://{base_host}:{port}"
    return {
        "health": f"{base}/health",
        "gh_copilot_openai": f"{base}/{gh_prefix}/openai",
        "gh_copilot_anthropic": f"{base}/{gh_prefix}/anthropic",
        "zai_openai": f"{base}/{zai_prefix}/openai",
        "zai_anthropic": f"{base}/{zai_prefix}/anthropic",
    }


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = load_config(config_path=config_path)
    gateway = UnifiedProxyGateway(config=config)
    app = gateway.app
    server = config.get("server", {})
    host = str(server.get("host", "0.0.0.0"))
    port = int(server.get("port", 4343))
    routes = config.get("routes", {})
    gh_prefix = str(routes.get("gh_copilot_prefix", "gh-copilot")).strip("/")
    zai_prefix = str(routes.get("zai_prefix", "zai")).strip("/")

    endpoints = _build_endpoints(host=host, port=port, gh_prefix=gh_prefix, zai_prefix=zai_prefix)
    endpoints_path = Path("endpoints.json")
    endpoints_path.write_text(json.dumps(endpoints, indent=2) + "\n")

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    print("Available endpoints:")
    print(json.dumps(endpoints, indent=2))
    print(f"Saved endpoint list: {endpoints_path}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import os
import json
import hashlib
import logging
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
import httpx
import uvicorn

app = FastAPI(title="Copilot Caching Proxy")
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("copilot_proxy")

# Environment variables & Upstream Base URLs
OPENAI_UPSTREAM = os.environ.get("OPENAI_UPSTREAM", "https://api.githubcopilot.com").rstrip("/")
ANTHROPIC_UPSTREAM = os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")

# Optional fixed Copilot token. If missing, token is auto-fetched via GitHub token exchange.
COPILOT_TOKEN = os.environ.get("COPILOT_TOKEN", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_TOKEN_FILE = Path(os.environ.get("GITHUB_TOKEN_FILE", str(Path.home() / ".cache" / "copilot-token")))

# Cache setup
CACHE_DIR = Path(".cache/responses")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))


def _short_text(value: object, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else f"{text[:limit]}...(truncated)"


def _log_payload(method: str, path: str, payload: object, is_stream: bool) -> None:
    logger.info(json.dumps({
        "type": "payload",
        "method": method,
        "path": path,
        "stream": is_stream,
        "payload": _short_text(payload),
    }, ensure_ascii=False))


def _log_response(method: str, path: str, status: int, response_data: object, *, stream: bool = False, cached: bool = False) -> None:
    logger.info(json.dumps({
        "type": "response",
        "method": method,
        "path": path,
        "status_code": status,
        "stream": stream,
        "cached": cached,
        "response": _short_text(response_data),
    }, ensure_ascii=False))


async def _ensure_copilot_token() -> str:
    """Resolve a usable Copilot token without importing src/ internals."""
    if COPILOT_TOKEN:
        return COPILOT_TOKEN

    github_token = GITHUB_TOKEN
    if not github_token and GITHUB_TOKEN_FILE.exists():
        github_token = GITHUB_TOKEN_FILE.read_text().strip()
    if not github_token:
        raise RuntimeError("Set COPILOT_TOKEN, GITHUB_TOKEN, or GITHUB_TOKEN_FILE")

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/json",
        "User-Agent": "copilot-proxy",
    }
    async with client.stream(
        "GET", "https://api.github.com/copilot_internal/v2/token", headers=headers
    ) as resp:
        payload = await resp.aread()
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub token exchange failed ({resp.status_code}): {payload.decode(errors='ignore')}")
    data = json.loads(payload)
    token = data.get("token")
    if not token:
        raise RuntimeError("No Copilot token in GitHub response")
    return token

def _get_cache_key(path: str, body_dict: dict) -> str:
    """Generate a consistent cache key based on path and payload."""
    body_dict.pop("stream", None)
    body_str = json.dumps(body_dict, sort_keys=True)
    return hashlib.md5(f"{path}:{body_str}".encode()).hexdigest()

async def _proxy(request: Request, path: str, base_url: str):
    url = f"{base_url}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
        
    # Clean headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    
    # FORCE overwrite Authorization header with a valid Copilot token
    try:
        token = await _ensure_copilot_token()
    except Exception as e:
        error_data = {
            "error": {
                "message": f"Copilot token unavailable: {type(e).__name__}: {e}",
                "type": "authentication_error",
            }
        }
        _log_response(request.method, path, 401, error_data)
        return Response(
            content=json.dumps(error_data),
            status_code=401,
            media_type="application/json",
        )

    headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    headers["Authorization"] = f"Bearer {token}"

    # Inject strictly required Copilot headers
    headers.update({
        "copilot-integration-id": "vscode-chat",
        "editor-version": "vscode/1.96.0",
        "editor-plugin-version": "copilot-chat/0.26.7",
        "user-agent": "GitHubCopilotChat/0.26.7",
        "openai-intent": "conversation-panel",
        "x-github-api-version": "2025-04-01",
    })

    # Parse body to check cache/stream
    try:
        body_bytes = await request.body()
        body_dict = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        body_dict = None
        body_bytes = await request.body()

    cache_file = None
    is_stream_request = bool(body_dict and body_dict.get("stream") is True)
    _log_payload(request.method, path, body_dict if body_dict is not None else body_bytes.decode(errors="ignore"), is_stream_request)
    
    # 1. Cache hit check (skip cache for streaming)
    if body_dict is not None and request.method == "POST" and not is_stream_request:
        cache_key = _get_cache_key(path, dict(body_dict))
        cache_file = CACHE_DIR / f"{cache_key}.json"
        
        if cache_file.exists():
            cached_content = cache_file.read_bytes()
            _log_response(request.method, path, 200, cached_content.decode(errors="ignore"), cached=True)
            return Response(
                content=cached_content,
                media_type="application/json"
            )
        content = json.dumps(body_dict).encode("utf-8")
    else:
        content = body_bytes

    def _response_headers(raw_headers):
        skip = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length"}
        return {k: v for k, v in raw_headers.items() if k.lower() not in skip}

    # 2. Stream passthrough for SSE responses
    if is_stream_request:
        req = client.build_request(request.method, url, content=content, headers=headers)
        upstream = await client.send(req, stream=True)
        _log_response(request.method, path, upstream.status_code, "streaming_started", stream=True)
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=_response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
            background=BackgroundTask(upstream.aclose),
        )

    # 3. Fetch non-stream response from Upstream
    req = client.build_request(request.method, url, content=content, headers=headers)
    upstream = await client.send(req)

    # 4. Cache the response if successful
    if upstream.status_code == 200 and cache_file:
        cache_file.write_bytes(upstream.content)
    _log_response(request.method, path, upstream.status_code, upstream.text)

    # 5. Return to client
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type")
    )

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_v1_default(request: Request, path: str):
    return await _proxy(request, path, OPENAI_UPSTREAM)

@app.api_route("/openai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_openai(request: Request, path: str):
    if path.startswith("v1/"):
        path = path[3:]
    return await _proxy(request, path, OPENAI_UPSTREAM)

@app.api_route("/anthropic/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_anthropic(request: Request, path: str):
    return await _proxy(request, path, ANTHROPIC_UPSTREAM)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4242)

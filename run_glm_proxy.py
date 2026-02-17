#!/usr/bin/env python3
"""
Thin passthrough proxy for Z.ai GLM API.

Maps:  http://localhost:4343/v1/{path} → {UPSTREAM_BASE}/{path}

Bits in, bits out. No transformation. Supports streaming.
Logs request/response metadata + JSON bodies to .cache/.
"""

import json
import os
import time
import traceback
import uuid
from pathlib import Path

import httpx
import typer
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger

# Load .env file (won't override existing env vars)
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
UPSTREAM_BASE = os.environ.get(
    "GLM_UPSTREAM_BASE", "https://api.z.ai/api/coding/paas/v4"
).rstrip("/")

# If set, every request gets this key injected as Authorization: Bearer <key>
# If not set, caller must supply their own Authorization header.
DEFAULT_API_KEY = os.environ.get("Z_AI_API_KEY", "")


def _get_api_key() -> str:
    """Get API key, re-reading from env if not set at startup."""
    global DEFAULT_API_KEY
    if not DEFAULT_API_KEY:
        DEFAULT_API_KEY = os.environ.get("Z_AI_API_KEY", "")
    return DEFAULT_API_KEY

LOG_DIR = Path(".cache")
LOG_DIR.mkdir(exist_ok=True)

# Only forward these headers to upstream (whitelist approach)
_FORWARD_HEADERS = frozenset({
    "content-type", "accept", "authorization",
})


def _clean_headers(raw: dict[str, str]) -> dict[str, str]:
    # Normalize to lowercase keys to avoid duplicate headers (HTTP headers are case-insensitive)
    out = {k.lower(): v for k, v in raw.items() if k.lower() in _FORWARD_HEADERS}
    # Always inject API key if available (overrides caller's header)
    api_key = _get_api_key()
    if api_key:
        out["authorization"] = f"Bearer {api_key}"
    # Ensure content-type is set for JSON bodies
    if "content-type" not in out:
        out["content-type"] = "application/json"
    return out


def _safe_json(data: bytes) -> dict | list | None:
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager

# Single async client for connection pooling — timeout=None for long streams
_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=None, write=30, pool=30))
    yield
    await _client.aclose()


app = FastAPI(title="GLM Passthrough Proxy", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "upstream": UPSTREAM_BASE}


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, path: str):
    req_id = str(uuid.uuid4())[:8]
    started = time.time()

    upstream_url = f"{UPSTREAM_BASE}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    # Read request body fully (needed for logging + forwarding)
    body = await request.body()
    out_headers = _clean_headers(dict(request.headers))

    logger.info(f"[{req_id}] {request.method} /v1/{path} → {upstream_url}")
    logger.debug(f"[{req_id}] forwarded headers: {out_headers}")

    # Determine if caller expects streaming (SSE)
    body_json = _safe_json(body)
    is_stream = isinstance(body_json, dict) and body_json.get("stream", False)

    if is_stream:
        return await _stream_proxy(req_id, request.method, upstream_url, body, out_headers, started, path, body_json)
    else:
        return await _buffered_proxy(req_id, request.method, upstream_url, body, out_headers, started, path, body_json)


async def _buffered_proxy(req_id, method, url, body, headers, started, path, body_json):
    """Non-streaming: buffer full response, log, return."""
    try:
        resp = await _client.request(method=method, url=url, content=body, headers=headers)
    except httpx.HTTPError as e:
        tb = traceback.format_exc()
        logger.error(f"[{req_id}] upstream error: {e}")
        _log(req_id, method, url, headers, body_json, None, 502, time.time() - started, error=str(e), traceback=tb)
        return StreamingResponse(iter([f"Upstream error: {e}".encode()]), status_code=502)

    resp_json = _safe_json(resp.content)
    duration = time.time() - started
    logger.info(f"[{req_id}] ← {resp.status_code} ({duration:.2f}s)")

    if resp.status_code >= 400:
        error_text = resp.content.decode(errors="replace")
        logger.error(f"[{req_id}] upstream {resp.status_code}: {error_text[:500]}")
        _log(req_id, method, url, headers, body_json, resp_json or {"raw": error_text[:2000]}, resp.status_code, duration, error=error_text[:2000])
    else:
        _log(req_id, method, url, headers, body_json, resp_json, resp.status_code, duration)

    resp_headers = _response_headers(resp.headers)
    return StreamingResponse(
        iter([resp.content]),
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=resp.headers.get("content-type"),
    )


async def _stream_proxy(req_id, method, url, body, headers, started, path, body_json):
    """Streaming: pipe bytes through, collect for logging."""
    try:
        req = _client.build_request(method, url, content=body, headers=headers)
        upstream = await _client.send(req, stream=True)
    except httpx.HTTPError as e:
        tb = traceback.format_exc()
        logger.error(f"[{req_id}] upstream connect error: {e}")
        _log(req_id, method, url, headers, body_json, None, 502, time.time() - started, error=str(e), traceback=tb)
        return StreamingResponse(iter([f"Upstream error: {e}".encode()]), status_code=502)

    if upstream.status_code >= 400:
        error_body = (await upstream.aread()).decode(errors="replace")
        await upstream.aclose()
        logger.error(f"[{req_id}] upstream error {upstream.status_code}: {error_body}")
        _log(req_id, method, url, headers, body_json, {"error": error_body}, upstream.status_code, time.time() - started, error=error_body[:2000])
        return StreamingResponse(
            iter([error_body.encode()]),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

    collected_chunks: list[bytes] = []

    async def _pipe():
        try:
            async for chunk in upstream.aiter_bytes():
                collected_chunks.append(chunk)
                yield chunk
        finally:
            await upstream.aclose()
            duration = time.time() - started
            logger.info(f"[{req_id}] ← stream done ({duration:.2f}s)")
            full = b"".join(collected_chunks)
            _log(req_id, method, url, headers, body_json, _parse_sse_log(full), upstream.status_code, duration)

    resp_headers = _response_headers(upstream.headers)
    return StreamingResponse(
        _pipe(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


def _parse_sse_log(data: bytes) -> dict | list | None:
    """Best-effort parse SSE stream for logging."""
    try:
        text = data.decode("utf-8", errors="replace")
        chunks = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    chunks.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
        if chunks:
            return {"_sse_chunks": len(chunks), "first": chunks[0], "last": chunks[-1]}
    except Exception:
        pass
    return None


def _response_headers(raw_headers) -> dict[str, str]:
    """Filter response headers to avoid hop-by-hop issues."""
    skip = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length"}
    return {k: v for k, v in raw_headers.items() if k.lower() not in skip}


def _log(req_id, method, url, fwd_headers, req_json, resp_json, status, duration, *, error=None, traceback=None):
    """Write a JSON log file to .cache/ with full debug info."""
    record = {
        "id": req_id,
        "ts": time.time(),
        "duration_s": round(duration, 3),
        "request": {
            "method": method,
            "upstream_url": url,
            "forwarded_headers": {k: v for k, v in fwd_headers.items() if k.lower() != "authorization"},
            "json": req_json,
        },
        "response": {"status_code": status, "json": resp_json},
    }
    if error:
        record["error"] = error
    if traceback:
        record["traceback"] = traceback
    try:
        (LOG_DIR / f"{req_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2)
        )
    except Exception as e:
        logger.warning(f"[{req_id}] failed to write log: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(
    port: int = typer.Option(4343, "--port", "-p", help="Listen port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Listen host"),
    upstream: str = typer.Option(UPSTREAM_BASE, "--upstream", "-u", help="Upstream base URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
):
    """Start the GLM passthrough proxy."""
    global UPSTREAM_BASE
    UPSTREAM_BASE = upstream.rstrip("/")

    level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=level, colorize=True)

    logger.info(f"Proxy: http://{host}:{port}/v1/... → {UPSTREAM_BASE}/...")
    key = _get_api_key()
    if key:
        logger.info(f"Default API key: {key[:10]}...")
    else:
        logger.info("No default API key — caller must supply Authorization header")

    uvicorn.run(app, host=host, port=port, log_level=level.lower())


if __name__ == "__main__":
    typer.run(main)

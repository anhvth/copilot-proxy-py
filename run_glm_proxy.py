#!/usr/bin/env python3
"""
Simple passthrough proxy for OpenAI + Anthropic APIs.

Maps:
  - http://localhost:4343/openai/{path}    → {OPENAI_UPSTREAM}/{path}
  - http://localhost:4343/anthropic/{path} → {ANTHROPIC_UPSTREAM}/{path}

Drop-in replacement: wherever you used https://api.z.ai/api/coding/paas/v4,
now use http://localhost:4343/openai — same for anthropic.

Bits in, bits out. No transformation. Supports streaming.
Logs request/response metadata + JSON bodies to .cache/logs/.
"""

import json
import os
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import portalocker
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
OPENAI_UPSTREAM = os.environ.get(
    "OPENAI_UPSTREAM_BASE", os.environ.get("GLM_UPSTREAM_BASE", "https://api.z.ai/api/coding/paas/v4")
).rstrip("/")

ANTHROPIC_UPSTREAM = os.environ.get(
    "ANTHROPIC_UPSTREAM_BASE", "https://api.z.ai/api/anthropic"
).rstrip("/")

# If set, every request gets this key injected as Authorization: Bearer <key>
DEFAULT_API_KEY = os.environ.get("Z_AI_API_KEY", os.environ.get("API_KEY", ""))


def _get_api_key() -> str:
    """Get API key, re-reading from env if not set at startup."""
    global DEFAULT_API_KEY
    if not DEFAULT_API_KEY:
        DEFAULT_API_KEY = os.environ.get("Z_AI_API_KEY", "")
    return DEFAULT_API_KEY


LOG_DIR = Path(".cache/logs")


def _get_hour_folder() -> Path:
    """Get current hour folder path."""
    now = datetime.now()
    date_str = now.strftime("%y%m%d_%H")
    folder = LOG_DIR / date_str
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _get_next_sequence(folder: Path) -> int:
    """Get next sequence number using file locking."""
    counter_file = folder / "counter.txt"

    if not counter_file.exists():
        counter_file.write_text("0\n")

    try:
        with open(counter_file, "r+") as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            f.seek(0)
            content = f.read().strip()
            current = int(content) if content else 0
            next_seq = current + 1
            f.seek(0)
            f.write(str(next_seq) + "\n")
            f.truncate()
            return next_seq
    except Exception as e:
        logger.error(f"Failed to get next sequence: {e}")
        fallback = len(list(folder.glob("*.json"))) + 1
        logger.warning(f"Using fallback sequence number: {fallback}")
        return fallback


# Only forward these headers to upstream (whitelist approach)
_FORWARD_HEADERS = frozenset({
    "content-type", "accept", "authorization", "x-api-key",
})


def _clean_headers(raw: dict[str, str]) -> dict[str, str]:
    out = {k.lower(): v for k, v in raw.items() if k.lower() in _FORWARD_HEADERS}
    api_key = _get_api_key()
    if api_key:
        out["authorization"] = f"Bearer {api_key}"
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


def _drop_none_values(value: Any) -> Any:
    """Recursively remove keys with None values from dict/list payloads."""
    if isinstance(value, dict):
        return {k: _drop_none_values(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none_values(v) for v in value]
    return value


def _normalize_message_content_parts(payload: dict[str, Any]) -> None:
    """Normalize OpenAI content-part variants to text parts expected by GLM-compatible upstreams."""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return

    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue

        normalized_parts: list[Any] = []
        changed = False
        for part in content:
            if not isinstance(part, dict):
                normalized_parts.append(part)
                continue

            part_type = part.get("type")
            # Newer OpenAI SDKs may emit input_text/output_text; many compatible
            # providers only accept type="text".
            if part_type in {"input_text", "output_text"}:
                changed = True
                normalized_parts.append({"type": "text", "text": part.get("text", "")})
                continue

            # Discard unsupported part types that commonly trigger strict upstream validation.
            if part_type in {"input_audio", "audio", "image_url", "input_image", "file", "refusal"}:
                changed = True
                continue

            normalized_parts.append(part)

        if changed:
            message["content"] = normalized_parts


def _sanitize_openai_payload(path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Best-effort compatibility sanitizer for strict OpenAI-compatible upstreams.

    Returns sanitized payload and a list of notes describing applied changes.
    """
    sanitized = _drop_none_values(dict(payload))
    notes: list[str] = []

    # Common alias used by latest SDKs; many OpenAI-compatible providers still expect max_tokens.
    if "max_completion_tokens" in sanitized and "max_tokens" not in sanitized:
        sanitized["max_tokens"] = sanitized.pop("max_completion_tokens")
        notes.append("mapped max_completion_tokens -> max_tokens")

    if path in {"chat/completions", "v1/chat/completions"}:
        # Fields often rejected by strict OpenAI-compatible providers.
        dropped = []
        for key in (
            "store",
            "metadata",
            "prediction",
            "modalities",
            "audio",
            "reasoning",
            "reasoning_effort",
            "service_tier",
        ):
            if key in sanitized:
                sanitized.pop(key, None)
                dropped.append(key)

        if dropped:
            notes.append(f"dropped unsupported keys: {', '.join(dropped)}")

        _normalize_message_content_parts(sanitized)

    return sanitized, notes


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager

_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=None, write=30, pool=30))
    yield
    await _client.aclose()


app = FastAPI(
    title="Passthrough Proxy",
    description=(
        f"OpenAI: /openai/... → {OPENAI_UPSTREAM}/...\n"
        f"Anthropic: /anthropic/... → {ANTHROPIC_UPSTREAM}/..."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "openai_upstream": OPENAI_UPSTREAM,
        "anthropic_upstream": ANTHROPIC_UPSTREAM,
    }


# ---------------------------------------------------------------------------
# Two simple catch-all routes
# ---------------------------------------------------------------------------
@app.api_route(
    "/openai/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    summary="Proxy to OpenAI-compatible upstream",
    tags=["OpenAI"],
)
async def proxy_openai(request: Request, path: str):
    """Forward /openai/{path} → OPENAI_UPSTREAM/{path}, stripping v1/ prefix since upstream has its own version."""
    # Strip v1/ prefix — upstream base URL already includes versioning (e.g. /v4)
    if path.startswith("v1/"):
        path = path[3:]
    return await _proxy_request(request, path, OPENAI_UPSTREAM)


@app.api_route(
    "/anthropic/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    summary="Proxy to Anthropic-compatible upstream",
    tags=["Anthropic"],
)
async def proxy_anthropic(request: Request, path: str):
    """Forward /anthropic/{path} → ANTHROPIC_UPSTREAM/{path}"""
    return await _proxy_request(request, path, ANTHROPIC_UPSTREAM)

# ---------------------------------------------------------------------------
# Root-level v1 routes for tools expecting standard paths
# ---------------------------------------------------------------------------
@app.api_route(
    "/v1/messages{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    summary="Direct Anthropic v1/messages proxy",
    tags=["Anthropic Root"],
)
async def proxy_anthropic_root(request: Request, path: str = ""):
    """Forward /v1/messages... → ANTHROPIC_UPSTREAM/v1/messages..."""
    # Construct the full path to forward, handling query params in _proxy_request
    forward_path = f"v1/messages{path}"
    return await _proxy_request(request, forward_path, ANTHROPIC_UPSTREAM)

@app.api_route(
    "/v1/complete{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    summary="Direct Anthropic v1/complete proxy",
    tags=["Anthropic Root"],
)
async def proxy_anthropic_complete(request: Request, path: str = ""):
    """Forward /v1/complete... → ANTHROPIC_UPSTREAM/v1/complete..."""
    forward_path = f"v1/complete{path}"
    return await _proxy_request(request, forward_path, ANTHROPIC_UPSTREAM)


# ---------------------------------------------------------------------------
# Core proxy helper
# ---------------------------------------------------------------------------
async def _proxy_request(request: Request, path: str, base_url: str):
    req_id = str(uuid.uuid4())[:8]
    started = time.time()

    upstream_url = f"{base_url}/{path}"
    if request.url.query:
        upstream_url += f"?{request.url.query}"

    body = await request.body()
    out_headers = _clean_headers(dict(request.headers))

    logger.info(f"[{req_id}] {request.method} /{path} → {upstream_url}")
    logger.debug(f"[{req_id}] forwarded headers: {out_headers}")

    body_json = _safe_json(body)

    # Compatibility mode for strict OpenAI-compatible upstreams (e.g., Z.AI).
    # Some latest OpenAI SDK params are rejected with generic "invalid parameter" errors.
    if isinstance(body_json, dict) and base_url == OPENAI_UPSTREAM:
        sanitized_body_json, sanitize_notes = _sanitize_openai_payload(path, body_json)
        if sanitized_body_json != body_json:
            body_json = sanitized_body_json
            body = json.dumps(body_json, ensure_ascii=False).encode("utf-8")
            logger.debug(f"[{req_id}] sanitized request body for upstream compatibility: {sanitize_notes}")

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
        full_content = []
        full_reasoning = []
        
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    chunk = json.loads(line[6:])
                    chunks.append(chunk)
                    
                    # OpenAI-compatible format (including GLM)
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        # Capture regular content
                        if "content" in delta and delta["content"]:
                            full_content.append(delta["content"])
                        # Capture reasoning_content (GLM-specific)
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            full_reasoning.append(delta["reasoning_content"])
                    
                    # Anthropic Messages API format
                    if "type" in chunk:
                        if chunk["type"] == "content_block_delta":
                            if "delta" in chunk and "text" in chunk.get("delta", {}):
                                full_content.append(chunk["delta"]["text"])
                        elif chunk["type"] == "content_block_start":
                            # Anthropic can have initial text in content_block_start
                            if "content_block" in chunk and chunk["content_block"].get("type") == "text":
                                text_val = chunk["content_block"].get("text", "")
                                if text_val:
                                    full_content.append(text_val)
                except json.JSONDecodeError:
                    pass
                    
        if chunks:
            result = {
                "_sse_chunks": len(chunks), 
                "first": chunks[0], 
                "last": chunks[-1],
            }
            # Add full_response_text if we captured any content
            if full_content:
                result["full_response_text"] = "".join(full_content)
            # Add reasoning if present (GLM-specific)
            if full_reasoning:
                result["full_reasoning_content"] = "".join(full_reasoning)
            return result
    except Exception:
        pass
    return None


def _response_headers(raw_headers) -> dict[str, str]:
    """Filter response headers to avoid hop-by-hop issues."""
    skip = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length"}
    return {k: v for k, v in raw_headers.items() if k.lower() not in skip}


def _log(
    req_id: str,
    method: str,
    url: str,
    fwd_headers: Dict[str, str],
    req_json: Optional[Dict[str, Any]],
    resp_json: Optional[Any],
    status: int,
    duration: float,
    *,
    error: Optional[str] = None,
    traceback: Optional[str] = None,
) -> None:
    """Write a JSON log file to .cache/logs/yymmdd_HH/{seq}.json with structured format."""
    try:
        folder = _get_hour_folder()
        seq = _get_next_sequence(folder)
        log_file = folder / f"{seq}.json"

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "sequence": seq,
            "request": {
                "method": method,
                "upstream_url": url,
                "forwarded_headers": {k: v for k, v in fwd_headers.items() if k.lower() != "authorization"},
                "body": req_json,
            },
            "response": {
                "status_code": status,
                "body": resp_json,
            },
            "duration_s": round(duration, 3),
        }

        if error:
            log_entry["error"] = error
        if traceback:
            log_entry["traceback"] = traceback

        with open(log_file, "w") as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning(f"[{req_id}] failed to write log: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(
    port: int = typer.Option(4343, "--port", "-p", help="Listen port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Listen host"),
    openai_upstream: str = typer.Option(OPENAI_UPSTREAM, "--openai-upstream", "-o", help="OpenAI-compatible upstream base URL"),
    anthropic_upstream: str = typer.Option(ANTHROPIC_UPSTREAM, "--anthropic-upstream", "-a", help="Anthropic-compatible upstream base URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
):
    """Start the passthrough proxy."""
    global OPENAI_UPSTREAM, ANTHROPIC_UPSTREAM
    OPENAI_UPSTREAM = openai_upstream.rstrip("/")
    ANTHROPIC_UPSTREAM = anthropic_upstream.rstrip("/")

    level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=level, colorize=True)

    logger.info(f"Starting passthrough proxy on http://{host}:{port}")
    logger.info(f"  /openai/... → {OPENAI_UPSTREAM}/...")
    logger.info(f"  /anthropic/... → {ANTHROPIC_UPSTREAM}/...")
    key = _get_api_key()
    if key:
        logger.info(f"Default API key: {key[:10]}...")
    else:
        logger.info("No default API key — caller must supply Authorization header")

    uvicorn.run(app, host=host, port=port, log_level=level.lower())


if __name__ == "__main__":
    typer.run(main)

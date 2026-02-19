#!/usr/bin/env python3
import hashlib
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
import fcntl

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse


class ProxyAuthError(Exception):
    def __init__(self, status_code: int, body: dict):
        super().__init__(body.get("error", {}).get("message", "Proxy auth error"))
        self.status_code = status_code
        self.body = body


class BaseCachingProxy:
    def __init__(
        self,
        *,
        title: str,
        openai_upstream: str,
        anthropic_upstream: str,
        cache_dir: Path,
        logger_name: str,
    ) -> None:
        self.openai_upstream = openai_upstream.rstrip("/")
        self.anthropic_upstream = anthropic_upstream.rstrip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._counter_file = self.cache_dir / ".counter"
        self._counter_lock_file = self.cache_dir / ".counter.lock"
        self._index_file = self.cache_dir / ".index.json"
        self._index_lock_file = self.cache_dir / ".index.lock"
        self._counter_file.touch(exist_ok=True)
        self._counter_lock_file.touch(exist_ok=True)
        self._index_file.touch(exist_ok=True)
        self._index_lock_file.touch(exist_ok=True)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.logger = logging.getLogger(logger_name)
        self.app = FastAPI(title=title)
        self._register_routes()

    def _register_routes(self) -> None:
        @self.app.get("/health")
        async def health():
            return {
                "status": "ok",
                "openai_upstream": self.openai_upstream,
                "anthropic_upstream": self.anthropic_upstream,
            }

        @self.app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def proxy_v1_default(request: Request, path: str):
            return await self._proxy(request, path, self.openai_upstream)

        @self.app.api_route("/openai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def proxy_openai(request: Request, path: str):
            normalized_path = path[3:] if path.startswith("v1/") else path
            return await self._proxy(request, normalized_path, self.openai_upstream)

        @self.app.api_route("/anthropic/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def proxy_anthropic(request: Request, path: str):
            return await self._proxy(request, path, self.anthropic_upstream)

    async def provider_headers(self, request: Request, headers: dict[str, str]) -> dict[str, str]:
        return headers

    def _log_exchange(
        self,
        method: str,
        path: str,
        *,
        status: int | None = None,
        stream: bool = False,
        cached: bool = False,
        cache_file: Path | None = None,
    ) -> None:
        self.logger.info(
            json.dumps(
                {
                    "method": method,
                    "path": path,
                    "status_code": status,
                    "stream": stream,
                    "cached": cached,
                    "cache_file": str(cache_file) if cache_file else None,
                },
                ensure_ascii=False,
            )
        )

    def _get_cache_key(self, path: str, body_dict: dict) -> str:
        body_dict.pop("stream", None)
        body_str = json.dumps(body_dict, sort_keys=True)
        return hashlib.md5(f"{path}:{body_str}".encode()).hexdigest()

    @staticmethod
    def _sanitize_name(value: str, default: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
        return cleaned or default

    def _next_cache_count(self) -> int:
        with self._locked_file(self._counter_lock_file):
            raw = self._counter_file.read_text().strip()
            current = int(raw) if raw.isdigit() else 0
            nxt = current + 1
            self._counter_file.write_text(f"{nxt}\n")
            return nxt

    @contextmanager
    def _locked_file(self, lock_file: Path):
        with lock_file.open("w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _load_cache_index(self) -> dict[str, str]:
        raw = self._index_file.read_text().strip()
        if not raw:
            return {}
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {str(k): str(v) for k, v in loaded.items()}

    def _find_existing_cache_file(self, cache_key: str, stream: bool) -> Path | None:
        entry_key = f"{'stream' if stream else 'json'}:{cache_key}"
        with self._locked_file(self._index_lock_file):
            index = self._load_cache_index()
            filename = index.get(entry_key, "")
        if not filename:
            return None
        found = self.cache_dir / filename
        return found if found.exists() else None

    def _register_cache_file(self, cache_key: str, stream: bool, cache_file: Path) -> None:
        entry_key = f"{'stream' if stream else 'json'}:{cache_key}"
        with self._locked_file(self._index_lock_file):
            index = self._load_cache_index()
            index[entry_key] = cache_file.name
            self._index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")

    def _build_named_cache_file(self, path: str, body_dict: dict, stream: bool) -> Path:
        endpoint_raw = path.split("/", 1)[0] if path else "unknown"
        endpoint = self._sanitize_name(endpoint_raw, "unknown")
        model = self._sanitize_name(str(body_dict.get("model", "unknown")), "unknown")
        count = self._next_cache_count()
        suffix = ".stream.json" if stream else ".json"
        return self.cache_dir / f"{endpoint}-{model}-{count}{suffix}"

    @staticmethod
    def _response_headers(raw_headers: httpx.Headers) -> dict[str, str]:
        skip = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length"}
        return {k: v for k, v in raw_headers.items() if k.lower() not in skip}

    @staticmethod
    def _extract_openai_message_from_json(data: object) -> dict:
        message: dict = {"role": "assistant", "content": ""}
        if not isinstance(data, dict):
            return message
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                m = first.get("message")
                if isinstance(m, dict):
                    role = m.get("role")
                    if isinstance(role, str):
                        message["role"] = role
                    content = m.get("content")
                    if isinstance(content, str):
                        message["content"] = content
                    elif isinstance(content, list):
                        parts: list[str] = []
                        for part in content:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                parts.append(part["text"])
                        message["content"] = "".join(parts)
                    if isinstance(m.get("tool_calls"), list):
                        message["tool_calls"] = m["tool_calls"]
                    if isinstance(m.get("reasoning_content"), str):
                        message["reasoning_content"] = m["reasoning_content"]
                    if isinstance(m.get("reasoning"), str):
                        message["reasoning_content"] = m["reasoning"]
                    return message
        return message

    @staticmethod
    def _extract_openai_message_from_sse_text(sse_text: str) -> dict:
        role = "assistant"
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_by_index: dict[int, dict] = {}

        for raw_line in sse_text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                continue
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = event.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    delta = first.get("delta")
                    if isinstance(delta, dict):
                        if isinstance(delta.get("role"), str):
                            role = delta["role"]
                        if isinstance(delta.get("content"), str):
                            content_parts.append(delta["content"])
                        if isinstance(delta.get("reasoning_content"), str):
                            reasoning_parts.append(delta["reasoning_content"])
                        if isinstance(delta.get("reasoning"), str):
                            reasoning_parts.append(delta["reasoning"])
                        tool_calls = delta.get("tool_calls")
                        if isinstance(tool_calls, list):
                            for item in tool_calls:
                                if not isinstance(item, dict):
                                    continue
                                idx = item.get("index", 0)
                                if not isinstance(idx, int):
                                    idx = 0
                                tc = tool_calls_by_index.setdefault(
                                    idx,
                                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                                )
                                if isinstance(item.get("id"), str) and item["id"]:
                                    tc["id"] = item["id"]
                                if isinstance(item.get("type"), str) and item["type"]:
                                    tc["type"] = item["type"]
                                fn = item.get("function")
                                if isinstance(fn, dict):
                                    if isinstance(fn.get("name"), str) and fn["name"]:
                                        tc["function"]["name"] = fn["name"]
                                    if isinstance(fn.get("arguments"), str):
                                        tc["function"]["arguments"] += fn["arguments"]

            if event.get("type") == "content_block_delta":
                delta = event.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                    content_parts.append(delta["text"])

        message: dict = {"role": role, "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tool_calls_by_index:
            ordered = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
            message["tool_calls"] = ordered
        return message

    @staticmethod
    def _sse_from_openai_message(message: dict) -> bytes:
        delta: dict = {"role": message.get("role", "assistant")}
        if isinstance(message.get("content"), str) and message.get("content"):
            delta["content"] = message["content"]
        if isinstance(message.get("reasoning_content"), str) and message.get("reasoning_content"):
            delta["reasoning_content"] = message["reasoning_content"]
        if isinstance(message.get("tool_calls"), list) and message.get("tool_calls"):
            delta["tool_calls"] = message["tool_calls"]
        chunk = {
            "id": "chatcmpl-cache",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": "stop"}],
        }
        return (f"data: {json.dumps(chunk, ensure_ascii=False)}\n\ndata: [DONE]\n\n").encode("utf-8")

    async def _proxy(self, request: Request, path: str, base_url: str):
        url = f"{base_url}/{path}"
        if request.url.query:
            url += f"?{request.url.query}"

        headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
        try:
            headers = await self.provider_headers(request, headers)
        except ProxyAuthError as e:
            self._log_exchange(request.method, path, status=e.status_code)
            return Response(content=json.dumps(e.body), status_code=e.status_code, media_type="application/json")
        except Exception as e:
            body = {"error": {"message": f"Proxy configuration error: {e}", "type": "configuration_error"}}
            self._log_exchange(request.method, path, status=500)
            return Response(content=json.dumps(body), status_code=500, media_type="application/json")

        body_bytes = await request.body()
        try:
            body_dict = json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError:
            body_dict = None

        cache_file = None
        stream_cache_file = None
        is_stream_request = bool(body_dict and body_dict.get("stream") is True)
        payload_for_log = body_dict if body_dict is not None else body_bytes.decode(errors="ignore")

        if body_dict is not None and request.method == "POST":
            cache_key = self._get_cache_key(path, dict(body_dict))
            if is_stream_request:
                stream_cache_file = self._find_existing_cache_file(cache_key, stream=True)
                if stream_cache_file and stream_cache_file.exists():
                    cache_obj = json.loads(stream_cache_file.read_text())
                    cached_message = cache_obj.get("response", {}).get("message", {"role": "assistant", "content": ""})
                    self._log_exchange(
                        request.method,
                        path,
                        status=200,
                        stream=True,
                        cached=True,
                        cache_file=stream_cache_file,
                    )
                    return Response(content=self._sse_from_openai_message(cached_message), media_type="text/event-stream")
                stream_cache_file = self._build_named_cache_file(path, body_dict, stream=True)
            else:
                cache_file = self._find_existing_cache_file(cache_key, stream=False)
                if cache_file and cache_file.exists():
                    cached_content = cache_file.read_bytes()
                    self._log_exchange(
                        request.method,
                        path,
                        status=200,
                        cached=True,
                        cache_file=cache_file,
                    )
                    return Response(content=cached_content, media_type="application/json")
                cache_file = self._build_named_cache_file(path, body_dict, stream=False)
            content = json.dumps(body_dict).encode("utf-8")
        else:
            content = body_bytes

        if is_stream_request:
            req = self.client.build_request(request.method, url, content=content, headers=headers)
            upstream = await self.client.send(req, stream=True)
            stream_chunks: list[bytes] = []

            async def _iter_and_cache():
                try:
                    async for chunk in upstream.aiter_raw():
                        stream_chunks.append(chunk)
                        yield chunk
                finally:
                    await upstream.aclose()
                    sse_text = b"".join(stream_chunks).decode(errors="ignore")
                    response_message = self._extract_openai_message_from_sse_text(sse_text)
                    if upstream.status_code == 200 and stream_cache_file and stream_chunks:
                        stream_cache_file.parent.mkdir(parents=True, exist_ok=True)
                        cache_obj = {
                            "payload": payload_for_log,
                            "response": {"message": response_message},
                        }
                        stream_cache_file.write_text(json.dumps(cache_obj, ensure_ascii=False))
                        self._register_cache_file(cache_key=cache_key, stream=True, cache_file=stream_cache_file)
                    self._log_exchange(
                        request.method,
                        path,
                        status=upstream.status_code,
                        stream=True,
                        cache_file=stream_cache_file if upstream.status_code == 200 else None,
                    )

            return StreamingResponse(
                _iter_and_cache(),
                status_code=upstream.status_code,
                headers=self._response_headers(upstream.headers),
                media_type=upstream.headers.get("content-type"),
            )

        req = self.client.build_request(request.method, url, content=content, headers=headers)
        upstream = await self.client.send(req)

        if upstream.status_code == 200 and cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(upstream.content)
            self._register_cache_file(cache_key=cache_key, stream=False, cache_file=cache_file)

        self._log_exchange(
            request.method,
            path,
            status=upstream.status_code,
            cache_file=cache_file if upstream.status_code == 200 else None,
        )

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=self._response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

#!/usr/bin/env python3
"""
Live Conversations - Interactive Log Visualization Tool

A web-based UI for browsing, searching, and inspecting proxy conversation logs.
Run with: uv run live_conversations.py
Default: http://0.0.0.0:4446
"""

import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "4446"))
LOG_DIR = Path(os.getenv("CACHE_DIR", Path.home() / ".cache" / "conversations_proxy_cache"))

app = FastAPI(title="Live Conversations")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Data Models
class LogSummary(BaseModel):
    filename: str
    path: str
    timestamp: str | None = None
    method: str | None = None
    url: str | None = None
    status_code: int | None = None
    duration: float | None = None
    preview: str | None = None
    model: str | None = None
    total_tokens: int | None = None
    has_reasoning: bool = False
    has_error: bool = False


class LogDetail(BaseModel):
    filename: str
    path: str
    content: dict[str, Any]


# Helper Functions
def get_log_files(limit: int = 100) -> list[Path]:
    """Get log files sorted by modification time (newest first)."""
    if not LOG_DIR.exists():
        return []

    log_files = [f for f in LOG_DIR.rglob("*.json") if f.name != ".index.json"]
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return log_files[:limit]


def extract_preview(body: Any, max_length: int = 100) -> str:
    """Extract a preview string from request body, preferring the last user message."""
    if not body:
        return ""

    if isinstance(body, str):
        return body[:max_length]

    if isinstance(body, dict):
        # Try common fields - find LAST user message (skip system prompts)
        if "messages" in body and body["messages"]:
            # Search from the end for user messages
            for msg in reversed(body["messages"]):
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "")
                if role in ("system", "tool"):
                    continue
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    # Strip XML-like tags for cleaner preview
                    import re
                    clean = re.sub(r"<[^>]+>", "", content).strip()
                    if clean:
                        return clean[:max_length]
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            return item.get("text", "")[:max_length]
        if "prompt" in body:
            prompt = body["prompt"]
            if isinstance(prompt, str):
                return prompt[:max_length]

    return str(body)[:max_length]


def parse_log_file(filepath: Path) -> dict[str, Any]:
    """Parse a log file and return its content."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def summarize_log(filepath: Path) -> LogSummary:
    """Create a summary of a log file."""
    content = parse_log_file(filepath)

    if "payload" in content:
        # New format: {"payload": {model, messages, system, ...}, "response": {"message": {role, content}}}
        from datetime import datetime
        payload = content.get("payload", {})
        response = content.get("response", {})
        message = response.get("message", {})
        model = payload.get("model")
        timestamp = datetime.fromtimestamp(filepath.stat().st_mtime).isoformat()
        has_error = isinstance(message.get("content"), str) and message["content"].startswith("Error")
        has_reasoning = bool(message.get("reasoning_content") or message.get("reasoning"))
        return LogSummary(
            filename=filepath.name,
            path=str(filepath.relative_to(LOG_DIR)),
            timestamp=timestamp,
            method="POST",
            url=None,
            status_code=200,
            duration=None,
            preview=extract_preview(payload),
            model=model,
            total_tokens=None,
            has_reasoning=has_reasoning,
            has_error=has_error,
        )

    # Old format: {"request": {...}, "response": {"body": {...}}}
    request = content.get("request", {})
    response = content.get("response", {})
    response_body = response.get("body", {})

    # Extract model name from request body or response
    model = None
    if isinstance(request.get("body"), dict):
        model = request["body"].get("model")
    if not model and isinstance(response_body, dict):
        last_chunk = response_body.get("last", {})
        if isinstance(last_chunk, dict):
            model = last_chunk.get("model")

    # Extract token usage
    total_tokens = None
    if isinstance(response_body, dict):
        last_chunk = response_body.get("last", {})
        if isinstance(last_chunk, dict):
            usage = last_chunk.get("usage", {})
            if isinstance(usage, dict):
                total_tokens = usage.get("total_tokens")

    # Check for reasoning content
    has_reasoning = bool(
        isinstance(response_body, dict)
        and response_body.get("full_reasoning_content")
    )

    return LogSummary(
        filename=filepath.name,
        path=str(filepath.relative_to(LOG_DIR)),
        timestamp=content.get("timestamp"),
        method=request.get("method"),
        url=request.get("upstream_url"),
        status_code=response.get("status_code"),
        duration=content.get("duration_s"),
        preview=extract_preview(request.get("body")),
        model=model,
        total_tokens=total_tokens,
        has_reasoning=has_reasoning,
        has_error=bool(content.get("error")),
    )


def fuzzy_match(content: str, query: str) -> bool:
    """Simple case-insensitive substring match."""
    return query.lower() in content.lower()


def search_logs(query: str, limit: int = 100) -> list[Path]:
    """Search logs by filename, URL, or content."""
    if not LOG_DIR.exists():
        return []

    log_files = [f for f in LOG_DIR.rglob("*.json") if f.name != ".index.json"]
    matches = []

    for filepath in log_files:
        # Check filename
        if fuzzy_match(filepath.name, query):
            matches.append(filepath)
            continue

        # Check content
        try:
            with open(filepath) as f:
                content = f.read()
            if fuzzy_match(content, query):
                matches.append(filepath)
        except IOError:
            continue

    # Sort by modification time
    matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return matches[:limit]


# API Endpoints
@app.get("/api/logs")
async def list_logs(
    limit: int = Query(default=100, le=1000),
    search: str | None = Query(default=None),
) -> list[LogSummary]:
    """List all logs with optional search."""
    if search:
        files = search_logs(search, limit)
    else:
        files = get_log_files(limit)

    return [summarize_log(f) for f in files]


@app.get("/api/logs/{path:path}")
async def get_log_detail(path: str) -> LogDetail:
    """Get full details of a specific log."""
    filepath = LOG_DIR / path

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Log not found")

    # Security: ensure path is within LOG_DIR
    try:
        filepath.resolve().relative_to(LOG_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    content = parse_log_file(filepath)

    return LogDetail(
        filename=filepath.name,
        path=path,
        content=content,
    )


# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Conversations</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        [v-cloak] { display: none; }
        .scrollbar-thin::-webkit-scrollbar { width: 6px; height: 6px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: #1f2937; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #6b7280; }
        pre[class*="language-"] { margin: 0; border-radius: 0.5rem; }
        code[class*="language-"] { font-size: 0.875rem; }
        .resize-handle { cursor: col-resize; }
        .msg-system { background: #1f2937; border-left: 3px solid #6b7280; }
        .msg-user { background: #1e3a5f; border-left: 3px solid #3b82f6; }
        .msg-assistant { background: #1a3a2a; border-left: 3px solid #22c55e; }
        .msg-tool { background: #3a2a1a; border-left: 3px solid #f59e0b; }
        .msg-reasoning { background: #2a1a3a; border-left: 3px solid #a855f7; }
        .prose pre { background: #111827; border-radius: 0.5rem; padding: 1rem; overflow-x: auto; }
        .prose code { font-size: 0.875rem; }
        .prose p { margin-bottom: 0.5rem; }
        .prose ul, .prose ol { margin-bottom: 0.5rem; padding-left: 1.5rem; }
        .prose li { margin-bottom: 0.25rem; }
        .prose h1, .prose h2, .prose h3 { margin-top: 1rem; margin-bottom: 0.5rem; font-weight: 600; }
        .fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
        .fade-enter-from, .fade-leave-to { opacity: 0; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    <div id="app" v-cloak class="flex h-screen overflow-hidden">
        <!-- Left Panel: Log List -->
        <div
            class="flex flex-col bg-gray-800 border-r border-gray-700 flex-shrink-0"
            :style="{ width: sidebarWidth + 'px' }"
            :class="{ 'hidden': isMobile && showDetail }"
        >
            <!-- Header -->
            <div class="p-4 border-b border-gray-700">
                <h1 class="text-xl font-bold text-white mb-3">Live Conversations</h1>
                <input
                    v-model="searchQuery"
                    @input="debouncedSearch"
                    type="text"
                    placeholder="Search logs..."
                    class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-blue-500"
                />
            </div>

            <!-- Log List -->
            <div class="flex-1 overflow-y-auto scrollbar-thin">
                <div
                    v-for="log in logs"
                    :key="log.path"
                    @click="selectLog(log)"
                    class="p-3 border-b border-gray-700 cursor-pointer hover:bg-gray-700 transition-colors"
                    :class="{ 'bg-gray-700 border-l-4 border-l-blue-500': selectedLog?.path === log.path }"
                >
                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                        <span
                            class="px-2 py-0.5 text-xs font-bold rounded"
                            :class="getMethodColor(log.method)"
                        >{{ log.method || 'N/A' }}</span>
                        <span
                            class="px-2 py-0.5 text-xs font-bold rounded"
                            :class="getStatusColor(log.status_code)"
                        >{{ log.status_code || 'N/A' }}</span>
                        <span v-if="log.model" class="px-1.5 py-0.5 text-xs rounded bg-gray-600 text-gray-300">{{ log.model }}</span>
                        <span v-if="log.has_reasoning" class="px-1.5 py-0.5 text-xs rounded bg-purple-900 text-purple-300" title="Has reasoning content">🧠</span>
                        <span v-if="log.has_error" class="px-1.5 py-0.5 text-xs rounded bg-red-900 text-red-300">⚠</span>
                        <span v-if="log.duration" class="text-xs text-gray-400 ml-auto">{{ log.duration.toFixed(2) }}s</span>
                    </div>
                    <div v-if="log.preview" class="text-sm text-gray-200 truncate mt-1">{{ log.preview }}</div>
                    <div class="flex items-center gap-2 mt-1">
                        <span v-if="log.total_tokens" class="text-xs text-gray-500">{{ formatTokens(log.total_tokens) }} tok</span>
                        <span v-if="log.timestamp" class="text-xs text-gray-500 ml-auto" :title="formatTime(log.timestamp)">{{ relativeTime(log.timestamp) }}</span>
                    </div>
                </div>
            </div>

            <!-- Footer -->
            <div class="p-3 border-t border-gray-700 text-xs text-gray-500 text-center">
                {{ logs.length }} logs | Auto-refresh: {{ autoRefresh ? 'ON' : 'OFF' }}
            </div>
        </div>

        <!-- Resize Handle (desktop only) -->
        <div
            v-if="!isMobile"
            class="w-1 bg-gray-700 hover:bg-blue-500 transition-colors resize-handle flex-shrink-0"
            @mousedown="startResize"
        ></div>

        <!-- Right Panel: Detail View -->
        <div
            class="flex-1 flex flex-col overflow-hidden min-w-0"
            :class="{ 'hidden': isMobile && !showDetail }"
        >
            <!-- Mobile back button -->
            <div v-if="isMobile && showDetail" class="p-2 border-b border-gray-700 bg-gray-800">
                <button @click="showDetail = false" class="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded text-gray-300">
                    ← Back to list
                </button>
            </div>

            <!-- Detail Header -->
            <div v-if="selectedLog" class="p-4 border-b border-gray-700 bg-gray-800">
                <div class="flex items-center justify-between flex-wrap gap-2">
                    <div class="flex items-center gap-3 flex-wrap">
                        <span
                            class="px-2 py-1 text-sm font-bold rounded"
                            :class="getMethodColor(selectedLog.method)"
                        >{{ selectedLog.method }}</span>
                        <span
                            class="px-2 py-1 text-sm font-bold rounded"
                            :class="getStatusColor(selectedLog.status_code)"
                        >{{ selectedLog.status_code }}</span>
                        <span class="text-gray-400 text-sm">{{ selectedLog.path }}</span>
                    </div>
                    <div class="flex gap-2">
                        <button
                            @click="viewMode = 'chat'"
                            class="px-3 py-1 text-sm rounded transition-colors"
                            :class="viewMode === 'chat' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'"
                        >Chat</button>
                        <button
                            @click="viewMode = 'json'"
                            class="px-3 py-1 text-sm rounded transition-colors"
                            :class="viewMode === 'json' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'"
                        >JSON</button>
                    </div>
                </div>

                <!-- Metadata bar -->
                <div v-if="metadata" class="flex items-center gap-4 mt-2 text-xs text-gray-400 flex-wrap">
                    <span v-if="metadata.model" class="flex items-center gap-1">
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a8 8 0 100 16 8 8 0 000-16zM8 12a2 2 0 114 0 2 2 0 01-4 0zm2-6a1 1 0 011 1v3a1 1 0 11-2 0V7a1 1 0 011-1z"/></svg>
                        {{ metadata.model }}
                    </span>
                    <span v-if="metadata.promptTokens" class="flex items-center gap-1">
                        ↗ {{ formatTokens(metadata.promptTokens) }} prompt
                    </span>
                    <span v-if="metadata.completionTokens" class="flex items-center gap-1">
                        ↙ {{ formatTokens(metadata.completionTokens) }} completion
                    </span>
                    <span v-if="metadata.cachedTokens" class="flex items-center gap-1 text-green-400">
                        ♻ {{ formatTokens(metadata.cachedTokens) }} cached
                    </span>
                    <span v-if="selectedLog.duration" class="flex items-center gap-1">
                        ⏱ {{ selectedLog.duration.toFixed(2) }}s
                    </span>
                </div>
            </div>

            <!-- Detail Content -->
            <div class="flex-1 overflow-y-auto scrollbar-thin p-4">
                <div v-if="!selectedLog" class="flex items-center justify-center h-full text-gray-500">
                    <div class="text-center">
                        <div class="text-4xl mb-3">💬</div>
                        <p>Select a log to view details</p>
                    </div>
                </div>

                <!-- Chat View -->
                <div v-else-if="viewMode === 'chat'" class="space-y-3 max-w-4xl mx-auto">
                    <!-- Error Display -->
                    <div v-if="logDetail?.content?.error" class="p-4 bg-red-900/50 border border-red-700 rounded-lg">
                        <h3 class="text-red-400 font-bold mb-2">⚠ Error</h3>
                        <pre class="text-red-300 text-sm whitespace-pre-wrap">{{ logDetail.content.error }}</pre>
                    </div>

                    <!-- Messages with proper role colors -->
                    <div v-for="(msg, idx) in chatMessages" :key="'msg-' + idx">
                        <!-- System Message (collapsed by default) -->
                        <div v-if="msg.role === 'system'" class="msg-system p-3 rounded-lg">
                            <div class="flex items-center justify-between cursor-pointer" @click="toggleCollapse('system-' + idx)">
                                <div class="flex items-center gap-2">
                                    <span class="text-gray-400 text-xs font-bold uppercase px-1.5 py-0.5 bg-gray-700 rounded">System</span>
                                    <span class="text-gray-500 text-xs">{{ msg.content.length.toLocaleString() }} chars</span>
                                </div>
                                <span class="text-gray-500 text-xs">{{ isCollapsed('system-' + idx) ? '▶ Show' : '▼ Hide' }}</span>
                            </div>
                            <div v-if="!isCollapsed('system-' + idx)" class="mt-2 text-gray-300 text-sm whitespace-pre-wrap max-h-96 overflow-y-auto scrollbar-thin">{{ msg.content }}</div>
                            <div v-else class="mt-1 text-gray-500 text-xs truncate">{{ msg.content.substring(0, 150) }}...</div>
                        </div>

                        <!-- User Message -->
                        <div v-else-if="msg.role === 'user'" class="msg-user p-3 rounded-lg">
                            <div class="text-blue-400 text-xs font-bold uppercase mb-2 px-1.5 py-0.5 bg-blue-900/50 rounded inline-block">User</div>
                            <div v-if="msg.type === 'text'" class="text-gray-100 prose prose-invert max-w-none text-sm" v-html="renderMarkdown(msg.content)"></div>
                            <div v-else-if="msg.type === 'image'" class="inline-block">
                                <img :src="msg.content" class="max-w-md rounded border border-gray-600" />
                            </div>
                        </div>

                        <!-- Assistant Message -->
                        <div v-else-if="msg.role === 'assistant'" class="msg-assistant p-3 rounded-lg">
                            <div class="text-green-400 text-xs font-bold uppercase mb-2 px-1.5 py-0.5 bg-green-900/50 rounded inline-block">Assistant</div>
                            <!-- Inline reasoning block -->
                            <div v-if="msg.reasoning_content" class="msg-reasoning p-2 rounded mb-2">
                                <div class="flex items-center justify-between cursor-pointer" @click="toggleCollapse('msg-reasoning-' + idx)">
                                    <div class="flex items-center gap-2">
                                        <span class="text-purple-400 text-xs font-bold uppercase px-1.5 py-0.5 bg-purple-900/50 rounded">🧠 Reasoning</span>
                                        <span class="text-gray-500 text-xs">{{ msg.reasoning_content.length.toLocaleString() }} chars</span>
                                    </div>
                                    <span class="text-gray-500 text-xs">{{ isCollapsed('msg-reasoning-' + idx) ? '▶ Show' : '▼ Hide' }}</span>
                                </div>
                                <div v-if="!isCollapsed('msg-reasoning-' + idx)" class="mt-2 text-purple-200 text-sm prose prose-invert max-w-none" v-html="renderMarkdown(msg.reasoning_content)"></div>
                                <div v-else class="mt-1 text-gray-500 text-xs truncate">{{ msg.reasoning_content.substring(0, 200) }}...</div>
                            </div>
                            <!-- Tool calls -->
                            <div v-if="msg.tool_calls && msg.tool_calls.length" class="space-y-2">
                                <div v-if="msg.content" class="text-gray-100 prose prose-invert max-w-none text-sm mb-2" v-html="renderMarkdown(msg.content)"></div>
                                <div v-for="(tc, tIdx) in msg.tool_calls" :key="'tc-' + tIdx" class="bg-gray-800/50 rounded p-2 text-sm">
                                    <div class="flex items-center gap-2 mb-1">
                                        <span class="text-yellow-400 font-mono text-xs">🔧 {{ tc.function?.name || 'unknown' }}</span>
                                        <span class="text-gray-600 text-xs">{{ tc.id?.substring(0, 12) }}...</span>
                                    </div>
                                    <div class="text-gray-400 text-xs font-mono cursor-pointer" @click="toggleCollapse('tc-' + idx + '-' + tIdx)">
                                        <span v-if="isCollapsed('tc-' + idx + '-' + tIdx)">▶ Arguments (click to expand)</span>
                                        <span v-else>▼ Arguments</span>
                                    </div>
                                    <pre v-if="!isCollapsed('tc-' + idx + '-' + tIdx)" class="text-gray-300 text-xs mt-1 whitespace-pre-wrap max-h-48 overflow-y-auto scrollbar-thin">{{ formatToolArgs(tc.function?.arguments) }}</pre>
                                </div>
                            </div>
                            <div v-else class="text-gray-100 prose prose-invert max-w-none text-sm" v-html="renderMarkdown(msg.content || '')"></div>
                        </div>

                        <!-- Tool Result -->
                        <div v-else-if="msg.role === 'tool'" class="msg-tool p-3 rounded-lg">
                            <div class="flex items-center gap-2 mb-2">
                                <span class="text-amber-400 text-xs font-bold uppercase px-1.5 py-0.5 bg-amber-900/50 rounded">Tool Result</span>
                                <span v-if="msg.tool_call_id" class="text-gray-600 text-xs font-mono">{{ msg.tool_call_id?.substring(0, 16) }}...</span>
                            </div>
                            <div class="cursor-pointer" @click="toggleCollapse('tool-' + idx)">
                                <span class="text-gray-500 text-xs">{{ isCollapsed('tool-' + idx) ? '▶ Show result' : '▼ Hide result' }} ({{ msg.content?.length?.toLocaleString() || 0 }} chars)</span>
                            </div>
                            <div v-if="!isCollapsed('tool-' + idx)" class="mt-2 text-gray-300 text-sm whitespace-pre-wrap max-h-64 overflow-y-auto scrollbar-thin font-mono text-xs">{{ msg.content }}</div>
                        </div>
                    </div>

                    <!-- Reasoning Content (from response) -->
                    <div v-if="reasoningContent" class="msg-reasoning p-3 rounded-lg">
                        <div class="flex items-center justify-between cursor-pointer" @click="toggleCollapse('reasoning')">
                            <div class="flex items-center gap-2">
                                <span class="text-purple-400 text-xs font-bold uppercase px-1.5 py-0.5 bg-purple-900/50 rounded">🧠 Reasoning</span>
                                <span class="text-gray-500 text-xs">{{ reasoningContent.length.toLocaleString() }} chars</span>
                            </div>
                            <span class="text-gray-500 text-xs">{{ isCollapsed('reasoning') ? '▶ Show' : '▼ Hide' }}</span>
                        </div>
                        <div v-if="!isCollapsed('reasoning')" class="mt-2 text-purple-200 text-sm prose prose-invert max-w-none" v-html="renderMarkdown(reasoningContent)"></div>
                        <div v-else class="mt-1 text-gray-500 text-xs truncate">{{ reasoningContent.substring(0, 200) }}...</div>
                    </div>

                    <!-- Model Response -->
                    <div v-if="responseText" class="msg-assistant p-4 rounded-lg">
                        <div class="text-green-400 text-xs font-bold uppercase mb-2 px-1.5 py-0.5 bg-green-900/50 rounded inline-block">Model Response</div>
                        <div class="text-gray-100 prose prose-invert max-w-none" v-html="renderMarkdown(responseText)"></div>
                    </div>

                    <!-- Streaming Info -->
                    <div v-if="sseChunks" class="p-3 bg-gray-800 rounded-lg text-gray-400 text-sm flex items-center gap-2">
                        <span class="text-yellow-400">📡</span>
                        <span>Streamed response: <strong>{{ sseChunks }}</strong> chunks</span>
                    </div>
                </div>

                <!-- JSON View -->
                <div v-else-if="viewMode === 'json'" class="bg-gray-800 rounded-lg max-w-5xl mx-auto">
                    <pre class="!bg-transparent"><code class="language-json">{{ formattedJson }}</code></pre>
                </div>
            </div>
        </div>
    </div>

    <script>
    const { createApp, ref, computed, watch, onMounted, onUnmounted, reactive } = Vue;

    createApp({
        setup() {
            const logs = ref([]);
            const selectedLog = ref(null);
            const logDetail = ref(null);
            const searchQuery = ref('');
            const viewMode = ref('chat');
            const autoRefresh = ref(true);
            const sidebarWidth = ref(350);
            const showDetail = ref(false);
            const isMobile = ref(window.innerWidth < 768);
            const collapsedSections = reactive({});

            // Default collapsed sections
            collapsedSections['reasoning'] = true;

            let refreshInterval = null;
            let searchTimeout = null;

            // Handle responsive
            const handleResize = () => {
                isMobile.value = window.innerWidth < 768;
                if (!isMobile.value) {
                    showDetail.value = false;
                }
            };

            // Collapse management
            const toggleCollapse = (key) => {
                collapsedSections[key] = !collapsedSections[key];
            };

            const isCollapsed = (key) => {
                // System messages and tool results default collapsed
                if (!(key in collapsedSections)) {
                    if (key.startsWith('system-') || key.startsWith('tool-') || key.startsWith('tc-') || key === 'reasoning') {
                        collapsedSections[key] = true;
                        return true;
                    }
                    return false;
                }
                return collapsedSections[key];
            };

            // Fetch logs
            const fetchLogs = async () => {
                try {
                    const params = new URLSearchParams();
                    params.append('limit', '100');
                    if (searchQuery.value) {
                        params.append('search', searchQuery.value);
                    }
                    const res = await fetch(`/api/logs?${params}`);
                    logs.value = await res.json();
                } catch (e) {
                    console.error('Failed to fetch logs:', e);
                }
            };

            // Fetch log detail
            const fetchLogDetail = async (path) => {
                try {
                    const res = await fetch(`/api/logs/${encodeURIComponent(path)}`);
                    logDetail.value = await res.json();
                    setTimeout(() => {
                        if (viewMode.value === 'json') {
                            Prism.highlightAll();
                        }
                    }, 0);
                } catch (e) {
                    console.error('Failed to fetch log detail:', e);
                    logDetail.value = null;
                }
            };

            // Select a log
            const selectLog = (log) => {
                selectedLog.value = log;
                fetchLogDetail(log.path);
                if (isMobile.value) {
                    showDetail.value = true;
                }
            };

            // Debounced search
            const debouncedSearch = () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    fetchLogs();
                    autoRefresh.value = !searchQuery.value;
                }, 300);
            };

            // Color helpers
            const getMethodColor = (method) => {
                const colors = {
                    GET: 'bg-green-600',
                    POST: 'bg-blue-600',
                    PUT: 'bg-yellow-600',
                    DELETE: 'bg-red-600',
                    PATCH: 'bg-purple-600',
                };
                return colors[method] || 'bg-gray-600';
            };

            const getStatusColor = (code) => {
                if (!code) return 'bg-gray-600';
                if (code >= 200 && code < 300) return 'bg-green-600';
                if (code >= 400 && code < 500) return 'bg-yellow-600';
                if (code >= 500) return 'bg-red-600';
                return 'bg-gray-600';
            };

            // Time formatters
            const formatTime = (timestamp) => {
                if (!timestamp) return '';
                const d = new Date(timestamp);
                return d.toLocaleString();
            };

            const relativeTime = (timestamp) => {
                if (!timestamp) return '';
                const now = new Date();
                const d = new Date(timestamp);
                const diff = Math.floor((now - d) / 1000);
                if (diff < 60) return diff + 's ago';
                if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
                if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
                return Math.floor(diff / 86400) + 'd ago';
            };

            const formatTokens = (n) => {
                if (!n) return '';
                if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
                return n.toString();
            };

            // Markdown renderer
            const renderMarkdown = (text) => {
                if (!text) return '';
                try {
                    return marked.parse(text);
                } catch (e) {
                    return text;
                }
            };

            // Format tool call arguments
            const formatToolArgs = (args) => {
                if (!args) return '';
                try {
                    const parsed = typeof args === 'string' ? JSON.parse(args) : args;
                    return JSON.stringify(parsed, null, 2);
                } catch {
                    return args;
                }
            };

            // Extract all chat messages with proper roles
            const chatMessages = computed(() => {
                const content = logDetail.value?.content;
                if (!content) return [];

                // New format: content.payload has messages + optional system
                // Old format: content.request.body has messages
                let body = null;
                let systemPrompt = null;
                if (content.payload) {
                    body = content.payload;
                    if (body.system) {
                        systemPrompt = typeof body.system === 'string' ? body.system : JSON.stringify(body.system);
                    }
                } else if (content.request?.body) {
                    body = content.request.body;
                } else {
                    return [];
                }

                const messages = [];

                // Prepend system from payload.system (new format)
                if (systemPrompt) {
                    messages.push({ role: 'system', type: 'text', content: systemPrompt });
                }

                // OpenAI messages format
                if (body.messages && Array.isArray(body.messages)) {
                    for (const msg of body.messages) {
                        const role = msg.role || 'user';

                        if (role === 'assistant' && msg.tool_calls) {
                            messages.push({
                                role: 'assistant',
                                type: 'text',
                                content: msg.content || '',
                                tool_calls: msg.tool_calls,
                                reasoning_content: msg.reasoning_content || msg.reasoning || null,
                            });
                        } else if (role === 'tool') {
                            messages.push({
                                role: 'tool',
                                type: 'text',
                                content: msg.content || '',
                                tool_call_id: msg.tool_call_id,
                            });
                        } else if (role === 'system') {
                            messages.push({
                                role: 'system',
                                type: 'text',
                                content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
                            });
                        } else {
                            // user or assistant without tool_calls
                            const content = msg.content;
                            if (typeof content === 'string') {
                                messages.push({ role, type: 'text', content, reasoning_content: msg.reasoning_content || msg.reasoning || null });
                            } else if (Array.isArray(content)) {
                                // Multi-modal content (Anthropic format)
                                for (const item of content) {
                                    if (item.type === 'text') {
                                        messages.push({ role, type: 'text', content: item.text });
                                    } else if (item.type === 'image' && item.source?.data) {
                                        const dataUrl = `data:${item.source.media_type || 'image/png'};base64,${item.source.data}`;
                                        messages.push({ role, type: 'image', content: dataUrl });
                                    }
                                }
                            }
                        }
                    }
                }
                // Legacy prompt format
                else if (body.prompt) {
                    messages.push({ role: 'user', type: 'text', content: body.prompt });
                }

                return messages;
            });

            // Extract reasoning content
            const reasoningContent = computed(() => {
                const content = logDetail.value?.content;
                if (!content) return '';
                // New format: response.message.reasoning_content
                if (content.response?.message?.reasoning_content) {
                    return content.response.message.reasoning_content;
                }
                // Old format: response.body.full_reasoning_content
                if (content.response?.body) {
                    return content.response.body.full_reasoning_content || '';
                }
                return '';
            });

            // Extract response text
            const responseText = computed(() => {
                if (!logDetail.value?.content?.response) return '';
                const response = logDetail.value.content.response;

                // New format: response.message.content
                if (response.message) {
                    const content = response.message.content;
                    if (typeof content === 'string') return content;
                    if (Array.isArray(content)) {
                        return content.filter(c => c.type === 'text').map(c => c.text).join('\\n\\n');
                    }
                }

                // Old format: response.body.*
                const body = response.body;
                if (!body) return '';
                if (body.full_response_text) return body.full_response_text;
                if (body.choices?.[0]?.message?.content) return body.choices[0].message.content;
                if (body.choices?.[0]?.text) return body.choices[0].text;

                if (body.content && Array.isArray(body.content)) {
                    const texts = body.content.filter(c => c.type === 'text').map(c => c.text);
                    if (texts.length > 0) return texts.join('\\n\\n');
                }

                if (typeof body === 'string') return body;
                // Don't show raw JSON for streaming responses
                if (body._sse_chunks && !body.full_response_text) return '';
                return JSON.stringify(body, null, 2);
            });

            // SSE chunks info (old format only)
            const sseChunks = computed(() => {
                const body = logDetail.value?.content?.response?.body;
                return body?._sse_chunks || null;
            });

            // Metadata
            const metadata = computed(() => {
                if (!logDetail.value?.content) return null;
                const content = logDetail.value.content;

                // New format
                if (content.payload) {
                    const model = content.payload.model || null;
                    return { model, promptTokens: null, completionTokens: null, totalTokens: null, cachedTokens: null };
                }

                // Old format
                const respBody = content.response?.body || {};
                const reqBody = content.request?.body || {};
                const lastChunk = respBody.last || {};
                const usage = lastChunk.usage || {};

                return {
                    model: reqBody.model || lastChunk.model || null,
                    promptTokens: usage.prompt_tokens || null,
                    completionTokens: usage.completion_tokens || null,
                    totalTokens: usage.total_tokens || null,
                    cachedTokens: usage.prompt_tokens_details?.cached_tokens || null,
                };
            });

            // Formatted JSON
            const formattedJson = computed(() => {
                if (!logDetail.value?.content) return '';
                return JSON.stringify(logDetail.value.content, null, 2);
            });

            // Resize sidebar
            let isResizing = false;
            const startResize = (e) => {
                isResizing = true;
                document.addEventListener('mousemove', doResize);
                document.addEventListener('mouseup', stopResize);
            };

            const doResize = (e) => {
                if (!isResizing) return;
                const newWidth = e.clientX;
                if (newWidth >= 250 && newWidth <= 600) {
                    sidebarWidth.value = newWidth;
                }
            };

            const stopResize = () => {
                isResizing = false;
                document.removeEventListener('mousemove', doResize);
                document.removeEventListener('mouseup', stopResize);
            };

            // Keyboard navigation
            const handleKeydown = (e) => {
                if (e.key === 'Escape') {
                    if (isMobile.value && showDetail.value) {
                        showDetail.value = false;
                    }
                }
                if (e.key === 'ArrowDown' && !e.target.closest('input')) {
                    e.preventDefault();
                    const currentIdx = logs.value.findIndex(l => l.path === selectedLog.value?.path);
                    if (currentIdx < logs.value.length - 1) {
                        selectLog(logs.value[currentIdx + 1]);
                    }
                }
                if (e.key === 'ArrowUp' && !e.target.closest('input')) {
                    e.preventDefault();
                    const currentIdx = logs.value.findIndex(l => l.path === selectedLog.value?.path);
                    if (currentIdx > 0) {
                        selectLog(logs.value[currentIdx - 1]);
                    }
                }
            };

            // Auto-refresh
            onMounted(() => {
                fetchLogs();
                refreshInterval = setInterval(() => {
                    if (autoRefresh.value && !searchQuery.value) {
                        fetchLogs();
                    }
                }, 5000);
                window.addEventListener('resize', handleResize);
                window.addEventListener('keydown', handleKeydown);
            });

            onUnmounted(() => {
                clearInterval(refreshInterval);
                clearTimeout(searchTimeout);
                window.removeEventListener('resize', handleResize);
                window.removeEventListener('keydown', handleKeydown);
            });

            // Re-highlight when view mode changes
            watch(viewMode, () => {
                setTimeout(() => Prism.highlightAll(), 0);
            });

            return {
                logs, selectedLog, logDetail, searchQuery, viewMode,
                autoRefresh, sidebarWidth, showDetail, isMobile,
                selectLog, debouncedSearch,
                getMethodColor, getStatusColor, formatTime, relativeTime, formatTokens,
                renderMarkdown, formatToolArgs,
                chatMessages, reasoningContent, responseText, sseChunks,
                metadata, formattedJson, startResize,
                toggleCollapse, isCollapsed,
            };
        }
    }).mount('#app');
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the embedded Vue.js frontend."""
    return HTML_TEMPLATE


@app.get("/favicon.ico")
async def favicon():
    """Serve inline SVG favicon."""
    from fastapi.responses import Response

    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <rect width="100" height="100" rx="20" fill="#3B82F6"/>
    <path d="M25 35h50v25a10 10 0 01-10 10H35a10 10 0 01-10-10V35z" fill="#fff" opacity="0.9"/>
    <circle cx="38" cy="48" r="4" fill="#3B82F6"/>
    <circle cx="50" cy="48" r="4" fill="#3B82F6"/>
    <circle cx="62" cy="48" r="4" fill="#3B82F6"/>
    <path d="M35 60l-10 12v-12z" fill="#fff" opacity="0.9"/>
    </svg>"""
    return Response(content=svg, media_type="image/svg+xml")


if __name__ == "__main__":
    print(f"Starting Live Conversations at http://{HOST}:{PORT}")
    print(f"Watching logs in: {LOG_DIR.absolute()}")
    uvicorn.run(app, host=HOST, port=PORT)

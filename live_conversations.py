#!/usr/bin/env python3
"""
Live Log Visualizer for Proxy Logs.

Usage:
  uv run live_conversations.py

Features:
  - Lists logs from .cache/logs sorted by latest first
  - Fuzzy search across filenames and content snippets
  - Beautiful split-view UI (list on left, details on right)
  - JSON syntax highlighting and Markdown rendering
  - Auto-refresh support
"""

import json
import os
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOG_DIR = Path(".cache/logs")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 4446))

app = FastAPI(title="Log Visualizer", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
class LogSummary(BaseModel):
    id: str  # path relative to LOG_DIR
    timestamp: str
    method: str
    url: str
    status: int
    duration: float
    preview: str

class LogDetail(BaseModel):
    id: str
    content: Dict[str, Any]

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/api/logs", response_model=List[LogSummary])
async def list_logs(limit: int = 100, search: Optional[str] = None):
    """List recent logs, optionally filtered."""
    files = []
    # Walk through the directory structure: .cache/logs/YYMMDD_HH/*.json
    # We want to be efficient, so we'll look at the most recent directories first if possible
    # But for simplicity, let's glob all json files
    
    pattern = str(LOG_DIR / "**" / "*.json")
    all_files = glob.glob(pattern, recursive=True)
    
    # Sort by modification time, newest first
    all_files.sort(key=os.path.getmtime, reverse=True)
    
    results = []
    count = 0
    
    for f in all_files:
        if count >= limit and not search:
            break
            
        try:
            path = Path(f)
            rel_path = path.relative_to(LOG_DIR)
            
            # Peek at content for basic metadata without full parse if possible, 
            # but we need JSON fields.
            with open(f, "r", encoding="utf-8") as file:
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    continue
                
                # Check search query if present
                if search:
                    search_lower = search.lower()
                    haystack = f"{rel_path} {data.get('request', {}).get('upstream_url', '')} {json.dumps(data)}"
                    if search_lower not in haystack.lower():
                        continue

                results.append(LogSummary(
                    id=str(rel_path),
                    timestamp=data.get("timestamp", datetime.fromtimestamp(os.path.getmtime(f)).isoformat()),
                    method=data.get("request", {}).get("method", "???"),
                    url=data.get("request", {}).get("upstream_url", "unknown"),
                    status=data.get("response", {}).get("status_code", 0),
                    duration=data.get("duration_s", 0.0),
                    preview=str(data.get("request", {}).get("body", ""))[:100]
                ))
                count += 1
        except Exception as e:
            print(f"Error reading {f}: {e}")
            continue
            
    return results

@app.get("/api/logs/{path:path}", response_model=LogDetail)
async def get_log(path: str):
    """Get full details of a specific log file."""
    full_path = LOG_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Log not found")
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return LogDetail(id=path, content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Conversations</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <!-- Prism for synthax highlighting -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-markdown.min.js"></script>
    <!-- Marked for Markdown rendering -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    
    <style>
        body { background-color: #0f172a; color: #e2e8f0; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
        pre { background: #1e293b !important; border-radius: 0.5rem; padding: 1rem; margin: 0; }
        .markdown-body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }
        .markdown-body pre { background-color: #1e293b; padding: 16px; border-radius: 6px; overflow: auto; }
        .markdown-body code { font-family: ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace; font-size: 85%; }
        /* JSON viewer styling */
        .key { color: #9cdcfe; }
        .string { color: #ce9178; }
        .number { color: #b5cea8; }
        .boolean { color: #569cd6; }
        .null { color: #569cd6; }
    </style>
</head>
<body class="h-screen flex flex-col overflow-hidden">
    <div id="app" class="h-full flex flex-col">
        <!-- Header -->
        <header class="bg-slate-900 border-b border-slate-700 p-4 flex justify-between items-center shadow-md z-10">
            <div class="flex items-center gap-3">
                <div class="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
                <h1 class="text-xl font-bold text-white tracking-wide">Live Conversations <span class="text-slate-500 text-sm font-normal">v1.0</span></h1>
            </div>
            
            <div class="flex items-center gap-4">
                 <div class="relative">
                    <input 
                        v-model="searchQuery" 
                        @input="debouncedSearch"
                        type="text" 
                        placeholder="Fuzzy search logs..." 
                        class="bg-slate-800 border border-slate-600 text-white px-4 py-1.5 rounded-full text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                    >
                    <span v-if="loading" class="absolute right-3 top-2 w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
                </div>
                <button @click="fetchLogs" class="p-2 hover:bg-slate-800 rounded-full transition-colors" title="Refresh">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>
        </header>

        <!-- Main Content -->
        <div class="flex-1 flex overflow-hidden">
            <!-- Sidebar List -->
            <div class="w-1/3 min-w-[300px] max-w-[500px] border-r border-slate-700 bg-slate-900 flex flex-col">
                <div class="p-2 border-b border-slate-800 text-xs font-semibold text-slate-500 uppercase tracking-wider flex justify-between">
                    <span>Recent Activity</span>
                    <span>{{ logs.length }} items</span>
                </div>
                <div class="flex-1 overflow-y-auto custom-scrollbar">
                    <div v-if="logs.length === 0 && !loading" class="p-8 text-center text-slate-500">
                        No logs found matching your criteria.
                    </div>
                    
                    <div 
                        v-for="log in logs" 
                        :key="log.id"
                        @click="selectLog(log)"
                        class="cursor-pointer border-b border-slate-800 p-4 hover:bg-slate-800 transition-colors duration-150 group relative"
                        :class="{'bg-slate-800 border-l-4 border-l-blue-500': selectedLog?.id === log.id, 'border-l-4 border-l-transparent': selectedLog?.id !== log.id}"
                    >
                        <div class="flex justify-between items-start mb-1">
                            <span 
                                class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                                :class="{
                                    'bg-green-900 text-green-300': log.method === 'GET',
                                    'bg-blue-900 text-blue-300': log.method === 'POST',
                                    'bg-yellow-900 text-yellow-300': log.method === 'PUT',
                                    'bg-red-900 text-red-300': log.method === 'DELETE'
                                }"
                            >{{ log.method }}</span>
                            <span class="text-xs text-slate-500 font-mono">{{ formatTime(log.timestamp) }}</span>
                        </div>
                        
                        <div class="font-mono text-sm text-slate-300 truncate mb-1" :title="log.url">
                            {{ formatUrl(log.url) }}
                        </div>
                        
                        <div class="flex justify-between items-end">
                            <span 
                                class="text-xs font-mono"
                                :class="statusColor(log.status)"
                            >
                                {{ log.status }}
                            </span>
                            <span class="text-[10px] text-slate-600">{{ log.duration.toFixed(3) }}s</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Detail View -->
            <div class="flex-1 bg-slate-900 flex flex-col overflow-hidden relative">
                <div v-if="!selectedLog" class="flex-1 flex flex-col items-center justify-center text-slate-600">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mb-4 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p class="text-lg">Select a log entry to view details</p>
                </div>

                <div v-else class="flex-1 flex flex-col overflow-hidden">
                    <!-- Detail Header -->
                    <div class="bg-slate-800 p-4 border-b border-slate-700 shadow-sm">
                         <div class="flex items-center gap-3 mb-2">
                             <span 
                                class="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider text-white"
                                :class="{
                                    'bg-green-600': selectedDetail?.content?.request?.method === 'GET',
                                    'bg-blue-600': selectedDetail?.content?.request?.method === 'POST',
                                    'bg-yellow-600': selectedDetail?.content?.request?.method === 'PUT',
                                    'bg-red-600': selectedDetail?.content?.request?.method === 'DELETE'
                                }"
                            >{{ selectedDetail?.content?.request?.method }}</span>
                            <span 
                                class="text-sm font-bold px-2 py-0.5 rounded"
                                :class="statusBadge(selectedDetail?.content?.response?.status_code)"
                            >
                                {{ selectedDetail?.content?.response?.status_code }}
                            </span>
                            <span class="text-xs text-slate-400 font-mono">{{ selectedDetail?.id }}</span>
                         </div>
                         <div class="font-mono text-sm text-blue-300 break-all">
                             {{ selectedDetail?.content?.request?.upstream_url }}
                         </div>
                    </div>

                    <!-- Content Tabs -->
                    <div class="flex border-b border-slate-700 bg-slate-900">
                        <button 
                            @click="activeTab = 'chat'" 
                            class="px-6 py-2 text-sm font-medium transition-colors border-b-2"
                            :class="activeTab === 'chat' ? 'border-blue-500 text-blue-400 bg-slate-800' : 'border-transparent text-slate-400 hover:text-slate-200'"
                        >
                            Chat View
                        </button>
                        <button 
                            @click="activeTab = 'json'" 
                            class="px-6 py-2 text-sm font-medium transition-colors border-b-2"
                            :class="activeTab === 'json' ? 'border-blue-500 text-blue-400 bg-slate-800' : 'border-transparent text-slate-400 hover:text-slate-200'"
                        >
                            Raw JSON
                        </button>
                    </div>

                    <!-- Tab Panels -->
                    <div class="flex-1 overflow-y-auto p-0 bg-[#0d1117]">
                        
                        <!-- Chat View -->
                        <div v-show="activeTab === 'chat'" class="max-w-4xl mx-auto p-6 space-y-8">
                            
                            <!-- Request -->
                            <div class="space-y-2">
                                <div class="text-xs uppercase tracking-wider text-slate-500 font-bold mb-2 flex items-center gap-2">
                                    <span class="w-2 h-2 rounded-full bg-blue-500"></span> User Request
                                </div>
                                
                                <div v-if="hasMessages(selectedDetail?.content.request.body)" class="space-y-4">
                                     <div v-for="(msg, idx) in extractMessages(selectedDetail?.content.request.body)" :key="idx" 
                                          class="rounded-lg p-4 border"
                                          :class="msg.role === 'user' ? 'bg-slate-800 border-slate-700' : 'bg-slate-900 border-slate-700 ml-8'">
                                         <div class="text-xs font-bold uppercase mb-2" :class="msg.role === 'user' ? 'text-blue-400' : 'text-purple-400'">{{ msg.role }}</div>
                                         <div class="prose prose-invert prose-sm max-w-none" v-html="renderMarkdown(msg.content)"></div>
                                         
                                         <!-- Show images if present in Anthropic format -->
                                         <div v-if="Array.isArray(msg.content)" class="mt-2 space-y-2">
                                             <div v-for="(block, bIdx) in msg.content" :key="bIdx">
                                                 <div v-if="block && block.type === 'image'" class="rounded overflow-hidden border border-slate-700">
                                                     <div class="text-[10px] bg-slate-800 px-2 py-1 text-slate-400">Image ({{ block.source?.media_type || 'unknown' }})</div>
                                                     <img 
                                                        v-if="block.source && block.source.type === 'base64'" 
                                                        :src="'data:' + block.source.media_type + ';base64,' + block.source.data" 
                                                        class="max-w-xs max-h-64 object-contain" 
                                                     />
                                                 </div>
                                             </div>
                                         </div>
                                     </div>
                                </div>
                                <div v-else class="bg-slate-800 rounded-lg p-4 border border-slate-700 font-mono text-xs text-slate-300 overflow-auto whitespace-pre-wrap">
                                    {{ JSON.stringify(selectedDetail?.content.request.body, null, 2) }}
                                </div>
                            </div>

                            <!-- Divider -->
                            <div class="flex items-center justify-center opacity-20">
                                <div class="h-px bg-slate-500 w-full"></div>
                                <div class="px-2 text-slate-500 font-mono text-xs">RESPONSE</div>
                                <div class="h-px bg-slate-500 w-full"></div>
                            </div>

                            <!-- Response -->
                            <div class="space-y-2">
                                 <div class="text-xs uppercase tracking-wider text-slate-500 font-bold mb-2 flex items-center gap-2">
                                    <span class="w-2 h-2 rounded-full bg-green-500"></span> Model Response
                                </div>

                                <div class="bg-[#161b22] rounded-lg border border-slate-700 p-0 overflow-hidden">
                                    <div class="p-4 prose prose-invert prose-sm max-w-none">
                                        <div v-html="renderMarkdown(extractResponse(selectedDetail?.content.response))"></div>
                                    </div>
                                    
                                     <div v-if="selectedDetail?.content.error" class="bg-red-900/20 border-t border-red-900/50 p-4 text-red-400 text-sm font-mono">
                                        <strong>Error:</strong> {{ selectedDetail?.content.error }}
                                    </div>
                                </div>
                            </div>

                        </div>

                        <!-- JSON Raw View -->
                        <div v-show="activeTab === 'json'" class="p-4 h-full">
                            <pre class="language-json h-full overflow-auto text-xs"><code id="raw-json" class="language-json"></code></pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const { createApp, ref, onMounted, watch } = Vue;

        createApp({
            setup() {
                const logs = ref([]);
                const selectedLog = ref(null);
                const selectedDetail = ref(null);
                const searchQuery = ref('');
                const loading = ref(false);
                const activeTab = ref('chat');
                let searchTimeout = null;

                const fetchLogs = async () => {
                    loading.value = true;
                    try {
                        const q = searchQuery.value ? `&search=${encodeURIComponent(searchQuery.value)}` : '';
                        const res = await fetch(`/api/logs?limit=50${q}`);
                        if (!res.ok) throw new Error('Failed to fetch');
                        logs.value = await res.json();
                        
                        // If we have a selected log, refresh its connection to the list
                        if (selectedLog.value) {
                            const stillExists = logs.value.find(l => l.id === selectedLog.value.id);
                            if (stillExists) selectedLog.value = stillExists;
                        }
                    } catch (e) {
                        console.error("Fetch logs error:", e);
                    } finally {
                        loading.value = false;
                    }
                };

                const selectLog = async (log) => {
                    selectedLog.value = log;
                    loading.value = true;
                    try {
                        const res = await fetch(`/api/logs/${log.id}`);
                        if (res.ok) {
                            selectedDetail.value = await res.json();
                            activeTab.value = 'chat'; // default to chat view
                            
                            // Highlight JSON after update
                            setTimeout(() => {
                                const el = document.getElementById('raw-json');
                                if (el) {
                                    el.textContent = JSON.stringify(selectedDetail.value.content, null, 2);
                                    Prism.highlightElement(el);
                                }
                            }, 50);
                        }
                    } catch (e) {
                        console.error(e);
                    } finally {
                        loading.value = false;
                    }
                };

                const debouncedSearch = () => {
                    if (searchTimeout) clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(fetchLogs, 300);
                };
                
                // --- Helpers ---

                const formatTime = (ts) => {
                    const d = new Date(ts);
                    return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
                };

                const formatUrl = (url) => {
                    try {
                        const u = new URL(url);
                        return u.pathname + u.search;
                    } catch (e) { return url; }
                };

                const statusColor = (status) => {
                    if (status >= 200 && status < 300) return 'text-green-400';
                    if (status >= 400 && status < 500) return 'text-yellow-400';
                    if (status >= 500) return 'text-red-400';
                    return 'text-slate-400';
                };
                
                const statusBadge = (status) => {
                     if (status >= 200 && status < 300) return 'bg-green-900 text-green-300';
                    if (status >= 400 && status < 500) return 'bg-yellow-900 text-yellow-300';
                    if (status >= 500) return 'bg-red-900 text-red-300';
                    return 'bg-slate-700 text-slate-300';
                };

                const hasMessages = (body) => {
                    return body && (Array.isArray(body.messages) || (body.prompt && typeof body.prompt === 'string'));
                };

                const extractMessages = (body) => {
                     if (!body) return [];
                     if (body.messages) return body.messages;
                     // Legacy completion format
                     if (body.prompt) return [{role: 'user', content: body.prompt}];
                     return [];
                };

                const extractResponse = (response) => {
                    if (!response) return '<span class="text-slate-500 italic">No response body</span>';
                    
                    // Handle wrapped body if present
                    const data = response.body || response;
                    
                    // 1. Check for our custom full_stream_text from the updated logger
                    if (data.full_response_text) {
                        return data.full_response_text;
                    }

                    // 2. OpenAI Chat Completion (Non-streaming)
                    if (data.choices && data.choices[0]?.message?.content) {
                        return data.choices[0].message.content;
                    }
                    
                    // 3. OpenAI Completion (Legacy)
                    if (data.choices && data.choices[0]?.text) {
                        return data.choices[0].text;
                    }
                    
                    // 4. Anthropic Messages (Non-streaming)
                    if (data.content && Array.isArray(data.content)) {
                        return data.content
                            .filter(c => c.type === 'text')
                            .map(c => c.text)
                            .join('');
                    }

                    // 5. Fallback for unparsed/partial streams
                    if (data._sse_chunks) {
                         return `*(Streamed response with ${data._sse_chunks} chunks. Update logs to see full content)*`;
                    }

                    // 6. Generic JSON fallback
                    if (typeof data === 'object') {
                        return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
                    }
                    
                    return String(data);
                };

                const extractContent = (content) => {
                    if (!content) return '';
                    if (typeof content === 'string') return content;
                    
                    // Handle Anthropic content blocks array
                    if (Array.isArray(content)) {
                        return content
                            .filter(b => b && b.type === 'text' && b.text)
                            .map(b => b.text)
                            .join('\\n\\n');
                    }
                    
                    // Handle object content (unexpected but possible)
                    try {
                        return JSON.stringify(content, null, 2);
                    } catch (e) {
                        return String(content);
                    }
                };

                const renderMarkdown = (text) => {
                    if (!text) return '<span class="text-slate-600 italic">Empty content</span>';
                    
                    // Ensure text is a string before passing to marked
                    if (typeof text !== 'string') {
                         text = extractContent(text);
                    }
                    
                    // Fallback if marked is not available
                    if (typeof marked === 'undefined') {
                        return String(text).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    }

                    try {
                        return marked.parse(text);
                    } catch (e) {
                        console.error("Markdown error:", e);
                        return String(text);
                    }
                };

                onMounted(() => {
                    fetchLogs();
                    // Auto-refresh every 5 seconds
                    setInterval(() => {
                        if (!searchQuery.value) fetchLogs(); 
                    }, 5000);
                });

                return {
                    logs, selectedLog, selectedDetail, searchQuery, loading, activeTab,
                    fetchLogs, selectLog, debouncedSearch,
                    formatTime, formatUrl, statusColor, statusBadge,
                    hasMessages, extractMessages, extractResponse, renderMarkdown
                };
            }
        }).mount('#app');
    </script>
</body>
</html>
"""

@app.get("/")
async def get_index():
    return HTMLResponse(HTML_TEMPLATE)

if __name__ == "__main__":
    if not LOG_DIR.exists():
        LOG_DIR.mkdir(parents=True)
        print(f"Created log directory at {LOG_DIR}")
        
    print(f"Starting Log Visualizer on http://{HOST}:{PORT}")
    print(f"Reading logs from: {LOG_DIR}")
    uvicorn.run(app, host=HOST, port=PORT)

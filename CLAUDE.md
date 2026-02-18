# Copilot Proxy Python Edition - AI Agent Instructions

## Project Overview

This is a Python-based proxy server that provides OpenAI and Anthropic SDK-compatible interfaces to GitHub Copilot's API. It implements a VLLM-compatible proxy with full async/await architecture, token management, and streaming support.

**Technology Stack:**
- Python 3.11+ (required)
- FastAPI (web framework)
- uvicorn (ASGI server)
- httpx (async HTTP client)
- Typer (CLI framework)
- loguru (logging)
- Pydantic (validation)

**Package Manager:** `uv`

---

## Essential Commands

### Installation & Setup
```bash
# Install dependencies
uv sync

# Alternative quick setup
./setup.sh
```

### Running the Application
```bash
# Authenticate with GitHub (required first step)
uv run run_proxy.py authenticate

# Start the proxy server
uv run run_proxy.py start-server

# Start with verbose logging (recommended for development)
uv run run_proxy.py start-server --verbose

# Start with custom options
uv run run_proxy.py start-server --port 4242 --host 0.0.0.0 --rate-limit 5 --wait

# Check Copilot usage quota
uv run run_proxy.py check-usage

# Show debug information
uv run run_proxy.py debug-info
```

### Testing
```bash
# Run basic functionality tests
uv run python test_basic.py

# Run pytest suite (when available)
uv run pytest

# Run specific test file
uv run pytest tests/test_specific.py -v

# Run with coverage
uv run pytest --cov=src/copilot_proxy --cov-report=html
```

### Code Quality
```bash
# Lint with ruff
uv run ruff check src/

# Auto-fix issues
uv run ruff check --fix src/

# Format code
uv run ruff format src/
```

---

## Architecture & Component Boundaries

### Module Organization

```
src/copilot_proxy/
├── cli/              # CLI commands (Typer-based)
├── api/              # FastAPI server and HTTP routes
├── services/         # External API clients (GitHub, Copilot)
├── core/             # Core business logic (tokens, rate limiting)
├── config/           # Configuration (settings, paths, constants)
├── translators/      # API format conversion (OpenAI ↔ Anthropic)
├── schemas/          # Pydantic validation models
└── utils/            # Utilities (logging, HTTP client, headers)
```

### Key Data Flow

```
Client Request
  → FastAPI Route Handler
    → Rate Limiter Check (if configured)
    → get_copilot_token() → TokenManager.ensure_valid_token()
    → get_copilot_client(token)
      → CopilotClient.create_chat_completion()
        → HTTP POST to GitHub Copilot API
        → Translator (format conversion)
        → Streaming via EventSourceResponse
  → Response to Client
```

### Core Components

- **[cli/app.py](src/copilot_proxy/cli/app.py)** - Typer CLI entry point registry
- **[api/app.py](src/copilot_proxy/api/app.py)** - FastAPI factory with middleware and route registration
- **[core/token_manager.py](src/copilot_proxy/core/token_manager.py)** - GitHub→Copilot token exchange and auto-refresh
- **[core/state.py](src/copilot_proxy/core/state.py)** - Global singleton state (AppState)
- **[core/rate_limiter.py](src/copilot_proxy/core/rate_limiter.py)** - Rate limiting (wait or reject modes)
- **[services/copilot/client.py](src/copilot_proxy/services/copilot/client.py)** - Copilot API client
- **[services/github/auth.py](src/copilot_proxy/services/github/auth.py)** - GitHub Device Code OAuth

---

## Critical Conventions

### File & Code Structure

**File Naming:**
- Use `snake_case` for all files and directories
- Entry point: `run_proxy.py` (never `main.py`)
- Test files: Use `test_*.py` prefix

**Module Init Files:**
- Keep `__init__.py` files minimal - just docstrings or empty
- No imports or code unless necessary for exposing components

**Type Hints:**
- Use Python 3.11+ style: `str | None` instead of `Optional[str]`
- Minimum Python version: **3.11+**

### API Route Conventions

When adding a new API route in [src/copilot_proxy/api/routes/](src/copilot_proxy/api/routes/):

```python
from fastapi import APIRouter, HTTPException
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

@router.post("/your-endpoint")
async def your_endpoint(request: YourRequest):
    """Your endpoint description."""
    try:
        # 1. Check rate limit (if configured)
        # 2. Log request (info + debug with truncated payload)
        # 3. Process request
        # 4. Log response (debug truncated)
        logger.info("Processing request")
        return response
    except HTTPException:
        raise  # Re-raise HTTPException immediately
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal error")
```

**Always follow this pattern:**
1. Check rate limit (if `state.rate_limit_seconds` is set)
2. Log request at `info` level, debug level with truncated payload
3. Process the request
4. Log response at `debug` level with truncated payload
5. Handle exceptions properly

**Streaming Responses:**
```python
from typing import AsyncGenerator
from sse_starlette import EventSourceResponse

async def stream_response() -> AsyncGenerator[str, None]:
    """Stream responses using SSE format."""
    # Yield individual chunks
    yield f"data: {json_data}\n\n"  # Note: double newline required
    # Send completion marker
    yield "data: [DONE]\n\n"

return EventSourceResponse(stream_response())
```

### CLI Command Conventions

When adding a new CLI command in [src/copilot_proxy/cli/](src/copilot_proxy/cli/):

```python
import asyncio
import typer
from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)

async def async_your_command(
    param1: str = typer.Option(..., "--param1", help="Parameter 1"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Async implementation of your command."""
    setup_logger(verbose=verbose)
    logger.info("Starting your command")
    try:
        result = await some_async_operation()
        logger.info("Command completed successfully")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise typer.Exit(code=1)

def your_command(
    param1: str = typer.Argument(..., help="Parameter 1"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Your command description."""
    asyncio.run(async_your_command(param1=param1, verbose=verbose))
```

**Register in [cli/app.py](src/copilot_proxy/cli/app.py):**
```python
from . import your_command
app.command()(your_command.your_command)
```

### Logging Conventions (loguru)

**Pattern:**
```python
from ..utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Info message")
logger.debug(f"Debug with var: {variable}")
logger.warning("Warning message")
logger.error(f"Error: {type(e).__name__}: {e}")
```

**Critical Rules:**
1. **Always bind module name:** `get_logger(__name__)`
2. **Never log full tokens:** Use `token[:10]...` for preview
3. **For large payloads:** Log only last 400 chars: `str(data)[-400:]`
4. **Use `.debug()`** for detailed traces (payloads, headers, internals)
5. **Use `.info()`** for normal operation (request received, token refreshed)
6. **Use `.warning()`** for recoverable issues (rate limit hit)
7. **Use `.error()`** for failures (API errors, validation errors)

### Error Handling Conventions

**API Routes:**
- Use `HTTPException` with specific status codes
- **Re-raise `HTTPException` immediately** - don't wrap it
- Log full context: `logger.error(f"{type(e).__name__}: {e}")`

**CLI Commands:**
- Use `typer.Exit(code=1)` for errors
- Provide clear error messages to user

**Async/Await:**
- **Never use `asyncio.run()` inside async functions** - just `await`
- All API calls should be async
- All HTTP requests use `httpx.AsyncClient`

---

## Common Pitfalls to Avoid

### 1. Token Refresh Race Conditions
**❌ Wrong:** Checking token expiry manually per-request
**✅ Correct:** The project uses background auto-refresh ([token_manager](src/copilot_proxy/core/token_manager.py#L93-L128)) - just call `ensure_valid_token()`

### 2. Rate Limiting
**❌ Wrong:** Forgetting to check rate limit in new routes
**✅ Correct:** Check `state.rate_limit_seconds` in EVERY route before processing

### 3. Path Resolution
**❌ Wrong:** Hardcoding `../copilot-data/` paths
**✅ Correct:** Always use `get_github_token_path()` from [config/paths.py](src/copilot_proxy/config/paths.py)

### 4. Streaming Responses
**❌ Wrong:** Yielding `data: {json}\n` (single newline)
**✅ Correct:** Yield `f"data: {json}\n\n"` (double newline)

### 5. HTTP Exceptions
**❌ Wrong:** Wrapping `HTTPException` in try/except
**✅ Correct:** Re-raise `HTTPException` immediately without wrapping

---

## Development Workflow

### Adding a New API Route

1. Create route file: `src/copilot_proxy/api/routes/my_endpoint.py`
2. Register in [api/app.py](src/copilot_proxy/api/app.py#L24): `app.include_router(my_endpoint.router)`
3. Add schemas if needed: `src/copilot_proxy/schemas/openai.py` or `anthropic.py`
4. Test with curl or SDK after server is running

### Adding a New CLI Command

1. Create command file: `src/copilot_proxy/cli/my_command.py`
2. Register in [cli/app.py](src/copilot_proxy/cli/app.py#L8): `app.command()(my_command.my_command)`
3. Test: `uv run run_proxy.py my-command --help`

### Adding a New Service

1. Create client in `src/copilot_proxy/services/`
2. Use `httpx.AsyncClient` from [utils/http_client.py](src/copilot_proxy/utils/http_client.py)
3. Define schemas in `src/copilot_proxy/services/*/schemas.py`
4. Make all methods async

---

## Configuration & Environment

### Environment Variables

Create `.env` in project root:
```env
PORT=4242
HOST=0.0.0.0
ACCOUNT_TYPE=individual
VERBOSE=false
RATE_LIMIT_SECONDS=None
RATE_LIMIT_WAIT=false
MANUAL_APPROVE=false
SHOW_TOKEN=false
```

### Token Storage

GitHub tokens are stored at: `../copilot-data/github_token` (shared with TypeScript version)

- Always use `get_github_token_path()` from [config/paths.py](src/copilot_proxy/config/paths.py)
- Token file permissions: 0o600 (owner read/write only)

---

## API Endpoints Reference

### OpenAI-Compatible
- `GET /health` - Health check
- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Chat completions (streaming + non-streaming)
- `POST /v1/completions` - Legacy completions
- `POST /v1/embeddings` - Create embeddings
- `GET /usage` - Usage statistics

### Anthropic-Compatible
- `POST /v1/messages` - Messages API
- `POST /v1/messages/count_tokens` - Token counting

### Debug (if `--show-token` enabled)
- `GET /debug/token` - Token information

---

## Key File Locations

| Component | File Path |
|-----------|-----------|
| CLI Registry | [src/copilot_proxy/cli/app.py](src/copilot_proxy/cli/app.py) |
| Server Factory | [src/copilot_proxy/api/app.py](src/copilot_proxy/api/app.py) |
| Token Management | [src/copilot_proxy/core/token_manager.py](src/copilot_proxy/core/token_manager.py) |
| Copilot Client | [src/copilot_proxy/services/copilot/client.py](src/copilot_proxy/services/copilot/client.py) |
| GitHub Auth | [src/copilot_proxy/services/github/auth.py](src/copilot_proxy/services/github/auth.py) |
| Settings | [src/copilot_proxy/config/settings.py](src/copilot_proxy/config/settings.py) |
- Dependencies: [pyproject.toml](pyproject.toml)
- Entry Point: [run_proxy.py](run_proxy.py)

---

## Testing Recommendations

When writing tests:
1. Use `pytest-asyncio` for async tests
2. Mock HTTP clients with `pytest-httpx`
3. Test both streaming and non-streaming responses
4. Verify rate limiting behavior
5. Test error handling and edge cases

---

## Docker Deployment

```bash
# Build image
docker build -t copilot-proxy-py .

# Run container
docker run -p 4242:4242 -e COPILOT_DATA_DIR=/data copilot-proxy-py

# Set COPILOT_DATA_DIR to shared volume for token storage
docker run -p 4242:4242 -v /path/to/copilot-data:/data copilot-proxy-py
```

---

## Additional Notes

- The proxy shares token storage with the TypeScript version for interoperability
- Streaming responses use SSE (Server-Sent Events) format
- Rate limiting supports two modes: wait (sleep until allowed) or reject (return 429)
- Token auto-refresh runs in background every 30 seconds, refreshing when token expires in < 60 seconds
- All API calls are async and non-blocking
- Connection pooling is configured (100 max connections in httpx)

# Copilot Proxy - Project Conventions & Best Practices

This guide documents project-specific conventions, patterns, and common pitfalls for the Copilot Proxy Python project.

---

## 1. Coding Conventions

### File Naming Conventions

- **Python files**: Use `snake_case` for all Python files (e.g., `token_manager.py`, `request_logger.py`)
- **Module packages**: Use `snake_case` for directories (e.g., `copilot_proxy/`, `services/`)
- **Entry point**: `run_proxy.py` (not `main.py` or `cli.py`)
- **Test files**: Use `test_*.py` prefix (e.g., `test_basic.py`)
- **Config files**: Use `.py` for config, not `.yaml` or `.json` (e.g., `settings.py`, `constants.py`)

### Module `__init__.py` Patterns

All packages require `__init__.py` files following these patterns:

```python
# __init__.py files are minimal - just export main interfaces
# Example: src/copilot_proxy/__init__.py
"""Copilot Proxy package."""

# Example: src/copilot_proxy/cli/__init__.py
"""CLI commands."""
```

**Pattern**: Empty or just docstring. Import actual functions from full paths:
```python
# ✅ GOOD: Import directly
from copilot_proxy.cli.app import app

# ❌ BAD: Don't re-export in __init__.py
from .app import app
app = app
```

### Error Handling Patterns

Use standard exception hierarchy with specific HTTP status codes:

```python
# ✅ GOOD: Pattern for API endpoints
from fastapi import HTTPException

try:
    result = await some_operation()
    return result
except httpx.HTTPStatusError as e:
    logger.error(f"Upstream API error: {e}")
    raise HTTPException(status_code=e.response.status_code, detail=str(e))
except ValueError as e:
    logger.error(f"Validation error: {e}")
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.error(f"Unexpected error: {type(e).__name__}: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")

# ✅ GOOD: Pattern for CLI commands
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise typer.Exit(code=1)
```

**Key patterns:**
- Always log errors with full context (`type(e).__name__`: {e})
- Use `HTTPException` with appropriate status codes in API routes
- Use `typer.Exit(code=1)` for CLI command failures
- Don't catch generic `Exception` without logging
- Always re-raise HTTPException (don't swallow it)

### Logging Patterns (loguru)

**Setup** ([utils/logger.py](src/copilot_proxy/utils/logger.py#L1-L54)):

```python
from loguru import logger as loguru_logger

# Logger setup happens once at startup
def setup_logger(verbose: bool = False, show_token: bool = False):
    """Setup logging configuration."""
    loguru_logger.remove()  # Remove default handler
    
    level = "DEBUG" if verbose else "INFO"
    log_format = (
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    loguru_logger.add(sys.stdout, format=log_format, level=level, colorize=True)
    loguru_logger.show_token = show_token  # For token masking
```

**Usage in modules**:

```python
from ..utils.logger import get_logger

logger = get_logger(__name__)

logger.info("Info message")
logger.debug(f"Debug with var: {variable}")
logger.warning("Warning message")
logger.error(f"Error occurred: {type(e).__name__}: {e}")

# Sensitive data - show only first 10 chars
logger.debug(f"Token preview: {token[:10]}...")
```

**Critical patterns:**
- Always bind module name: `get_logger(__name__)`
- Use `.debug()` for detailed traces (payloads, headers, internals)
- Use `.info()` for normal operation (request received, token refreshed)
- Use `.warning()` for recoverable issues (rate limit hit)
- Use `.error()` for failures (API errors, validation errors)
- Never log full tokens (use token[:10]... for preview)
- For large payloads, log only last 400 chars: `str(data)[-400:]`

### Type Hinting Conventions

Use modern Python 3.11+ type hints:

```python
# ✅ GOOD: Use | operator for unions (Python 3.10+)
def function(token: str | None = None) -> str:
    ...

# ❌ BAD: Old-style Optional
import typing
def function(token: typing.Optional[str] = None) -> str:
    ...

# ✅ GOOD: List and dict generics
def process(items: list[dict[str, Any]]) -> None:
    ...

# ✅ GOOD: AsyncGenerator for streaming
async def stream_chunks() -> AsyncGenerator[str, None]:
    ...

# ✅ GOOD: Type aliases for complex types
from typing import AsyncGenerator
ChunkGenerator = AsyncGenerator[str, None]
```

---

## 2. API Conventions

### Adding New API Routes

Follow this pattern for all new routes:

```python
# src/copilot_proxy/api/routes/your_endpoint.py
"""Your endpoint description."""

from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_copilot_client, get_copilot_token
from ...schemas.your_schema import YourRequest, YourResponse
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/v1/your-endpoint")
async def your_handler(
    request: YourRequest,
    client: CopilotClient = Depends(get_copilot_client),  # Inject client
):
    """Your endpoint description."""
    try:
        # Check rate limit
        state = get_state()
        if state.rate_limit_seconds:
            rate_limiter = get_rate_limiter()
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )
        
        # Log request
        payload_dict = request.model_dump()
        logger.info(f"Your endpoint request - param: {request.some_param}")
        logger.debug(f"Request payload (last 400 chars): {str(payload_dict)[-400:]}")
        
        # Process request
        result = await client.some_method(...)
        
        # Log response
        logger.debug(f"Response (last 400 chars): {str(result.model_dump())[-400:]}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Your endpoint error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Operation failed: {str(e)}")
```

**Register route in app factory** ([api/app.py](src/copilot_proxy/api/app.py#L1-L40)):

```python
from .routes import your_endpoint

app.include_router(your_endpoint.router)
```

### Request/Response Schema Patterns

All schemas use Pydantic BaseModel:

```python
# src/copilot_proxy/schemas/openai.py (or anthropic.py)
from typing import Optional
from pydantic import BaseModel, Field


class YourRequest(BaseModel):
    """Your request description."""
    
    # Required fields
    model: str
    messages: list[dict]
    
    # Optional fields with defaults
    temperature: Optional[float] = None
    max_tokens: Optional[int] = Field(None, description="Max tokens to generate")
    stream: bool = False


class YourResponse(BaseModel):
    """Your response description."""
    
    id: str
    object: str = "your.object.type"
    created: int
    data: list[Something]
```

**Schema patterns:**
- Use `Optional[T]` for nullable fields
- Use `Field(..., description="...")` for docs
- Include `object: str = "fixed.type"` for OpenAI compatibility
- Use descriptive docstrings for each class
- Group related schemas in one file (openai.py, anthropic.py)

### Error Response Format

Consistent error format across all endpoints:

```python
# HTTPException format (automatic HTTP status code)
raise HTTPException(
    status_code=400,
    detail="Missing required parameter: model"
)

# Response:
{
  "detail": "Missing required parameter: model"
}
```

**Status code conventions:**
- `400`: Bad request (validation errors)
- `401`: Unauthorized (token not found/expired)
- `429`: Rate limited
- `500`: Internal server error (API failures, unexpected errors)

### Streaming Response Handling with sse-starlette

**For OpenAI-style streaming** ([api/routes/chat.py](src/copilot_proxy/api/routes/chat.py#L13-L92)):

```python
from sse_starlette.sse import EventSourceResponse
import json
import time


async def stream_chat_chunks(
    request: ChatCompletionRequest,
    client: CopilotClient,
) -> AsyncGenerator[str, None]:
    """Stream chat completion chunks in OpenAI format."""
    chunk_id = f"chatcmpl-{int(time.time())}"
    accumulated_content = ""
    finish_reason = None
    
    async for line in client.stream_chat_completion(...):
        # Parse SSE line
        if line.startswith("data:"):
            line = line[5:].strip()
        
        if not line or line == "[DONE]":
            # Send final chunk with finish_reason
            if finish_reason:
                final_chunk = ChatCompletionStreamResponse(...)
                yield f"data: {final_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
            break
        
        try:
            data = json.loads(line)
            # Process chunk and yield
            chunk = ChatCompletionStreamResponse(...)
            yield f"data: {chunk.model_dump_json()}\n\n"
        except json.JSONDecodeError:
            continue


# In route handler
if request.stream:
    return EventSourceResponse(stream_chat_chunks(request, client))
```

**For Anthropic-style streaming** ([api/routes/messages.py](src/copilot_proxy/api/routes/messages.py#L13-L48)):

```python
async def stream_anthropic_messages(...) -> AsyncGenerator[str, None]:
    """Stream Anthropic-format messages using OpenAI backend."""
    # Translate request
    openai_request = translate_anthropic_to_openai(request)
    
    # Stream and translate events
    async for line in stream_openai_to_anthropic(
        client.stream_chat_completion(...)
    ):
        yield line
```

**Critical streaming patterns:**
- Always use `EventSourceResponse()` wrapper
- Yield format: `f"data: {json_data}\n\n"` (note double newline)
- Always send `data: [DONE]\n\n` at end (OpenAI)
- Always use `model_dump_json()` from Pydantic
- Handle connection errors gracefully (catch and log)
- Use `time.time()` for chunk timestamps

---

## 3. CLI Conventions

### Adding New CLI Commands

All CLI commands use Typer patterns:

```python
# src/copilot_proxy/your_command.py
"""Your command description."""

import asyncio
import typer
from typing import Optional

from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def async_your_command(
    param1: str = typer.Option(..., "--param1", help="Parameter 1"),
    param2: int = typer.Option(42, "--param2", help="Parameter 2"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Async implementation of your command."""
    # Setup logging first
    setup_logger(verbose=verbose)
    
    try:
        logger.info("Starting your command")
        
        # Your logic here
        result = await some_async_operation(...)
        
        logger.info(f"Command completed successfully")
        
    except Exception as e:
        logger.error(f"Command failed: {type(e).__name__}: {e}")
        raise typer.Exit(code=1)


def your_command(
    param1: str = typer.Option(..., "--param1", help="Parameter 1"),
    param2: int = typer.Option(42, "--param2", help="Parameter 2"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Your command description (sync wrapper)."""
    asyncio.run(async_your_command(
        param1=param1,
        param2=param2,
        verbose=verbose,
    ))
```

**Register command** ([cli/app.py](src/copilot_proxy/cli/app.py#L1-L30)):

```python
from . import your_command

app.command()(your_command.your_command)
```

### Command Option Patterns with Typer

```python
# ✅ GOOD: Standard option patterns
def start_server(
    port: int = typer.Option(4242, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Server host"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    rate_limit: Optional[int] = typer.Option(
        None,
        "--rate-limit",
        help="Rate limit in seconds between requests",
    ),
    wait: bool = typer.Option(False, "--wait", help="Wait when rate limited (vs reject)"),
    account_type: str = typer.Option(
        "individual",
        "--account-type",
        help="Account type: individual, business, enterprise"
    ),
):
    """Start the proxy server."""
    ...

# Options:
# - Use short flag (-v) for common options
# - Use long form (--verbose) for clarity
# - Provide help text for ALL options
# - Use Optional[int] for nullable options
# - Always provide defaults for optional params
```

### Help Text Conventions

```python
# ✅ GOOD: Command description
def authenticate(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Authenticate with GitHub using device code flow."""
    ...

# Run: uv run run_proxy.py authenticate --help
# Output:
# Authenticate with GitHub using device code flow.
#
# Options:
#   --verbose, -v   Verbose logging [default: False]
```

**Help text patterns:**
- Keep command descriptions concise and imperative ("Authenticate with...", "List...")
- Use short descriptions for options (1-2 lines)
- Include units in descriptions ("Rate limit in seconds", "Server port")
- Use present tense for descriptions ("Verbose logging" not "Enable verbose logging")

---

## 4. Common Issues

### Token Management Issues

**Race Conditions with Token Refresh**:

```python
# ❌ PROBLEM: Multiple concurrent requests can trigger multiple refreshes
async def ensure_valid_token(self) -> str:
    if self.copilot_token and self.token_expires_at:
        time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()
        if time_until_expiry > 60:
            return self.copilot_token
    
    # PROBLEM: Multiple requests can reach this line simultaneously
    await self.fetch_copilot_token()  # Multiple refreshes!
    return self.copilot_token

# ✅ FIXED: Use background refresh + caching
# In token_manager.py:
# - Background task runs every 30s
# - Refreshes only when time_until_expiry < 60
# - All requests read from cached self.copilot_token
# - No race condition possible

# Usage pattern:
state = get_state()
state.copilot_token is already valid (refreshed in background)
# Just use:
client = CopilotClient(copilot_token=state.copilot_token)
```

**Solution from [core/token_manager.py](src/copilot_proxy/core/token_manager.py#L93-L128)**:
```python
async def start_auto_refresh(self, check_interval: int = 30) -> None:
    """Start background task to auto-refresh token before expiry."""
    async def refresh_loop():
        while True:
            try:
                if self.token_expires_at:
                    time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()
                    
                    # Refresh 60 seconds before expiry
                    if 0 < time_until_expiry < 60:
                        logger.info("Refreshing Copilot token (expires soon)")
                        await self.ensure_valid_token()
                
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in token refresh loop: {e}")
                await asyncio.sleep(check_interval)
    
    self._refresh_task = asyncio.create_task(refresh_loop())
```

### Rate Limiting Configuration

**Common mistake: Forgetting to check rate limit in routes**

```python
# ❌ BAD: Forgot rate limiting
@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Directly process - ignores rate limit!
    return await client.create_chat_completion(...)

# ✅ GOOD: Always check rate limit first
@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Check rate limit BEFORE processing
    state = get_state()
    if state.rate_limit_seconds:
        rate_limiter = get_rate_limiter()
        await rate_limiter.check_rate_limit(
            rate_limit_seconds=state.rate_limit_seconds,
            wait_mode=state.rate_limit_wait,
        )
    
    # Now process
    return await client.create_chat_completion(...)

# ✅ Pattern to copy-paste:
state = get_state()
if state.rate_limit_seconds:
    rate_limiter = get_rate_limiter()
    await rate_limiter.check_rate_limit(
        rate_limit_seconds=state.rate_limit_seconds,
        wait_mode=state.rate_limit_wait,
    )
```

**Rate limiter behavior** ([core/rate_limiter.py](src/copilot_proxy/core/rate_limiter.py#L8-L44)):
- `wait_mode=False` (default): Raises Exception with message, causes HTTP 500
- `wait_mode=True`: Sleeps and returns True, delays request
- Always check `state.rate_limit_seconds` first (None = disabled)

### Path Resolution Issues (copilot-data directory)

**Common issue: Token file not found**

```python
# ✅ ALWAYS use the path utility (never hardcode paths)
from ..config.paths import get_github_token_path

token_file = get_github_token_path()
if not token_file.exists():
    raise FileNotFoundError(f"GitHub token not found at {token_file}")

# ❌ BAD: Hardcoded path or relative paths
token = Path("../copilot-data/github_token").read_text()  # Breaks in Docker!
token =("./copilot-data/github_token")  # Wrong location!
```

**Path resolution** ([config/paths.py](src/copilot_proxy/config/paths.py#L1-L31)):
```python
# Project root is always calculated correctly
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Data directory can be overridden via env var (for Docker)
DATA_DIR = Path(os.environ.get("COPILOT_DATA_DIR", PROJECT_ROOT.parent / "copilot-data"))
GITHUB_TOKEN_FILE = DATA_DIR / "github_token"

# Cache directory is always in project
CACHE_DIR = PROJECT_ROOT / ".cache"
```

**Docker usage:**
```bash
# Set environment variable to override location
docker run -e COPILOT_DATA_DIR=/data copilot-proxy
```

### Async/Await Gotchas

**🚨 Forgetting to await async operations:**

```python
# ❌ BAD: Forgot await
response = client.get_models()  # Returns coroutine, not result!

# ✅ GOOD: Wait for async operation
response = await client.get_models()

# ❌ BAD: Using sync httpx in async function
import httpx

async def fetch_data():
    client = httpx.Client()  # Wrong! Use AsyncClient
    response = client.get(url)  # This blocks the event loop!
    return response.json()

# ✅ GOOD: Use async httpx
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

**🚨 Don't use asyncio.run() inside async functions:**

```python
# ❌ BAD: Blocking
async def process():
    # This blocks the event loop - BAD!
    result = asyncio.run(some_async_operation())
    return result

# ✅ GOOD: Just await
async def process():
    # Just await directly
    result = await some_async_operation()
    return result
```

**🚨 Don't create async tasks without proper error handling:**

```python
# ❌ BAD: Unhandled errors in background tasks
async def background_task():
    await something_that_fails()  # Error gets lost!

# ✅ GOOD: Wrap in try/except
async def background_task():
    try:
        await something_that_might_fail()
    except asyncio.CancelledError:
        logger.info("Task cancelled")
        raise
    except Exception as e:
        logger.error(f"Task error: {e}")
```

### Common Mistakes Developers Make

**1. Forgetting to log request/response payloads**

```python
# ❌ BAD: No logging
@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    return await client.create_chat_completion(...)

# ✅ GOOD: Log request and response
@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    payload_dict = request.model_dump()
    logger.info(f"Chat completion request - model: {request.model}, stream: {request.stream}")
    logger.debug(f"Request payload (last 400 chars): {str(payload_dict)[-400:]}")
    
    result = await client.create_chat_completion(...)
    
    logger.debug(f"Response (last 400 chars): {str(result.model_dump())[-400:]}")
    return result
```

**2. Not masking sensitive data in logs**

```python
# ❌ BAD: Logging full token
logger.info(f"Token: {token}")

# ✅ GOOD: Show only preview
logger.info(f"Token preview: {token[:10]}...")

# For headers, use _sanitize_headers
logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
```

**3. Not handling connection errors properly**

```python
# ❌ BAD: Generic catch-all without specific handling
try:
    response = await client.get(url)
    return response.json()
except Exception as e:
    raise HTTPException(500, "Failed")  # No context!

# ✅ GOOD: Handle specific error types
try:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()
except httpx.HTTPStatusError as e:
    logger.error(f"API error (HTTP {e.response.status_code}): {e}")
    logger.error(f"Response body: {e.response.text}")
    raise HTTPException(e.response.status_code, "API request failed")
except httpx.ConnectError as e:
    logger.error(f"Connection failed: {e}")
    raise HTTPException(503, "Service unavailable")
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON response: {e}")
    raise HTTPException(502, "Invalid API response")
```

**4. Not using dependency injection for shared resources**

```python
# ❌ BAD: Creating new client for every request
@router.post("/v1/chat")
async def chat(request: ChatRequest):
    # New client created every time - wasteful!
    client = CopilotClient(token=token)
    return await client.create_completion(...)

# ✅ GOOD: Use FastAPI dependency injection
@router.post("/v1/chat")
async def chat(request: ChatRequest, client: CopilotClient = Depends(get_copilot_client)):
    # Same client instance reused
    return await client.create_completion(...)
```

**5. Forgetting to catch HTTPException to avoid double-raising**

```python
# ❌ BAD: HTTPException gets caught and re-raised
try:
    await some_operation()
except HTTPException as e:
    logger.error(f"Error: {e}")
    raise  # This creates a nested error!

except Exception as e:
    logger.error(f"Error: {e}")
    raise HTTPException(500, "Failed")

# ✅ GOOD: Re-raise HTTPException immediately
try:
    await some_operation()
except HTTPException:
    raise  # Immediately re-raise
except Exception as e:
    logger.error(f"Error: {e}")
    raise HTTPException(500, "Failed")
```

---

## 5. Development Environment

### Minimum Python Version Requirement

**Required: Python 3.11+**

This is enforced in [pyproject.toml](pyproject.toml#L5):
```toml
[project]
requires-python = ">=3.11"
```

**Why 3.11?**
- `str | None` union syntax (PEP 604)
- `list[dict[str, Any]]` generics syntax
- Exception groups (not used but available)
- Faster performance
- Better type inference

### Required Services/Dependencies

**Core dependencies** ([pyproject.toml](pyproject.toml#L5-L16)):
```toml
dependencies = [
    "fastapi>=0.115.0",           # Web framework
    "uvicorn[standard]>=0.32.0",  # ASGI server
    "httpx>=0.27.0",              # Async HTTP client
    "pydantic>=2.9.0",            # Data validation
    "pydantic-settings>=2.5.0",   # Settings management
    "sse-starlette>=2.1.0",       # SSE support
    "typer>=0.12.0",              # CLI framework
    "loguru>=0.7.0",              # Logging
    "apscheduler>=3.10.0",        # Background tasks
    "python-dotenv>=1.0.0",       # .env support
    "rich>=13.0.0",               # Terminal formatting
]
```

**Dev dependencies**:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
    "pytest-httpx>=0.36.0",
    "ruff>=0.8.0",
]
```

### Environment Setup Steps

**1. Install uv (package manager):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Sync dependencies:**
```bash
cd /path/to/copilot-proxy-py
uv sync
```

**3. Authenticate with GitHub:**
```bash
uv run run_proxy.py auth
```

**4. Start development server:**
```bash
uv run run_proxy.py start-server --verbose --port 4242
```

**5. Test with curl:**
```bash
# Health check
curl http://localhost:4242/health

# List models
curl http://localhost:4242/v1/models

# Chat completion
curl -X POST http://localhost:4242/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Troubleshooting Tips

**Issue: "GitHub token not found"**
```bash
# Solution: Run authentication
uv run run_proxy.py auth

# Manually check token location:
ls -la ../copilot-data/github_token

# If directory doesn't exist:
mkdir -p ../copilot-data
```

**Issue: "Port already in use"**
```bash
# Find process using port
lsof -i :4242

# Kill process
kill -9 <PID>

# Or use different port
uv run run_proxy.py start-server --port 4243
```

**Issue: "Module not found" errors**
```bash
# Reinstall dependencies
uv sync

# Clear cache and reinstall
uv cache clean
uv sync

# Verify Python version
python --version  # Must be 3.11+
```

**Issue: "Copilot token exchange failed"**
```bash
# Enable verbose logging to see details
uv run run_proxy.py start-server --verbose --show-token

# Check GitHub PAT scopes
# PAT needs: read:user scope for device code flow

# Try different account type
uv run run_proxy.py start-server --account-type business
```

**Issue: "Connection refused" to Copilot API**
```bash
# Check network connectivity
ping api.githubcopilot.com

# Check if token is expired
uv run run_proxy.py debug-info --verbose

# Manually refresh token
uv run run_proxy.py auth
```

**Issue: Tests failing with async errors**
```bash
# Ensure pytest-asyncio is installed
uv add --dev pytest-asyncio

# Run specific test file
uv run pytest test_basic.py -v

# Run with async mode
uv run pytest test_basic.py --asyncio-mode=auto
```

### Running the Development Server

**Start with auto-reload (uvicorn directly):**
```bash
uv run uvicorn copilot_proxy.api.app:app \
  --host 0.0.0.0 \
  --port 4242 \
  --reload \
  --log-level debug
```

**Start via CLI (standard way):**
```bash
uv run run_proxy.py start-server --verbose --rate-limit 1 --wait
```

**Start with environment variables:**
```bash
# Create .env file
cat > .env << EOF
PORT=4242
HOST=0.0.0.0
ACCOUNT_TYPE=individual
VERBOSE=true
RATE_LIMIT_SECONDS=1
RATE_LIMIT_WAIT=true
SHOW_TOKEN=false
EOF

# Start (will read from .env)
uv run run_proxy.py start-server
```

### Testing Strategy

**Run all tests:**
```bash
uv run pytest
```

**Run with coverage:**
```bash
uv run pytest --cov=copilot_proxy --cov-report=html
```

**Test specific endpoint:**
```bash
# Use test file pattern
uv run pytest tests/test_routes/test_chat.py -v
```

**Test with verbose output:**
```bash
uv run pytest -v -s
```

### Debugging

**Enable verbose logging:**
```bash
uv run run_proxy.py start-server --verbose --show-token
```

**Check debug endpoint:**
```bash
curl http://localhost:4242/debug/token
```

**Check request/response logs:**
```bash
# List all log files
ls -l .cache/logs/*/ 

# View latest request
ls -t .cache/logs/*/*.json | head -1 | xargs cat | python3 -m json.tool

# Count requests per hour
for dir in .cache/logs/*/; do
  echo "$dir: $(ls "$dir"/*.json 2>/dev/null | wc -l) requests"
done
```

**Use pytest debugger:**
```bash
# Drop into pdb on failure
uv run pytest --pdb

# Drop into ipdb if installed
uv run pytest --pdbcls=IPython.terminal.debugger:TerminalPdb --pdb
```

### Code Quality Tools

**Run linter:**
```bash
# Using ruff (defined in pyproject.toml)
uv run ruff check src/

# Auto-fix issues
uv run ruff check --fix src/

# Check specific file
uv run ruff check src/copilot_proxy/cli/app.py
```

**Run formatter (if configured):**
```bash
# Check formatting
uv run ruff format --check src/

# Format code
uv run ruff format src/
```

### Common Development Checklist

Before committing/pushing:
- [ ] Code follows type hinting conventions (use `|` not `Optional`)
- [ ] All async functions are properly awaited
- [ ] Error handling logs full context (`type(e).__name__`: {e}`)
- [ ] Sensitive data (tokens) are masked in logs
- [ ] New CLI commands registered in `cli/app.py`
- [ ] New API routes registered in `api/app.py`
- [ ] Rate limiting checked in all API routes
- [ ] Request/response logging added (`last 400 chars`)
- [ ] Dependencies exported in `__init__.py` if needed
- [ ] Tests pass locally (`uv run pytest`)
- [ ] Linter passes (`uv run ruff check`)

---

## Appendix: Quick Reference

### Import Patterns

```python
# ✅ Module imports (within copilot_proxy package)
from ..utils.logger import get_logger  # Up/down within package
from ...core.state import get_state    # Multiple levels up

# ✅ External imports
import httpx
import typer
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger as loguru_logger
from sse_starlette.sse import EventSourceResponse

# ✅ Type imports
from typing import AsyncGenerator, Optional, Any
from datetime import datetime
```

### Common Data Structures

```python
# Global state ([core/state.py](src/copilot_proxy/core/state.py#L1-L33))
state = get_state()
state.copilot_token  # str | None
state.rate_limit_seconds  # int | None
state.rate_limit_wait  # bool

# Token manager
token_manager = get_token_manager()
token = await token_manager.ensure_valid_token()

# Rate limiter
rate_limiter = get_rate_limiter()
await rate_limiter.check_rate_limit(
    rate_limit_seconds=5,
    wait_mode=True,
)

# HTTP client (in services)
async with httpx.AsyncClient() as client:
    response = await client.get(url, headers=headers)
    return response.json()
```

### Error Handling Template

```python
from fastapi import HTTPException
from ..utils.logger import get_logger

logger = get_logger(__name__)

async def your_function():
    try:
        result = await some_operation()
        return result
    except HTTPException:
        raise  # Re-raise immediately
    except ValueError as e:
        logger.error(f"Validation error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        logger.error(f"API error (HTTP {e.response.status_code}): {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Logging Template

```python
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Start of function
logger.info(f"Processing request - param: {value}")

# Debug info (large data truncated)
payload_dict = request.model_dump()
logger.debug(f"Request payload (last 400 chars): {str(payload_dict)[-400:]}")

# Success
logger.info("Operation completed successfully")

# Error (with full type)
logger.error(f"Operation failed: {type(e).__name__}: {e}")

# Sensitive data (masked)
token_preview = token[:10] + "..." if token else "None"
logger.debug(f"Token: {token_preview}")
```

---

## Summary

This guide covers the essential conventions and patterns used in the Copilot Proxy project. Follow these patterns to:

✅ Maintain code consistency  
✅ Avoid common pitfalls  
✅ Write production-ready code  
✅ Ensure proper error handling  
✅ Follow async/await best practices  
✅ Use logging effectively  
✅ Handle edge cases properly  

For questions, refer to the implementation files linked throughout this document.

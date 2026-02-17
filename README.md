# Copilot VLLM-Compatible Proxy (Python)

A Python-based VLLM-compatible proxy server that sits between clients and GitHub Copilot's API, providing a standardized OpenAI and Anthropic-compatible interface for LLM interactions.

## Features

✅ **OpenAI-Compatible API** - Use standard OpenAI SDKs and tools (LangChain, Claude Code, etc.)
✅ **Anthropic-Compatible API** - Works with Anthropic SDK and tools
✅ **Streaming Support** - Real-time chat completions with Server-Sent Events (SSE)
✅ **Non-Streaming** - Full response buffering for standard requests
✅ **Auto-Token Refresh** - Automatic Copilot token refresh before expiry
✅ **Rate Limiting** - Configurable request rate limiting with wait/reject modes
✅ **GitHub Authentication** - Device code OAuth flow for GitHub login
✅ **Production Ready** - Async/await throughout, connection pooling, proper error handling

## Installation

### Requirements
- Python 3.11+
- `uv` package manager (recommended)

### Setup

1. **Clone the repository** (if not already done):
```bash
cd /Users/anhvth/projects/copilot-reverse-proxy/copilot-proxy-py
```

2. **Install dependencies with uv**:
```bash
uv sync
```

## Quick Start (Docker)

### 1. Build and Start with Docker Compose

```bash
# Build and start the container
docker compose up -d --build

# The server is now running on http://localhost:4242
```

### 2. Copy GitHub Token to Container

If you already have a GitHub token in `../copilot-data/github_token`:

```bash
# Copy token to the Docker volume
docker cp ../copilot-data/github_token copilot-proxy:/app/copilot-data/github_token

# Restart the container to pick up the token
docker compose restart
```

If you need to authenticate:

```bash
# Run the auth command in the container
docker compose exec copilot-proxy uv run run_proxy.py authenticate
# Or authenticate locally, then copy the token
```

### 3. Verify It's Working

```bash
# Check container health
docker compose ps

# Test health endpoint
curl http://localhost:4242/health

# View logs
docker compose logs -f copilot-proxy
```

### 4. Test with OpenAI SDK

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:4242/v1",
    api_key="dummy"  # Not used, but required
)

# Non-streaming
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content, end="", flush=True)
```

### 5. Test with Anthropic SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:4242",
    api_key="dummy"
)

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
print(message.content[0].text)
```

## CLI Commands

### Start Server
```bash
uv run run_proxy.py start [OPTIONS]

Options:
  -p, --port INTEGER              Server port (default: 4242)
  --host TEXT                     Server host (default: 0.0.0.0)
  -v, --verbose                   Verbose logging
  --show-token                    Show token in logs (security: don't use in production)
  --rate-limit INTEGER            Rate limit in seconds between requests
  --wait                          Wait when rate limited (vs reject with 429)
  --manual-approve                Require approval per request
  --account-type [individual|business|enterprise]
                                  Account type (default: individual)
```

### GitHub Authentication
```bash
uv run run_proxy.py auth [OPTIONS]

Options:
  -v, --verbose                   Verbose logging
```

### Check Copilot Usage
```bash
uv run run_proxy.py check-usage [OPTIONS]

Options:
  -v, --verbose                   Verbose logging
```

### Debug Information
```bash
uv run run_proxy.py debug [OPTIONS]

Options:
  -v, --verbose                   Verbose logging
```

## API Endpoints

### OpenAI-Compatible Endpoints

- `GET /health` - Health check
- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Chat completions (OpenAI format)
- `POST /v1/completions` - Legacy completions
- `POST /v1/embeddings` - Create embeddings

### Anthropic-Compatible Endpoints

- `POST /v1/messages` - Messages API (Anthropic format)
- `POST /v1/messages/count_tokens` - Token counting

### Additional Endpoints

- `GET /usage` - Copilot usage statistics
- `GET /token` - Token information (if `--show-token` enabled)
- `GET /debug/token` - Debug token info

## Configuration

### Docker Compose

The [docker-compose.yml](docker-compose.yml) file includes:
- Named volume `copilot-data` for persistent token storage
- Health check endpoint
- Automatic restart policy
- Environment variables

### Environment Variables

Create `.env` file in project root (for local development):

```env
PORT=4242
HOST=0.0.0.0
ACCOUNT_TYPE=individual
VERBOSE=false
RATE_LIMIT_SECONDS=None
RATE_LIMIT_WAIT=false
MANUAL_APPROVE=false
SHOW_TOKEN=false
COPILOT_DATA_DIR=/app/copilot-data
```

### Token File Location

GitHub token is stored at: `../copilot-data/github_token`

Shared with TypeScript implementation for interoperability.

## Architecture

### Directory Structure

```
copilot-proxy-py/
├── run_proxy.py                 # Entry point
├── pyproject.toml              # Project configuration
├── .python-version             # Python version
└── src/copilot_proxy/
    ├── cli/                    # CLI commands
    ├── config/                 # Configuration
    ├── core/                   # Token management, rate limiting
    ├── services/               # GitHub and Copilot API clients
    ├── api/                    # FastAPI server
    ├── translators/            # API format translation
    ├── schemas/                # Pydantic models
    └── utils/                  # Utilities
```

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Web Framework | FastAPI |
| HTTP Client | httpx |
| CLI Framework | Typer |
| Streaming | sse-starlette |
| Validation | Pydantic v2 |
| Logging | loguru |
| Server | uvicorn |
| Package Manager | uv |

## Rate Limiting

### Wait Mode (Default for --wait)
Waits between requests to respect rate limit:

```bash
uv run run_proxy.py start --rate-limit 5 --wait
# Enforces 5 seconds between requests
```

### Reject Mode (Default)
Returns 429 status code when rate limited:

```bash
uv run run_proxy.py start --rate-limit 5
# Returns 429 if request within 5 seconds of last one
```

## Token Management

### Auto-Refresh
- Copilot token refreshes automatically 60 seconds before expiry
- Background task runs every 30 seconds
- No action required from user

### Manual Token Refresh
If you encounter `401 Unauthorized`:

```bash
uv run run_proxy.py auth
uv run run_proxy.py start
```

## Troubleshooting

### "GitHub token not found"
```bash
uv run run_proxy.py auth
```

### "Copilot token exchange failed"
- Check GitHub PAT has required scopes
- Verify `--account-type` matches your account

### "Port already in use"
```bash
uv run run_proxy.py start --port 4142
```

### "Connection refused"
- Ensure server is running: `uv run run_proxy.py start`
- Check port with: `lsof -i :4242`

## Development

### Running Tests
```bash
uv run pytest
```

### Debugging
```bash
uv run run_proxy.py debug --verbose
```

### Verbose Logging
```bash
uv run run_proxy.py start --verbose
```

## Production Deployment

### Docker Compose (Recommended)

```bash
# Start in detached mode
docker compose up -d

# View logs
docker compose logs -f copilot-proxy

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

### Using Docker Directly

```bash
# Build image
docker build -t copilot-proxy-py .

# Run container
docker run -d \
  --name copilot-proxy \
  -p 4242:4242 \
  -v copilot-data:/app/copilot-data \
  -e COPILOT_DATA_DIR=/app/copilot-data \
  copilot-proxy-py
```

### Local Development

```bash
# Install dependencies
uv sync

# Authenticate
uv run run_proxy.py authenticate

# Start server
uv run run_proxy.py start-server --verbose
```
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install uv
RUN uv sync

ENV PYTHONUNBUFFERED=1
EXPOSE 4242

CMD ["uv", "run", "run_proxy.py", "start"]
```

## Comparison with TypeScript Version

| Feature | Python | TypeScript |
|---------|--------|-----------|
| Entry Point | `uv run run_proxy.py` | `bun run` |
| Package Manager | uv | bun |
| Framework | FastAPI | Express |
| Token Refresh | asyncio | Node.js events |
| CLI | Typer | Commander.js |
| Completeness | ✅ Full parity | ✅ Original |

Both versions share:
- Same `../copilot-data/` token storage
- Compatible API endpoints
- Token refresh logic
- Rate limiting

## Limitations

- ⚠️ Manual approval mode not yet implemented
- ⚠️ Vision request headers added but image forwarding untested
- ⚠️ Tool use/function calling not fully tested

## Contributing

Issues and PRs welcome!

## License

MIT (same as TypeScript version)

## Related Projects

- [copilot-api](../copilot-api) - Original TypeScript implementation
- [copilot-data](../copilot-data) - Shared token storage directory

## Support

For issues:
1. Check troubleshooting section
2. Run `uv run run_proxy.py debug --verbose`
3. Check logs for detailed error messages

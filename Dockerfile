FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic pydantic-settings sse-starlette typer loguru apscheduler python-dotenv rich

# Copy application code
COPY src/ ./src/
COPY run_proxy.py ./

# Add src to Python path for proper imports
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Create copilot-data directory for shared token storage
RUN mkdir -p /app/copilot-data
ENV COPILOT_DATA_DIR=/app/copilot-data
ENV PYTHONUNBUFFERED=1

# Expose the default port
EXPOSE 4242

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:4242/health').read()" || exit 1

# Run the server directly with Python
CMD ["python", "run_proxy.py", "start-server", "--host", "0.0.0.0", "--port", "4242"]

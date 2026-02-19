FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (rarely changes) — cached layer
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# Copy application code (changes frequently)
COPY src/ ./src/
COPY config.yaml ./
COPY run.py ./
COPY live_conversations.py ./

# Add src to Python path for proper imports
ENV PYTHONPATH=/app/src:$PYTHONPATH
ENV PATH=/app/.venv/bin:$PATH

# Create copilot-data directory for shared token storage
RUN mkdir -p /app/copilot-data
ENV COPILOT_DATA_DIR=/app/copilot-data
ENV PYTHONUNBUFFERED=1

# Expose the default ports (4242 = copilot proxy, 4343 = GLM proxy)
EXPOSE 4343

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:4343/health').read()" || exit 1

# Run the server directly with Python
CMD ["python", "run.py", "config.yaml"]

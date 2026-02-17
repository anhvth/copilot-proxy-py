"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware import RequestLoggingMiddleware
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Copilot VLLM-Compatible Proxy",
        description="OpenAI and Anthropic compatible proxy for GitHub Copilot API",
        version="0.1.0",
    )

    # Request/response logging middleware (always enabled)
    app.add_middleware(RequestLoggingMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from .routes import chat, completions, embeddings, health, models, token, usage, messages

    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(completions.router)
    app.include_router(embeddings.router)
    app.include_router(messages.router)
    app.include_router(token.router)
    app.include_router(usage.router)

    logger.info("FastAPI app created successfully")

    return app

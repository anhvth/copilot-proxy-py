"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .middleware import RequestLoggingMiddleware
from ..config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""
    
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB
    
    async def dispatch(self, request: Request, call_next):
        """Process request with size limit check."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.MAX_REQUEST_SIZE:
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request too large. Maximum size: {self.MAX_REQUEST_SIZE} bytes"
                    )
            except ValueError:
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Note: Strict-Transport-Security should only be set behind HTTPS
        # Leaving it out for local development
        
        return response


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

    # Security headers middleware (applied first to all responses)
    app.add_middleware(SecurityHeadersMiddleware)

    # Request size limit middleware (applied before request processing)
    app.add_middleware(RequestSizeLimitMiddleware)

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

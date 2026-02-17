"""Middleware for logging requests and responses."""

import json
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...utils.request_logger import get_request_logger, RequestLogger
from ...utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_request_body(body: Any) -> Any:
    """Remove sensitive data from request body for logging.
    
    Args:
        body: Request body (dict, list, or primitive)
        
    Returns:
        Sanitized version with sensitive data redacted
    """
    sensitive_keys = {
        "api_key", "apikey", "token", "password", "auth",
        "authorization", "secret", "key", "credentials"
    }
    
    if isinstance(body, dict):
        sanitized = {}
        for key, value in body.items():
            # Check if key is sensitive (case-insensitive)
            key_lower = key.lower() if isinstance(key, str) else str(key).lower()
            if key_lower in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, (dict, list)):
                sanitized[key] = _sanitize_request_body(value)
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(body, list):
        return [_sanitize_request_body(item) for item in body]
    else:
        return body


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    def __init__(self, app: ASGIApp, cache_dir: Optional[Path] = None) -> None:
        """Initialize request logging middleware.

        Args:
            app: ASGI application
            cache_dir: Optional cache directory path (uses settings default if not provided)
        """
        super().__init__(app)
        self.request_logger: RequestLogger = get_request_logger(cache_dir=cache_dir)

    def _is_streaming_request(self, request: Request, request_body: dict) -> bool:
        """Check if this is a streaming request.

        Args:
            request: The incoming request
            request_body: The parsed request body

        Returns:
            True if this is a streaming request, False otherwise
        """
        # Check path-based detection
        path = request.url.path
        streaming_paths = [
            "/v1/chat/completions",
            "/chat/completions",
            "/v1/messages",
            "/messages",
        ]
        if any(path.endswith(sp) for sp in streaming_paths):
            # Check query params for stream=true
            if request.query_params.get("stream") == "true":
                return True
            # Check request body for stream=true
            if request_body and request_body.get("stream") is True:
                return True

        return False

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and log both request and response.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from the next handler
        """
        # Read request body for logging
        request_body = {}
        error = None
        response_body = {}

        # Read request body
        try:
            raw_body = await request.body()
            if raw_body:
                try:
                    request_body = json.loads(raw_body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    request_body = {"raw": raw_body.decode("utf-8", errors="ignore")[:1000]}
        except Exception as e:
            logger.warning(f"Failed to read request body: {e}")

        # Sanitize sensitive data from request body
        request_body = _sanitize_request_body(request_body)

        # Process request
        exception_raised = None
        try:
            response = await call_next(request)
        except Exception as e:
            exception_raised = e
            error = str(e)
            # Create an error response
            try:
                from fastapi import HTTPException
                if isinstance(e, HTTPException):
                    response = Response(
                        content=json.dumps({"error": e.detail}),
                        status_code=e.status_code,
                        media_type="application/json",
                    )
                else:
                    response = Response(
                        content=json.dumps({"error": str(e)}),
                        status_code=500,
                        media_type="application/json",
                    )
            except Exception:
                raise e

        # Try to read response body for logging (skip for streaming responses)
        try:
            # Check if this is a streaming request
            is_streaming = self._is_streaming_request(request, request_body)

            if is_streaming:
                # Skip reading response body for streaming responses to avoid consuming the stream
                logger.debug(f"Skipping response body logging for streaming endpoint: {request.url.path}")
                response_body = {}
            else:
                # Get response body
                response_body_bytes = b""
                response_body_type = response.headers.get("content-type", "")

                # Read from response object
                if hasattr(response, "body_iterator"):
                    async for chunk in response.body_iterator:
                        response_body_bytes += chunk
                elif hasattr(response, "body"):
                    response_body_bytes = response.body if isinstance(response.body, bytes) else str(response.body).encode("utf-8")
                elif hasattr(response, "_content"):
                    response_body_bytes = response._content

                # Parse response body based on content type
                if response_body_bytes:
                    if "json" in response_body_type:
                        try:
                            response_body = json.loads(response_body_bytes.decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            response_body = {"raw": response_body_bytes.decode("utf-8", errors="ignore")[:1000]}
                    else:
                        response_body = {"raw": response_body_bytes.decode("utf-8", errors="ignore")[:1000]}

                # Create new response with the body if we consumed it
                if hasattr(response, "body_iterator"):
                    response = Response(
                        content=response_body_bytes,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
        except Exception as e:
            logger.debug(f"Failed to read response body: {e}")

        # Log the request/response pair
        try:
            await self.request_logger.log_pair(
                request=request,
                response=response,
                request_body=request_body,
                response_body=response_body,
                error=error,
            )
        except Exception as e:
            logger.error(f"Failed to log request/response: {e}")

        # Re-raise exception if one occurred
        if exception_raised:
            raise exception_raised

        return response


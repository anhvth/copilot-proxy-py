"""HTTP client configuration and utilities."""

import httpx

from ..config.constants import DEFAULT_HEADERS


def create_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create configured async HTTP client.

    Args:
        timeout: Request timeout in seconds

    Returns:
        Configured httpx.AsyncClient
    """
    return httpx.AsyncClient(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    )


def create_sync_http_client(timeout: float = 30.0) -> httpx.Client:
    """Create configured sync HTTP client.

    Args:
        timeout: Request timeout in seconds

    Returns:
        Configured httpx.Client
    """
    return httpx.Client(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    )

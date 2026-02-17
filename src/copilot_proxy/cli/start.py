"""Start server command."""

import asyncio
from typing import Optional

import typer
from pathlib import Path

from ..api.app import create_app
from ..config.paths import get_github_token_path
from ..config.settings import Settings
from ..core.state import update_state
from ..core.token_manager import get_token_manager
from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def async_main(
    port: int = typer.Option(4242, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Server host"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    show_token: bool = typer.Option(False, "--show-token", help="Show token in logs"),
    rate_limit: Optional[int] = typer.Option(
        None,
        "--rate-limit",
        help="Rate limit in seconds between requests",
    ),
    wait: bool = typer.Option(False, "--wait", help="Wait when rate limited (vs reject)"),
    manual_approve: bool = typer.Option(False, "--manual-approve", help="Require approval per request"),
    account_type: str = typer.Option("individual", "--account-type", help="Account type: individual, business, enterprise"),
):
    """Start the proxy server."""
    # Setup logging
    setup_logger(verbose=verbose, show_token=show_token)
    logger.info("Starting Copilot VLLM-compatible proxy")

    # Check for GitHub token
    token_file = get_github_token_path()
    if not token_file.exists():
        logger.error(f"GitHub token not found at {token_file}")
        logger.info("Run: uv run run_proxy.py auth")
        raise typer.Exit(code=1)

    # Initialize state
    update_state(
        account_type=account_type,
        rate_limit_seconds=rate_limit,
        rate_limit_wait=wait,
        manual_approve=manual_approve,
    )

    # Load and validate GitHub token
    token_manager = get_token_manager()
    try:
        github_token = token_manager.load_github_token()
        logger.info(f"GitHub token loaded: {github_token[:10]}...")
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load GitHub token: {e}")
        raise typer.Exit(code=1)

    # Fetch initial Copilot token
    try:
        logger.info("Fetching Copilot API token...")
        copilot_token, expires_at = await token_manager.fetch_copilot_token(github_token)
        logger.info(f"Copilot token obtained, expires at {expires_at}")
    except Exception as e:
        logger.error(f"Failed to fetch Copilot token: {e}")
        raise typer.Exit(code=1)

    # Start auto-refresh
    try:
        await token_manager.start_auto_refresh()
        logger.info("Token auto-refresh started")
    except Exception as e:
        logger.error(f"Failed to start token auto-refresh: {e}")

    # Create FastAPI app
    app = create_app()

    # Start server
    import uvicorn

    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"OpenAPI docs at http://{host}:{port}/docs")
    logger.info(f"Health check at http://{host}:{port}/health")

    try:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="debug" if verbose else "info",
        )
        server = uvicorn.Server(config)
        await server.serve()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
        token_manager.stop_auto_refresh()
    except Exception as e:
        logger.error(f"Server error: {e}")
        token_manager.stop_auto_refresh()
        raise typer.Exit(code=1)


def start_server(
    port: int = typer.Option(4242, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Server host"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    show_token: bool = typer.Option(False, "--show-token", help="Show token in logs"),
    rate_limit: Optional[int] = typer.Option(
        None,
        "--rate-limit",
        help="Rate limit in seconds between requests",
    ),
    wait: bool = typer.Option(False, "--wait", help="Wait when rate limited (vs reject)"),
    manual_approve: bool = typer.Option(False, "--manual-approve", help="Require approval per request"),
    account_type: str = typer.Option("individual", "--account-type", help="Account type: individual, business, enterprise"),
):
    """Start the proxy server."""
    asyncio.run(
        async_main(
            port=port,
            host=host,
            verbose=verbose,
            show_token=show_token,
            rate_limit=rate_limit,
            wait=wait,
            manual_approve=manual_approve,
            account_type=account_type,
        )
    )

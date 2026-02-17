"""Auth command for GitHub OAuth."""

import asyncio
from pathlib import Path

import typer

from ..config.paths import get_github_token_path
from ..services.github.auth import GitHubDeviceCodeAuth
from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def async_authenticate(verbose: bool):
    """Authenticate with GitHub and save token."""
    setup_logger(verbose=verbose)
    logger.info("GitHub Device Code OAuth Flow")

    auth = GitHubDeviceCodeAuth()

    try:
        token = await auth.authenticate()

        if not token:
            logger.error("Authentication failed or was cancelled")
            raise typer.Exit(code=1)

        # Save token to file
        token_file = get_github_token_path()
        token_file.parent.mkdir(parents=True, exist_ok=True)

        # Set restrictive permissions before writing
        token_file.touch(mode=0o600)
        token_file.write_text(token)

        logger.info(f"Token saved to {token_file}")
        logger.info("You can now start the server with: uv run run_proxy.py start")

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise typer.Exit(code=1)


def authenticate(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Authenticate with GitHub using device code flow."""
    asyncio.run(async_authenticate(verbose=verbose))

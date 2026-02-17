"""Check usage command."""

import asyncio

import typer

from ..config.paths import get_github_token_path
from ..core.token_manager import get_token_manager
from ..services.github.client import GitHubClient
from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def async_check_usage(verbose: bool):
    """Check Copilot usage from GitHub API."""
    setup_logger(verbose=verbose)
    logger.info("Checking Copilot usage")

    try:
        token_file = get_github_token_path()

        if not token_file.exists():
            logger.error(f"GitHub token not found at {token_file}")
            logger.info("Run: uv run run_proxy.py auth")
            raise typer.Exit(code=1)

        # Load token
        token = token_file.read_text().strip()

        # Get usage
        github_client = GitHubClient()
        usage = await github_client.get_copilot_usage(token)

        # Display usage
        typer.echo("\n📊 Copilot Usage:")
        typer.echo(f"  Daily: {usage.get('daily', {}).get('used', 0)}/{usage.get('daily', {}).get('total', 0)}")
        typer.echo(f"  Monthly: {usage.get('monthly', {}).get('used', 0)}/{usage.get('monthly', {}).get('total', 0)}")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to check usage: {e}")
        raise typer.Exit(code=1)


def check_usage(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Check Copilot usage quota."""
    asyncio.run(async_check_usage(verbose=verbose))

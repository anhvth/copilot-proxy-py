"""Debug command."""

import asyncio
from pathlib import Path

import typer

from ..config.paths import get_github_token_path
from ..core.token_manager import get_token_manager
from ..utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def async_debug(verbose: bool):
    """Show debug information."""
    setup_logger(verbose=verbose)

    typer.echo("\n🔍 Debug Information:")

    # Check GitHub token
    token_file = get_github_token_path()
    typer.echo(f"\n📁 Token File: {token_file}")
    typer.echo(f"   Exists: {token_file.exists()}")

    if token_file.exists():
        token = token_file.read_text().strip()
        typer.echo(f"   Length: {len(token)}")
        typer.echo(f"   Preview: {token[:20]}...")

        # Try to fetch Copilot token
        token_manager = get_token_manager()
        try:
            typer.echo("\n🔐 Fetching Copilot token...")
            copilot_token, expires_at = await token_manager.fetch_copilot_token(token)
            typer.echo(f"   ✓ Success")
            typer.echo(f"   Expires: {expires_at}")
        except Exception as e:
            typer.echo(f"   ✗ Failed: {e}")
    else:
        typer.echo("   ⚠️  Token file not found")
        typer.echo(f"\n   Run: uv run run_proxy.py auth")


def debug_info(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Show debug information."""
    asyncio.run(async_debug(verbose=verbose))

"""Typer CLI application."""

import typer
from typing import Optional

from . import auth, start, check_usage, debug

app = typer.Typer(
    name="copilot-proxy",
    help="VLLM-compatible proxy for GitHub Copilot API",
    invoke_without_command=True,
    no_args_is_help=True,
)

# Register subcommands
app.command()(start.start_server)
app.command()(auth.authenticate)
app.command()(check_usage.check_usage)
app.command()(debug.debug_info)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        is_flag=True,
    ),
):
    """Copilot VLLM-compatible proxy server."""
    if version:
        typer.echo("copilot-proxy v0.1.0")
        raise typer.Exit()

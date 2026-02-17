"""Token management and authentication."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from ..config.constants import GITHUB_API_BASE, GITHUB_TOKEN_ENDPOINT
from ..config.paths import get_github_token_path
from ..services.github.auth import check_token_file_permissions
from ..utils.logger import get_logger
from .state import get_state, update_state

logger = get_logger(__name__)


class TokenManager:
    """Manages GitHub and Copilot API tokens."""

    def __init__(self):
        """Initialize token manager."""
        self.github_token: str | None = None
        self.copilot_token: str | None = None
        self.token_expires_at: datetime | None = None
        self._refresh_task: asyncio.Task | None = None

    def load_github_token(self) -> str:
        """Load GitHub token from file.

        Returns:
            GitHub token string

        Raises:
            FileNotFoundError: If token file doesn't exist
            ValueError: If token is empty
        """
        token_file = get_github_token_path()

        if not token_file.exists():
            raise FileNotFoundError(f"GitHub token file not found: {token_file}")

        # Check token file permissions for security
        check_token_file_permissions(token_file)

        token = token_file.read_text().strip()
        if not token:
            raise ValueError("GitHub token file is empty")

        self.github_token = token
        update_state(github_token=token)
        logger.info("GitHub token loaded successfully")
        return token

    async def fetch_copilot_token(self, github_token: str | None = None) -> tuple[str, datetime]:
        """Fetch Copilot API token from GitHub API.

        Args:
            github_token: GitHub PAT token (uses self.github_token if None)

        Returns:
            Tuple of (copilot_token, expiry_datetime)

        Raises:
            ValueError: If token fetch fails
        """
        token = github_token or self.github_token
        if not token:
            raise ValueError("GitHub token not available")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    GITHUB_TOKEN_ENDPOINT,
                    headers={
                        "Authorization": f"token {token}",
                        "editor-version": "vscode/1.96.0",
                        "editor-plugin-version": "copilot-chat/0.26.7",
                        "user-agent": "GitHubCopilotChat/0.26.7",
                        "x-github-api-version": "2025-04-01",
                        "x-vscode-user-agent-library-version": "electron-fetch",
                    },
                )
                response.raise_for_status()
                data = response.json()

                copilot_token = data.get("token")
                expires_in = data.get("expires_in", 3600)

                if not copilot_token:
                    raise ValueError("No token in response")

                expires_at = datetime.now() + timedelta(seconds=expires_in)

                self.copilot_token = copilot_token
                self.token_expires_at = expires_at

                update_state(
                    copilot_token=copilot_token,
                    copilot_token_expires_at=expires_at,
                )

                logger.info(f"Copilot token fetched, expires in {expires_in}s")
                return copilot_token, expires_at

            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch Copilot token: {e}")
                raise ValueError(f"Token exchange failed: {e}")

    async def ensure_valid_token(self) -> str:
        """Ensure a valid Copilot token is available.

        Returns:
            Valid Copilot token

        Raises:
            ValueError: If token cannot be obtained
        """
        if self.copilot_token and self.token_expires_at:
            time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()

            if time_until_expiry > 60:  # Valid for at least 60 more seconds
                return self.copilot_token

        logger.info("Copilot token expired or missing, fetching new one")
        token, _ = await self.fetch_copilot_token()
        return token

    async def start_auto_refresh(self, check_interval: int = 30) -> None:
        """Start background task to auto-refresh token before expiry.

        Args:
            check_interval: How often to check if refresh is needed (seconds)
        """
        if self._refresh_task and not self._refresh_task.done():
            logger.warning("Auto-refresh already running")
            return

        logger.info("Starting token auto-refresh")

        async def refresh_loop():
            while True:
                try:
                    if self.token_expires_at:
                        time_until_expiry = (
                            self.token_expires_at - datetime.now()
                        ).total_seconds()

                        # Refresh 60 seconds before expiry
                        if 0 < time_until_expiry < 60:
                            logger.info("Refreshing Copilot token (expires soon)")
                            await self.ensure_valid_token()

                    await asyncio.sleep(check_interval)

                except asyncio.CancelledError:
                    logger.info("Token auto-refresh stopped")
                    break
                except Exception as e:
                    logger.error(f"Error in token refresh loop: {e}")
                    await asyncio.sleep(check_interval)

        self._refresh_task = asyncio.create_task(refresh_loop())

    def stop_auto_refresh(self) -> None:
        """Stop background token refresh task."""
        if self._refresh_task and not self._refresh_task.done():
            logger.info("Stopping token auto-refresh")
            self._refresh_task.cancel()
            self._refresh_task = None

    def get_token(self) -> str:
        """Get current Copilot token without refresh.

        Returns:
            Copilot token if available

        Raises:
            ValueError: If token not available
        """
        if not self.copilot_token:
            raise ValueError("Copilot token not available")
        return self.copilot_token


# Global token manager instance
_token_manager: TokenManager | None = None


def get_token_manager() -> TokenManager:
    """Get or create global token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager

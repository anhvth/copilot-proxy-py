"""GitHub API client."""

import httpx

from ...config.constants import GITHUB_API_BASE
from ...utils.logger import get_logger
from .auth import GitHubDeviceCodeAuth

logger = get_logger(__name__)


class GitHubClient:
    """GitHub API client."""

    def __init__(self):
        """Initialize GitHub client."""
        self.auth = GitHubDeviceCodeAuth()

    async def get_user_info(self, access_token: str) -> dict:
        """Get authenticated user information.

        Args:
            access_token: GitHub access token

        Returns:
            User info dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def get_copilot_usage(self, access_token: str) -> dict:
        """Get Copilot usage information.

        Args:
            access_token: GitHub access token

        Returns:
            Usage information dictionary
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/copilot_internal/user/usage",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

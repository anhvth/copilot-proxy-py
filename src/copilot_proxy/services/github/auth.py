"""GitHub Device Code OAuth flow."""

import asyncio
import time
from typing import Optional

import httpx

from ...config.constants import GITHUB_BASE_URL
from ...utils.logger import get_logger
from .schemas import GitHubDeviceAuthorizationResponse, GitHubTokenResponse

logger = get_logger(__name__)


class GitHubDeviceCodeAuth:
    """Implements GitHub Device Code OAuth flow."""

    CLIENT_ID = "Iv1.b507a08c87ecfe98"

    async def request_device_code(self) -> GitHubDeviceAuthorizationResponse:
        """Request device code from GitHub.

        Returns:
            Device authorization response with user_code and verification_uri
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITHUB_BASE_URL}/login/device/code",
                json={
                    "client_id": self.CLIENT_ID,
                    "scope": "read:user",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            return GitHubDeviceAuthorizationResponse(**data)

    async def wait_for_user_authorization(
        self,
        device_code: str,
        user_code: str,
        verification_uri: str,
        expires_in: int,
        poll_interval: int,
    ) -> Optional[str]:
        """Wait for user to authorize on GitHub and return access token.

        Args:
            device_code: Device code from request_device_code
            user_code: User code to display to user
            verification_uri: URI where user should authorize
            expires_in: Seconds until device code expires
            poll_interval: Minimum seconds between polls

        Returns:
            Access token if authorized, None if timeout
        """
        deadline = time.time() + expires_in

        while time.time() < deadline:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{GITHUB_BASE_URL}/login/oauth/access_token",
                        json={
                            "client_id": self.CLIENT_ID,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()

                    token_response = GitHubTokenResponse(**response.json())

                    if token_response.access_token:
                        logger.info("User authorized successfully")
                        return token_response.access_token

                    if token_response.error and token_response.error != "authorization_pending":
                        logger.error(
                            f"Authorization failed: {token_response.error} - "
                            f"{token_response.error_description}"
                        )
                        return None

                    logger.debug("Authorization pending...")

            except Exception as e:
                logger.error(f"Error polling for authorization: {e}")
                return None

            await asyncio.sleep(poll_interval)

        logger.warning("Device code expired before authorization")
        return None

    async def authenticate(self) -> Optional[str]:
        """Run complete OAuth flow.

        Returns:
            GitHub access token if successful, None if cancelled
        """
        logger.info("Starting GitHub Device Code OAuth flow")

        try:
            # Request device code
            auth_response = await self.request_device_code()

            logger.info(
                f"\n{'='*60}\n"
                f"Device Code: {auth_response.user_code}\n"
                f"Visit: {auth_response.verification_uri}\n"
                f"{'='*60}\n"
            )

            # Wait for user authorization
            token = await self.wait_for_user_authorization(
                device_code=auth_response.device_code,
                user_code=auth_response.user_code,
                verification_uri=auth_response.verification_uri,
                expires_in=auth_response.expires_in,
                poll_interval=auth_response.interval,
            )

            if token:
                logger.info("Authentication successful")

            return token

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return None

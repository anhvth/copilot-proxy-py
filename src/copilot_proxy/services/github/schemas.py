"""GitHub API response schemas."""

from typing import Optional

from pydantic import BaseModel


class GitHubDeviceAuthorizationResponse(BaseModel):
    """Response from GitHub device authorization endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class GitHubTokenResponse(BaseModel):
    """Response from GitHub token endpoint."""

    access_token: Optional[str] = None
    token_type: Optional[str] = None
    scope: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None
    error_uri: Optional[str] = None

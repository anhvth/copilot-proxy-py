"""FastAPI dependencies."""

from fastapi import Depends, HTTPException

from ..core.state import get_state
from ..core.token_manager import get_token_manager
from ..services.copilot.client import CopilotClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def get_copilot_token() -> str:
    """Get valid Copilot token.

    Returns:
        Valid Copilot API token

    Raises:
        HTTPException: If token not available
    """
    token_manager = get_token_manager()

    try:
        logger.debug("Attempting to get valid Copilot token")
        token = await token_manager.ensure_valid_token()
        logger.debug(f"Copilot token obtained successfully (preview: {token[:10]}...)") if token else logger.debug("Copilot token obtained successfully")
        return token
    except Exception as e:
        logger.error(f"Failed to get copilot token: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Copilot token unavailable")


def get_copilot_client(token: str = Depends(get_copilot_token)) -> CopilotClient:
    """Get Copilot API client.

    Args:
        token: Copilot API token

    Returns:
        CopilotClient instance

    Raises:
        HTTPException: If client creation fails
    """
    state = get_state()

    try:
        logger.debug(f"Creating CopilotClient with account_type: {state.account_type}")
        client = CopilotClient(
            copilot_token=token,
            account_type=state.account_type,
        )
        logger.debug(f"CopilotClient created successfully: {repr(client)}")
        return client
    except Exception as e:
        logger.error(f"Failed to create copilot client: {type(e).__name__}: {e}")
        logger.error(f"Account type: {state.account_type}")
        raise HTTPException(status_code=500, detail="Failed to create Copilot client")

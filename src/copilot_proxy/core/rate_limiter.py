"""Rate limiting implementation."""

import asyncio
from datetime import datetime
from typing import Optional

from ..utils.logger import get_logger
from .state import get_state

logger = get_logger(__name__)


class RateLimiter:
    """Handles rate limiting for API requests."""

    async def check_rate_limit(
        self,
        rate_limit_seconds: Optional[int] = None,
        wait_mode: bool = False,
    ) -> bool:
        """Check and enforce rate limit.

        Args:
            rate_limit_seconds: Seconds to wait between requests (None = no limit)
            wait_mode: If True, wait instead of returning False

        Returns:
            True if request is allowed (or was waited for)

        Raises:
            Exception: If rate limited and wait_mode is False
        """
        if rate_limit_seconds is None:
            return True

        state = get_state()
        now = datetime.now()

        if state.last_request_timestamp is None:
            state.last_request_timestamp = now
            return True

        elapsed = (now - state.last_request_timestamp).total_seconds()

        if elapsed < rate_limit_seconds:
            wait_time = rate_limit_seconds - elapsed

            if wait_mode:
                logger.debug(f"Rate limited: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                state.last_request_timestamp = datetime.now()
                return True
            else:
                logger.warning(f"Rate limited: {wait_time:.1f}s until next request allowed")
                raise Exception(f"Rate limited. Wait {wait_time:.1f}s before next request.")

        state.last_request_timestamp = now
        return True


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter

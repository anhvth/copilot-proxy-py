"""Quick test script to verify basic functionality."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from copilot_proxy.config import get_settings
from copilot_proxy.core.state import get_state
from copilot_proxy.core.token_manager import get_token_manager
from copilot_proxy.utils.logger import setup_logger
from copilot_proxy.services.github.auth import GitHubDeviceCodeAuth
from copilot_proxy.api.app import create_app


async def main():
    """Run basic tests."""
    print("🧪 Testing Copilot Proxy Components\n")

    # Test 1: Settings
    print("✓ Test 1: Settings")
    settings = get_settings()
    print(f"  Port: {settings.port}")
    print(f"  Account Type: {settings.account_type}")

    # Test 2: State
    print("\n✓ Test 2: Application State")
    state = get_state()
    print(f"  Has GitHub Token: {state.github_token is not None}")
    print(f"  Account Type: {state.account_type}")

    # Test 3: Logger
    print("\n✓ Test 3: Logger Setup")
    setup_logger(verbose=True)
    from copilot_proxy.utils.logger import get_logger

    logger = get_logger(__name__)
    logger.debug("Debug logging works!")

    # Test 4: FastAPI App
    print("\n✓ Test 4: FastAPI App Creation")
    app = create_app()
    print(f"  App created: {app.title}")
    print(f"  OpenAPI docs at: /docs")

    # Test 5: Token Manager
    print("\n✓ Test 5: Token Manager")
    token_manager = get_token_manager()
    print(f"  Token Manager: {token_manager.__class__.__name__}")

    # Test 6: GitHub Auth
    print("\n✓ Test 6: GitHub Device Code Auth")
    auth = GitHubDeviceCodeAuth()
    print(f"  Client ID: {auth.CLIENT_ID}")

    print("\n✅ All basic tests passed!")
    print("\nNext steps:")
    print("1. Run: uv run run_proxy.py auth")
    print("2. Run: uv run run_proxy.py start-server --verbose")
    print("3. Test with: curl http://localhost:4141/health")


if __name__ == "__main__":
    asyncio.run(main())

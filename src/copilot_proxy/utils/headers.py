"""Header generation utilities."""

from uuid import uuid4

from ..config.constants import COPILOT_HEADERS_BASE


def generate_request_headers(
    copilot_token: str,
    vscode_version: str = "1.96.0",
    editor_plugin_version: str = "copilot-chat/0.26.7",
    has_vision: bool = False,
    is_agent: bool = False,
) -> dict:
    """Generate headers for Copilot API requests.

    Args:
        copilot_token: Copilot API bearer token
        vscode_version: VS Code version
        editor_plugin_version: Editor plugin version
        has_vision: Include vision request header
        is_agent: Set X-Initiator to "agent" instead of "user"

    Returns:
        Dictionary of headers for the request
    """
    headers = {
        "Authorization": f"Bearer {copilot_token}",
        "x-request-id": str(uuid4()),
        "X-Initiator": "agent" if is_agent else "user",
        "editor-version": f"vscode/{vscode_version}",
        "editor-plugin-version": editor_plugin_version,
        **COPILOT_HEADERS_BASE,
    }

    if has_vision:
        headers["copilot-vision-request"] = "true"

    return headers


def detect_agent_request(messages: list) -> bool:
    """Detect if request is from an agent (has assistant/tool roles).

    Args:
        messages: List of message objects

    Returns:
        True if request contains assistant or tool roles
    """
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        if role in ("assistant", "tool"):
            return True
    return False


def detect_vision_content(messages: list) -> bool:
    """Detect if messages contain image content.

    Args:
        messages: List of message objects

    Returns:
        True if any message contains image content
    """
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)

        if isinstance(content, str):
            continue

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "image" or "image_url" in item:
                        return True
                elif hasattr(item, "type") and item.type == "image":
                    return True

    return False

"""API constants and configurations."""

# GitHub URLs
# Use GITHUB_BASE_URL for device code OAuth flow (github.com)
# Use GITHUB_API_BASE for regular API calls (api.github.com)
GITHUB_BASE_URL = "https://github.com"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN_ENDPOINT = "https://api.github.com/copilot_internal/v2/token"
GITHUB_APP_SCOPES = "read:user"

# Copilot API endpoints by account type
COPILOT_API_ENDPOINTS = {
    "individual": "https://api.githubcopilot.com",
    "business": "https://api.business.githubcopilot.com",
    "enterprise": "https://api.enterprise.githubcopilot.com",
}

# Default headers
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "GitHubCopilotChat/0.26.7",
}

# Copilot-specific headers
COPILOT_HEADERS_BASE = {
    "copilot-integration-id": "vscode-chat",
    "editor-version": "vscode/1.96.0",
    "editor-plugin-version": "copilot-chat/0.26.7",
    "user-agent": "GitHubCopilotChat/0.26.7",
    "openai-intent": "conversation-panel",
    "x-github-api-version": "2025-04-01",
}

# Common model names
MODEL_NAMES = {
    "gpt-4": "gpt-4",
    "gpt-4o": "gpt-4o",
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
}

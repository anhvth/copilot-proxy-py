"""Copilot API client."""

from typing import Optional

import httpx

from ...config.constants import COPILOT_API_ENDPOINTS
from ...core.state import get_state
from ...utils.headers import detect_agent_request, detect_vision_content, generate_request_headers
from ...utils.logger import get_logger

logger = get_logger(__name__)


class CopilotClient:
    """Client for Copilot API."""

    def __init__(self, copilot_token: str, account_type: str = "individual"):
        """Initialize Copilot client.

        Args:
            copilot_token: Copilot API bearer token
            account_type: Account type (individual, business, enterprise)
        """
        self.copilot_token = copilot_token
        self.account_type = account_type
        self.base_url = COPILOT_API_ENDPOINTS.get(account_type, COPILOT_API_ENDPOINTS["individual"])
        self.http_client: Optional[httpx.AsyncClient] = None

        logger.debug(f"CopilotClient initialized - account_type: {account_type}, base_url: {self.base_url}")

    def __repr__(self) -> str:
        """Return string representation of the client.

        Returns:
            String representation with masked token
        """
        token_preview = self.copilot_token[:10] + "..." if self.copilot_token else "None"
        return f"CopilotClient(account_type={self.account_type}, base_url={self.base_url}, token={token_preview})"

    async def __aenter__(self):
        """Async context manager entry."""
        self.http_client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.http_client:
            await self.http_client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=60.0)
        return self.http_client

    def _get_headers(
        self,
        messages: Optional[list] = None,
        content_type: str = "application/json",
    ) -> dict:
        """Generate headers for request.

        Args:
            messages: Optional message list to detect agent/vision
            content_type: Content type header

        Returns:
            Headers dictionary
        """
        state = get_state()

        headers = generate_request_headers(
            copilot_token=self.copilot_token,
            vscode_version=state.vscode_version,
            editor_plugin_version=state.editor_plugin_version,
            has_vision=detect_vision_content(messages) if messages else False,
            is_agent=detect_agent_request(messages) if messages else False,
        )

        headers["Content-Type"] = content_type

        return headers

    @staticmethod
    def _sanitize_headers(headers: dict) -> dict:
        """Sanitize headers for logging by masking sensitive values.

        Args:
            headers: Original headers dictionary

        Returns:
            Headers with sensitive values masked
        """
        sanitized = headers.copy()
        if "Authorization" in sanitized:
            auth = sanitized["Authorization"]
            if isinstance(auth, str) and auth.startswith("Bearer "):
                # Keep first 10 chars and last 4 chars, mask the rest
                token = auth[7:]  # Remove "Bearer "
                if len(token) > 14:
                    masked = f"Bearer {token[:10]}...{token[-4:]}"
                else:
                    masked = "Bearer ***masked***"
                sanitized["Authorization"] = masked
        return sanitized

    async def get_models(self) -> list[dict]:
        """Fetch available models.

        Returns:
            List of available models
        """
        url = f"{self.base_url}/models"
        try:
            client = await self._get_client()
            headers = self._get_headers()

            logger.debug(f"Fetching models from {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")

            response = await client.get(url, headers=headers)

            logger.debug(f"Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()

            logger.debug(f"Fetched {len(data.get('data', []))} models")
            return data.get("data", [])

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch models (HTTP {e.response.status_code}): {e}")
            logger.error(f"Request URL: {url}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to {url}: {e}")
            logger.error(f"Connection error details: {type(e).__name__}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch models: {type(e).__name__}: {e}")
            logger.error(f"Request URL: {url}")
            # Return default models if fetch fails
            return [
                {"id": "gpt-4", "name": "GPT-4"},
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            ]

    async def create_chat_completion(
        self,
        messages: list[dict],
        model: str = "gpt-4",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Create chat completion.

        Args:
            messages: List of message objects
            model: Model name
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            stream: Whether to stream response
            **kwargs: Additional parameters

        Returns:
            Chat completion response
        """
        url = f"{self.base_url}/chat/completions"
        try:
            client = await self._get_client()
            headers = self._get_headers(messages=messages)

            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
            }

            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature

            payload.update(kwargs)

            logger.debug(f"Creating chat completion with model: {model}, stream: {stream}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            logger.debug(f"Payload (last 400 chars): {str(payload)[-400:]}")

            response = await client.post(url, json=payload, headers=headers)

            logger.debug(f"Response status: {response.status_code}")
            response.raise_for_status()

            if stream:
                return response
            else:
                response_data = response.json()
                logger.debug(f"Non-streaming response (last 400 chars): {str(response_data)[-400:]}")
                return response_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create chat completion (HTTP {e.response.status_code}): {e}")
            logger.error(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            logger.debug(f"Request payload (last 400 chars): {str(payload)[-400:]}")
            logger.error(f"Response body: {e.response.text}")
            logger.error(f"Request details: model={model}, stream={stream}, max_tokens={max_tokens}, temperature={temperature}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to {url}: {e}")
            logger.error(f"Connection error details: {type(e).__name__}: {str(e)}")
            logger.error(f"Base URL being used: {self.base_url}")
            logger.error(f"Account type: {self.account_type}")
            raise
        except Exception as e:
            logger.error(f"Chat completion failed: {type(e).__name__}: {e}")
            logger.error(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            raise

    async def stream_chat_completion(
        self,
        messages: list[dict],
        model: str = "gpt-4",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs,
    ):
        """Stream chat completion response.

        Args:
            messages: List of message objects
            model: Model name
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Yields:
            Streaming response chunks
        """
        url = f"{self.base_url}/chat/completions"
        try:
            client = await self._get_client()
            headers = self._get_headers(messages=messages)

            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
            }

            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if temperature is not None:
                payload["temperature"] = temperature

            payload.update(kwargs)

            logger.debug(f"Streaming chat completion with model: {model}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            logger.debug(f"Payload (last 400 chars): {str(payload)[-400:]}")

            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
            ) as response:
                logger.debug(f"Response status: {response.status_code}")
                response.raise_for_status()

                logger.debug("Starting to stream response")
                async for line in response.aiter_lines():
                    if line:
                        logger.debug(f"Streaming chunk (last 200 chars): {line[-200:]}")
                        yield line

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to stream chat completion (HTTP {e.response.status_code}): {e}")
            logger.error(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            logger.debug(f"Request payload (last 400 chars): {str(payload)[-400:]}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to {url}: {e}")
            logger.error(f"Connection error details: {type(e).__name__}: {str(e)}")
            logger.error(f"Base URL being used: {self.base_url}")
            logger.error(f"Account type: {self.account_type}")
            raise
        except Exception as e:
            logger.error(f"Chat completion streaming failed: {type(e).__name__}: {e}")
            logger.error(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            raise

    async def create_embeddings(
        self,
        input_text: str | list[str],
        model: str = "text-embedding-ada-002",
    ) -> dict:
        """Create embeddings.

        Args:
            input_text: Text or list of texts to embed
            model: Embedding model name

        Returns:
            Embeddings response
        """
        url = f"{self.base_url}/embeddings"
        try:
            client = await self._get_client()
            headers = self._get_headers()

            payload = {
                "input": input_text,
                "model": model,
            }

            logger.debug(f"Creating embeddings with model: {model}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")

            response = await client.post(url, json=payload, headers=headers)

            logger.debug(f"Response status: {response.status_code}")
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create embeddings (HTTP {e.response.status_code}): {e}")
            logger.error(f"Request URL: {url}")
            logger.debug(f"Request headers: {self._sanitize_headers(headers)}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to {url}: {e}")
            logger.error(f"Connection error details: {type(e).__name__}: {str(e)}")
            logger.error(f"Base URL being used: {self.base_url}")
            raise
        except Exception as e:
            logger.error(f"Embeddings creation failed: {type(e).__name__}: {e}")
            logger.error(f"Request URL: {url}")
            raise

    async def close(self):
        """Close HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

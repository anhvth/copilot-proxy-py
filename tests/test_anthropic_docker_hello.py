"""Integration test for Anthropic proxy running in Docker on localhost:4343."""

import os

import httpx
import pytest

BASE_URL = os.environ.get("GLM_PROXY_URL", "http://localhost:4343")


def test_anthropic_docker_hello():
    payload = {
        "model": "glm-4.5-air",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{BASE_URL}/anthropic/v1/messages",
            json=payload,
            headers={
                "content-type": "application/json",
                "x-api-key": "test",
                "anthropic-version": "2023-06-01",
            },
        )

    if response.status_code == 401:
        pytest.fail(
            "Received 401 from upstream. Check Z_AI_API_KEY in copilot-proxy-py/.env "
            "and recreate glm-proxy container."
        )

    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}. Body: {response.text[:500]}"
    )

    data = response.json()
    print(f"Status: {response.status_code}")
    print(f"Response JSON: {data}")
    text_chunks = [
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if text_chunks:
        print(f"Response text: {''.join(text_chunks)}")
    assert isinstance(data, dict)
    assert data.get("type") == "message"
    assert isinstance(data.get("content"), list)
    assert len(data["content"]) > 0

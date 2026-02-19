#!/usr/bin/env python3
"""Tests for Anthropic cache_control normalization in Copilot proxy."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from proxy_runners.copilot import CopilotProxy


def test_normalize_ephemeral_scope_shape_to_type() -> None:
    payload = {
        "model": "claude-haiku-4.5",
        "system": [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
            {
                "type": "text",
                "text": "c",
                "cache_control": {"ephemeral": {"scope": "conversation"}},
            },
        ],
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        "stream": True,
    }

    normalized = CopilotProxy._normalize_cache_controls(payload)

    assert normalized["system"][2]["cache_control"] == {"type": "ephemeral"}


def test_strip_unknown_cache_control_shape() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "hello",
                        "cache_control": {"scope": "request"},
                    }
                ],
            }
        ]
    }

    normalized = CopilotProxy._normalize_cache_controls(payload)

    assert "cache_control" not in normalized["messages"][0]["content"][0]


def test_keep_supported_type_and_drop_extra_keys() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "hello",
                        "cache_control": {"type": "ephemeral", "scope": "request"},
                    }
                ],
            }
        ]
    }

    normalized = CopilotProxy._normalize_cache_controls(payload)

    assert normalized["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}

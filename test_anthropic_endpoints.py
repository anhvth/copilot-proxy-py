#!/usr/bin/env python3
"""Test script for gh-copilot/anthropic and zai/anthropic endpoints."""
import json
import sys

import httpx

BASE = "http://127.0.0.1:4343"

ANTHROPIC_HELLO = {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 64,
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
}

HEADERS = {
    "Content-Type": "application/json",
    "anthropic-version": "2023-06-01",
    "x-api-key": "gh-local",
}


def test_endpoint(name: str, url: str) -> bool:
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL:     {url}")
    print(f"{'='*60}")
    try:
        with httpx.Client(timeout=60.0) as c:
            resp = c.post(url, json=ANTHROPIC_HELLO, headers=HEADERS)
        print(f"Status:  {resp.status_code}")
        try:
            body = resp.json()
            print(f"Body:    {json.dumps(body, indent=2)[:1000]}")
        except Exception:
            print(f"Body:    {resp.text[:1000]}")
        ok = 200 <= resp.status_code < 300
        print(f"Result:  {'PASS' if ok else 'FAIL'}")
        return ok
    except Exception as e:
        print(f"Error:   {type(e).__name__}: {e}")
        print("Result:  FAIL")
        return False


def main():
    # First check health
    print("Checking proxy health...")
    try:
        resp = httpx.get(f"{BASE}/health", timeout=5.0)
        print(f"Health: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Proxy not running: {e}")
        sys.exit(1)

    results = {}
    results["gh-copilot/anthropic"] = test_endpoint(
        "GitHub Copilot Anthropic",
        f"{BASE}/gh-copilot/anthropic/v1/messages",
    )
    results["zai/anthropic"] = test_endpoint(
        "Z.AI Anthropic",
        f"{BASE}/zai/anthropic/v1/messages",
    )

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()

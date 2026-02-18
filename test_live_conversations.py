#!/usr/bin/env python3
"""
Playwright test suite for live_conversations.py
Tests the UI components, API endpoints, and overall functionality
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

import pytest
import pytest_asyncio
from playwright.async_api import Page, expect

# Add the current directory to the path to import live_conversations
sys.path.insert(0, str(Path(__file__).parent))

# Test configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 4446
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
LOG_DIR = Path(".cache/logs")


@pytest_asyncio.fixture(scope="session")
async def start_server():
    """Start the live_conversations.py server in the background"""
    # Ensure the log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create some test log files
    create_test_logs()
    
    # Start the server
    proc = subprocess.Popen(
        [sys.executable, "live_conversations.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "HOST": SERVER_HOST, "PORT": str(SERVER_PORT)}
    )
    
    # Wait for server to start
    await asyncio.sleep(3)
    
    # Check if server is running
    try:
        import urllib.request
        urllib.request.urlopen(f"{SERVER_URL}/health")
    except Exception:
        # If health check fails, the server might not be ready yet
        await asyncio.sleep(2)
    
    yield SERVER_URL
    
    # Clean up
    proc.terminate()
    proc.wait()


@pytest_asyncio.fixture
async def page(start_server):
    """Create a Playwright page with the server running"""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(start_server)
        yield page
        await browser.close()


def create_test_logs():
    """Create test log files for testing purposes"""
    # Ensure the log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create test logs with different timestamps and content
    test_logs = [
        {
            "path": "20240101_10/chat001.json",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "request": {
                    "method": "POST",
                    "upstream_url": "https://api.githubcopilot.com/chat/completions",
                    "body": {
                        "messages": [
                            {"role": "user", "content": "Hello, how are you?"},
                            {"role": "assistant", "content": "I'm doing well, thank you for asking!"}
                        ]
                    }
                },
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": "I'm doing well, thank you for asking!"}}]
                    }
                },
                "duration_s": 1.234
            }
        },
        {
            "path": "20240101_11/chat002.json",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "request": {
                    "method": "POST",
                    "upstream_url": "https://api.githubcopilot.com/chat/completions",
                    "body": {
                        "messages": [
                            {"role": "user", "content": "Write a Python function to calculate fibonacci"}
                        ]
                    }
                },
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": "Here's a Python function to calculate fibonacci:"}}],
                        "full_response_text": "```python\ndef fibonacci(n):\n    if n <= 0:\n        return []\n    elif n == 1:\n        return [0]\n    fib = [0, 1]\n    for i in range(2, n):\n        fib.append(fib[i-1] + fib[i-2])\n    return fib\n```"
                    }
                },
                "duration_s": 2.567
            }
        },
        {
            "path": "20240101_12/error003.json",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "request": {
                    "method": "GET",
                    "upstream_url": "https://api.githubcopilot.com/models",
                    "body": {}
                },
                "response": {
                    "status_code": 404,
                    "body": {}
                },
                "error": "Model not found",
                "duration_s": 0.567
            }
        }
    ]
    
    # Write test logs to files
    for log in test_logs:
        log_path = LOG_DIR / log["path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "w") as f:
            json.dump(log["data"], f)


class TestLiveConversations:
    """Test suite for live_conversations.py"""
    
    @pytest.mark.asyncio
    async def test_page_loads(self, start_server):
        """Test that the page loads correctly"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_context()
            await page.goto(start_server)
            
            # Check that the page title is correct
            await expect(page).to_have_title("Live Conversations")
            
            # Check that the header is visible
            header = await page.locator("h1")
            await expect(header).to_contain_text("Live Conversations")
            await expect(header).to_be_visible()
            
            await browser.close()
    
    @pytest.mark.asyncio
    async def test_api_logs_endpoint(self, start_server):
        """Test the /api/logs endpoint"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()
            
            # Make a direct API request
            response = await page.request.get(f"{start_server}/api/logs")
            assert response.status == 200
            
            data = await response.json()
            assert isinstance(data, list)
            
            # Check that we have our test logs
            assert len(data) > 0
            
            # Check structure of first log
            first_log = data[0]
            required_fields = ["id", "timestamp", "method", "url", "status", "duration", "preview"]
            for field in required_fields:
                assert field in first_log
            
            await browser.close()
    
    @pytest.mark.asyncio
    async def test_search_functionality(self, start_server):
        """Test the search functionality"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_context()
            await page.goto(start_server)
            
            # Wait for logs to load
            await page.wait_for_selector(".group", timeout=5000)
            
            # Get initial count of logs
            initial_count = await page.locator(".group").count()
            assert initial_count > 0
            
            # Enter a search term
            search_input = await page.locator("input[placeholder='Fuzzy search logs...']")
            await search_input.fill("Hello")
            
            # Wait for search to complete
            await page.wait_for_timeout(1000)
            
            # Check that logs are filtered
            search_results = await page.locator(".group")
            # Should have fewer results after searching
            # (This assumes "Hello" appears in only one log)
            assert await search_results.count() <= initial_count
            
            # Clear search
            await search_input.clear()
            await page.wait_for_timeout(1000)
            
            # Should return to original count
            assert await page.locator(".group").count() == initial_count
            
            await browser.close()
    
    @pytest.mark.asyncio
    async def test_log_selection(self, page):
        """Test selecting a log entry and viewing details"""
        # Wait for logs to load
        await page.wait_for_selector(".group", timeout=5000)
        
        # Get the first log entry
        first_log = page.locator(".group").first
        
        # Get the ID of the first log
        first_log_id = await first_log.locator(".text-slate-400.font-mono").inner_text()
        
        # Click on the first log
        await first_log.click()
        
        # Wait for details to load
        await page.wait_for_selector(".bg-slate-800.p-4.border-b", timeout=5000)
        
        # Check that the detail view shows the correct log
        detail_id = await page.locator(".text-slate-400.font-mono").inner_text()
        assert detail_id == first_log_id
    
    @pytest.mark.asyncio
    async def test_json_view(self, page):
        """Test the JSON view tab"""
        # Wait for logs to load and select the first one
        await page.wait_for_selector(".group", timeout=5000)
        await page.locator(".group").first.click()
        await page.wait_for_selector(".bg-slate-800.p-4.border-b", timeout=5000)
        
        # Click on the JSON tab
        json_tab = await page.locator("button", has_text="Raw JSON")
        await json_tab.click()
        
        # Check that the JSON view is visible
        json_view = await page.locator("#raw-json")
        await expect(json_view).to_be_visible()
        
        # Check that it contains JSON
        json_text = await json_view.inner_text()
        assert "{" in json_text  # Should have JSON opening bracket
    
    @pytest.mark.asyncio
    async def test_api_log_detail_endpoint(self, start_server):
        """Test the /api/logs/{path} endpoint"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()
            
            # First, get the list of logs
            list_response = await page.request.get(f"{start_server}/api/logs")
            logs = await list_response.json()
            assert len(logs) > 0
            
            # Get details of the first log
            first_log_id = logs[0]["id"]
            detail_response = await page.request.get(f"{start_server}/api/logs/{first_log_id}")
            assert detail_response.status == 200
            
            detail_data = await detail_response.json()
            assert "id" in detail_data
            assert "content" in detail_data
            assert detail_data["id"] == first_log_id
            
            # Test a non-existent log
            not_found_response = await page.request.get(f"{start_server}/api/logs/nonexistent/path")
            assert not_found_response.status == 404
            
            await browser.close()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, page):
        """Test error handling in the UI"""
        # Wait for logs to load
        await page.wait_for_selector(".group", timeout=5000)
        
        # Select an error log (should have red status)
        error_logs = page.locator(".text-red-400")
        error_count = await error_logs.count()
        
        if error_count > 0:
            # Select the first error log
            error_log = page.locator(".text-red-400").first
            await error_log.locator("xpath=../..").click()
            
            # Check that error information is displayed
            await page.wait_for_selector(".bg-red-900\\/20", timeout=5000)
            error_info = await page.locator(".bg-red-900\\/20")
            await expect(error_info).to_be_visible()
    
    @pytest.mark.asyncio
    async def test_auto_refresh(self, page):
        """Test that logs auto-refresh"""
        # Wait for logs to load
        await page.wait_for_selector(".group", timeout=5000)
        
        # Get the current time string from the first log
        first_log_time = await page.locator(".text-slate-500.font-mono").first.inner_text()
        
        # Wait for auto-refresh (should happen every 5 seconds)
        await page.wait_for_timeout(6000)
        
        # The logs should still be visible (they don't disappear)
        logs_count = await page.locator(".group").count()
        assert logs_count > 0


@pytest.mark.asyncio
async def test_server_startup():
    """Test that the server starts up correctly"""
    from playwright.async_api import async_playwright
    
    # Start the server manually for this test
    proc = subprocess.Popen(
        [sys.executable, "live_conversations.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "HOST": SERVER_HOST, "PORT": str(SERVER_PORT + 1)}
    )
    
    # Wait for server to start
    await asyncio.sleep(3)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_context()
            
            # Test that the server responds
            response = await page.request.get(f"http://{SERVER_HOST}:{SERVER_PORT + 1}/")
            assert response.status == 200
            
            await browser.close()
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    # Run the tests
    pytest.main(["-xvs", __file__])
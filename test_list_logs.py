#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '/app')

# Import the function from live_conversations
import glob
import json
import os
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(".cache/logs")

async def test_list_logs():
    """Test the list_logs logic"""
    files = []
    pattern = str(LOG_DIR / "**" / "*.json")
    all_files = glob.glob(pattern, recursive=True)
    
    print(f"Pattern: {pattern}")
    print(f"Found {len(all_files)} files")
    print(f"LOG_DIR exists: {LOG_DIR.exists()}")
    print(f"LOG_DIR path: {LOG_DIR.absolute()}")
    
    # Sort by modification time, newest first
    all_files.sort(key=os.path.getmtime, reverse=True)
    
    results = []
    count = 0
    limit = 5
    
    for f in all_files:
        if count >= limit:
            break
            
        try:
            path = Path(f)
            rel_path = path.relative_to(LOG_DIR)
            
            with open(f, "r", encoding="utf-8") as file:
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    print(f"JSON decode error for {f}")
                    continue
                
                result = {
                    "id": str(rel_path),
                    "timestamp": data.get("timestamp", datetime.fromtimestamp(os.path.getmtime(f)).isoformat()),
                    "method": data.get("request", {}).get("method", "???"),
                    "url": data.get("request", {}).get("upstream_url", "unknown"),
                    "status": data.get("response", {}).get("status_code", 0),
                    "duration": data.get("duration_s", 0.0),
                    "preview": str(data.get("request", {}).get("body", ""))[:100]
                }
                results.append(result)
                count += 1
                print(f"✓ Processed: {rel_path}")
        except Exception as e:
            print(f"Error reading {f}: {e}")
            continue
    
    print(f"\nTotal results: {len(results)}")
    print(json.dumps(results, indent=2))

asyncio.run(test_list_logs())

# Live Conversations Debugging Guide

This document serves as a comprehensive guide for understanding and fixing issues with the `live_conversations.py` file.

## Overview

`live_conversations.py` provides a web interface for visualizing proxy logs. It has two main components:
1. A FastAPI backend that serves JSON log data
2. A Vue.js frontend that displays the logs in a user-friendly interface

## Architecture

### Backend Components

- **FastAPI Server**: Serves the web interface and API endpoints
- **API Routes**:
  - `/api/logs`: Lists log files with metadata
  - `/api/logs/{path:path}`: Gets detailed content of a specific log
- **Data Models**:
  - `LogSummary`: Summary information for log listings
  - `LogDetail`: Full content of a log file

### Frontend Components

The frontend is a Vue.js application with the following key features:
- **Log List**: Displays recent logs in a sidebar
- **Detail View**: Shows detailed content of selected logs
- **Tabbed Interface**: Switch between "Chat View" and "Raw JSON" views
- **Search**: Fuzzy search across log files and content
- **Auto-refresh**: Automatically updates log list every 5 seconds

## Common Issues and Solutions

### 1. Log Loading Issues

**Symptoms**: Log list is empty or shows "No logs found"

**Possible Causes**:
- Log directory doesn't exist
- Log files have incorrect permissions
- Log files have invalid JSON format
- Log directory path is incorrect

**Debugging Steps**:
1. Check if the log directory exists:
   ```
   ls -la .cache/logs
   ```
2. Verify log file permissions:
   ```
   ls -la .cache/logs/*
   ```
3. Check if log files contain valid JSON:
   ```
   python -c "import json; print(json.load(open('.cache/logs/your-log.json')))"
   ```

**Solutions**:
- Create the log directory if it doesn't exist:
  ```python
  Path(".cache/logs").mkdir(parents=True, exist_ok=True)
  ```
- Fix file permissions:
  ```
  chmod 644 .cache/logs/*.json
  ```
- Repair or delete invalid JSON files

### 2. CORS Issues

**Symptoms**: Errors in browser console about CORS policy, or blank frontend

**Possible Causes**:
- CORS middleware misconfigured
- Different ports/origins between frontend and API

**Solutions**:
- Ensure CORS middleware is properly configured in `live_conversations.py`:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],  # Or specific origins for production
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

### 3. UI Rendering Issues

**Symptoms**: UI elements not displaying correctly, Vue.js errors in console

**Possible Causes**:
- Missing or incorrect Vue.js code
- HTML template issues
- CSS conflicts

**Debugging Steps**:
1. Check browser console for JavaScript errors
2. Inspect HTML structure with browser developer tools
3. Test with a minimal HTML template

### 4. Search Functionality Issues

**Symptoms**: Search doesn't filter logs or throws errors

**Possible Causes**:
- Search implementation bug
- Issues with string comparison
- Encoding problems

**Solutions**:
- Review `list_logs` function in `live_conversations.py`
- Check how search queries are processed:
  ```python
  if search:
      search_lower = search.lower()
      haystack = f"{rel_path} {data.get('request', {}).get('upstream_url', '')} {json.dumps(data)}"
      if search_lower not in haystack.lower():
          continue
  ```

### 5. JSON View Issues

**Symptoms**: JSON view tab doesn't show content or displays incorrectly

**Possible Causes**:
- Prism.js not loaded correctly
- JSON formatting issues
- DOM manipulation problems

**Solutions**:
- Ensure Prism.js libraries are loaded:
  ```html
  <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-tomorrow.min.css" rel="stylesheet" />
  <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js"></script>
  ```
- Check JSON highlighting code in the Vue.js app

### 6. Performance Issues

**Symptoms**: Slow page loading, UI lags

**Possible Causes**:
- Too many log files processed at once
- Inefficient DOM updates
- Blocking operations

**Solutions**:
- Implement pagination or virtual scrolling for log lists
- Optimize JSON parsing
- Use debouncing for search operations

## Testing

### Running Tests

Use the Playwright test suite to verify functionality:

```bash
# Install dependencies
pip install pytest pytest-asyncio playwright

# Install Playwright browsers
playwright install

# Run tests
pytest test_live_conversations.py -v
```

### Test Coverage

The test suite covers:
- Page loading and basic rendering
- API endpoint functionality
- Search functionality
- Log selection and detail viewing
- JSON view rendering
- Error handling
- Auto-refresh behavior

## Debugging Tools

### 1. Browser Developer Tools

Use browser developer tools to:
- Check console for JavaScript errors
- Inspect network requests
- Debug Vue.js components
- Examine CSS styling

### 2. Python Logging

Add detailed logging to identify issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or use the existing loguru configuration:

```python
from loguru import logger
logger.debug("Debug message")
```

### 3. Manual API Testing

Test API endpoints directly:

```bash
# Get log list
curl http://localhost:4446/api/logs

# Get specific log
curl http://localhost:4446/api/logs/20240101_10/chat001.json
```

## Code Structure

### Backend Structure

```python
# Main imports and configuration

# Data models
class LogSummary(BaseModel):
    # Fields: id, timestamp, method, url, status, duration, preview

class LogDetail(BaseModel):
    # Fields: id, content

# API routes
@app.get("/api/logs", response_model=List[LogSummary])
async def list_logs(limit: int = 100, search: Optional[str] = None):
    # Implementation

@app.get("/api/logs/{path:path}", response_model=LogDetail)
async def get_log(path: str):
    # Implementation

# Frontend HTML template with Vue.js
```

### Frontend Structure

The Vue.js application includes:
- Data: `logs`, `selectedLog`, `selectedDetail`, `searchQuery`, etc.
- Methods: `fetchLogs()`, `selectLog()`, `debouncedSearch()`, helpers
- Lifecycle hooks: `onMounted()` for initial fetch and auto-refresh

## Fixes to Apply

Based on common issues, here are recommended fixes:

### 1. Improve Error Handling

Add better error handling in API routes:

```python
@app.get("/api/logs/{path:path}", response_model=LogDetail)
async def get_log(path: str):
    """Get full details of a specific log file."""
    full_path = LOG_DIR / path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Log not found")
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return LogDetail(id=path, content=data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in log file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 2. Add Loading States

Improve user experience with better loading indicators:

```javascript
const selectLog = async (log) => {
    selectedLog.value = log;
    loading.value = true;
    try {
        // Existing code
    } catch (e) {
        console.error(e);
        selectedDetail.value = null;  // Clear details on error
    } finally {
        loading.value = false;
    }
};
```

### 3. Improve Search Functionality

Make search more robust:

```python
@app.get("/api/logs", response_model=List[LogSummary])
async def list_logs(limit: int = 100, search: Optional[str] = None):
    """List recent logs, optionally filtered."""
    files = []
    pattern = str(LOG_DIR / "**" / "*.json")
    all_files = glob.glob(pattern, recursive=True)
    
    # Sort by modification time, newest first
    all_files.sort(key=os.path.getmtime, reverse=True)
    
    results = []
    count = 0
    
    for f in all_files:
        if count >= limit and not search:
            break
            
        try:
            path = Path(f)
            rel_path = path.relative_to(LOG_DIR)
            
            with open(f, "r", encoding="utf-8") as file:
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {f}")
                    continue
                
                # Better search implementation
                if search:
                    search_lower = search.lower()
                    haystack = f"{rel_path} {data.get('request', {}).get('upstream_url', '')} {json.dumps(data)}"
                    if search_lower not in haystack.lower():
                        continue

                # Better error handling for missing fields
                request_data = data.get("request", {})
                response_data = data.get("response", {})
                
                results.append(LogSummary(
                    id=str(rel_path),
                    timestamp=data.get("timestamp", datetime.fromtimestamp(os.path.getmtime(f)).isoformat()),
                    method=request_data.get("method", "???"),
                    url=request_data.get("upstream_url", "unknown"),
                    status=response_data.get("status_code", 0),
                    duration=data.get("duration_s", 0.0),
                    preview=str(request_data.get("body", ""))[:100]
                ))
                count += 1
        except Exception as e:
            logger.error(f"Error reading {f}: {e}")
            continue
            
    return results
```

### 4. Fix JSON View

Ensure JSON view works correctly:

```javascript
// After selecting a log
setTimeout(() => {
    const el = document.getElementById('raw-json');
    if (el && selectedDetail.value) {
        el.textContent = JSON.stringify(selectedDetail.value.content, null, 2);
        if (window.Prism) {
            Prism.highlightElement(el);
        }
    }
}, 50);
```

### 5. Better Error Display

Improve error display in the frontend:

```javascript
// In extractResponse
const extractResponse = (response) => {
    if (!response) return '<span class="text-slate-500 italic">No response body</span>';
    
    // Handle wrapped body if present
    const data = response.body || response;
    
    // Check for errors
    if (response.error || data.error) {
        return `<div class="bg-red-900/20 border border-red-900/50 p-3 rounded">
                    <strong>Error:</strong> ${response.error || data.error || 'Unknown error'}
                </div>`;
    }
    
    // Rest of the function...
};
```

## Checklist for Subagents

Before submitting fixes, ensure:

1. [ ] All test cases in `test_live_conversations.py` pass
2. [ ] No JavaScript errors in browser console
3. [ ] All API endpoints work correctly
4. [ ] Search functionality works as expected
5. [ ] Log selection and detail viewing work
6. [ ] Both Chat and JSON views display correctly
7. [ ] Error handling is robust
8. [ ] Performance is acceptable (no excessive delays)
9. [ ] Code follows Python and Vue.js best practices
10. [ ] Documentation is updated if needed

## Dependencies

The project depends on the following Python packages:
- fastapi
- uvicorn
- pydantic
- loguru

The frontend depends on:
- Vue.js
- Tailwind CSS
- Prism.js
- Marked

Ensure all dependencies are properly installed and configured.
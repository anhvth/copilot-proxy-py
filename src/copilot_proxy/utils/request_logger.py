"""Request/response logging to cache files."""

import json
import portalocker
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import Request, Response
from loguru import logger


class RequestLogger:
    """Logs requests and responses to cache files.

    Structure:
        .cache/logs/
        ├── yymmdd_HH/           # folder per hour
        │   ├── counter.txt      # tracks next sequence number (thread-safe)
        │   ├── 1.json          # request 1
        │   ├── 2.json          # request 2
        │   └── ...
    """

    def __init__(self, cache_dir: Path):
        """Initialize request logger.

        Args:
            cache_dir: Directory to store cache files
        """
        self.logs_dir = cache_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_hour_folder(self) -> Path:
        """Get current hour folder path.

        Returns:
            Path to the current hour folder
        """
        now = datetime.now()
        date_str = now.strftime("%y%m%d_%H")
        folder = self.logs_dir / date_str
        folder.mkdir(exist_ok=True)
        return folder

    def _get_next_sequence(self, folder: Path) -> int:
        """Get next sequence number using file locking.

        Args:
            folder: The hour folder path

        Returns:
            Next sequence number
        """
        counter_file = folder / "counter.txt"

        # Create counter file if it doesn't exist
        if not counter_file.exists():
            counter_file.write_text("0\n")

        # Use portalocker for cross-platform file locking
        try:
            with open(counter_file, "r+") as f:
                # Acquire exclusive lock (blocks until lock is acquired)
                portalocker.lock(f, portalocker.LOCK_EX)

                # Read current counter value
                f.seek(0)
                content = f.read().strip()
                current = int(content) if content else 0

                # Increment
                next_seq = current + 1

                # Write back
                f.seek(0)
                f.write(str(next_seq) + "\n")
                f.truncate()

                # Lock is automatically released when we exit the with block
                return next_seq
        except Exception as e:
            logger.error(f"Failed to get next sequence: {e}")
            # Fallback: count existing files
            fallback = len(list(folder.glob("*.json"))) + 1
            logger.warning(f"Using fallback sequence number: {fallback}")
            return fallback

    async def log_pair(
        self,
        request: Request,
        response: Response,
        request_body: Dict[str, Any],
        response_body: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        """Log a request/response pair.

        Creates a separate JSON file for each request in an hour folder.

        Args:
            request: FastAPI request object
            response: FastAPI response object
            request_body: Parsed request body as dict
            response_body: Parsed response body as dict
            error: Error message if request failed
        """
        try:
            # Get hour folder and next sequence number
            folder = self._get_hour_folder()
            seq = self._get_next_sequence(folder)

            # Create log file path
            log_file = folder / f"{seq}.json"

            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "sequence": seq,
                "request": {
                    "method": request.method,
                    "url": str(request.url),
                    "path": request.url.path,
                    "query_params": dict(request.query_params),
                    "headers": dict(request.headers),
                    "body": request_body,
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                },
            }

            if error:
                log_entry["error"] = error

            # Write entire log entry as JSON (not JSONL)
            with open(log_file, "w") as f:
                json.dump(log_entry, f, ensure_ascii=False, indent=2)

            logger.debug(
                f"Logged request/response to {log_file.name}: {request.method} {request.url.path}"
            )

        except Exception as e:
            logger.error(f"Failed to log request/response: {e}")

    def read_log_file(self, log_file: Path) -> Optional[Dict[str, Any]]:
        """Read and parse a log file.

        Args:
            log_file: Path to the log file

        Returns:
            Log entry dict, or None if failed
        """
        try:
            with open(log_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read log file {log_file}: {e}")
            return None
    def list_log_files(self, hour_folder: Optional[str] = None) -> List[Path]:
        """List all log files in the cache directory.

        Args:
            hour_folder: Optional specific hour folder (e.g., "250217_14")

        Returns:
            List of log file paths
        """
        try:
            if hour_folder:
                folder = self.logs_dir / hour_folder
                if folder.exists():
                    return sorted(folder.glob("*.json"))
            else:
                # List all JSON files from all hour folders
                all_files = []
                for folder in sorted(self.logs_dir.iterdir()):
                    if folder.is_dir():
                        all_files.extend(sorted(folder.glob("*.json")))
                return all_files
            return []
        except Exception as e:
            logger.error(f"Failed to list log files: {e}")
            return []

    def get_log_file(self, date_str: str = None, seq: int = 1) -> Optional[Path]:
        """Get a specific log file path.

        Args:
            date_str: Date string in format "yymmdd_HH". If None, uses current date/hour.
            seq: Sequence number of the log file

        Returns:
            Path to the log file, or None if not found
        """
        if date_str is None:
            now = datetime.now()
            date_str = now.strftime("%y%m%d_%H")

        folder = self.logs_dir / date_str
        log_file = folder / f"{seq}.json"
        return log_file if log_file.exists() else None

    def list_hour_folders(self) -> List[Path]:
        """List all hour folders.

        Returns:
            List of folder paths sorted by name
        """
        try:
            return sorted([f for f in self.logs_dir.iterdir() if f.is_dir()])
        except Exception as e:
            logger.error(f"Failed to list hour folders: {e}")
            return []


# Global instance
_request_logger: Optional[RequestLogger] = None


def get_request_logger(cache_dir: Optional[Path] = None) -> RequestLogger:
    """Get or create the global request logger instance.

    Args:
        cache_dir: Optional cache directory path (uses settings default if not provided)

    Returns:
        RequestLogger instance
    """
    global _request_logger
    if _request_logger is None:
        if cache_dir is None:
            from ..config import settings
            cache_dir = settings.cache_dir
        _request_logger = RequestLogger(cache_dir)
    return _request_logger


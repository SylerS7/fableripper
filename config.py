import os
import tempfile
from pathlib import Path

# Detect Vercel / serverless environment
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

BASE_DIR = Path(__file__).resolve().parent

if IS_VERCEL:
    TEMP_ROOT = Path(tempfile.gettempdir()) / "novel_to_epub"
    OUTPUT_DIR = TEMP_ROOT / "output"
    CACHE_DIR = TEMP_ROOT / "cache"
else:
    OUTPUT_DIR = BASE_DIR / "output"
    CACHE_DIR = BASE_DIR / ".cache"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Network settings
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 1.0
DEFAULT_CONCURRENCY = 8

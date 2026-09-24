import sys
from pathlib import Path

# Ensure root directory is in sys.path for Vercel serverless execution
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from web_app import app

# Vercel serverless function entrypoint
# The WSGI app must be exposed as `app`

#!/usr/bin/env python3
"""
Dev server for Tracks viewer - serves static files from viewer/ directory
on the port specified in .env.dev (default: 4020)
"""

import os
import sys
import http.server
import socketserver
from pathlib import Path

def load_env_file(path):
    """Load environment variables from a simple .env file"""
    env_vars = {}
    if not path.exists():
        return env_vars
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars

# Load environment from .env.dev
env_file = Path(__file__).parent / ".env.dev"
env_vars = load_env_file(env_file)

# Get configuration
port = int(env_vars.get("PORT", os.getenv("PORT", "4020")))
hostname = os.getenv("HOSTNAME", "tracks.local")
viewer_dir = Path(__file__).parent / "viewer"

# Change to viewer directory
os.chdir(viewer_dir)

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default log messages
        pass

# Create server
handler = QuietHTTPRequestHandler
with socketserver.TCPServer(("", port), handler) as httpd:
    print(f"http://{hostname}  (localhost:{port})")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", file=sys.stderr)
        sys.exit(0)

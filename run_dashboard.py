#!/usr/bin/env python3
"""
Entry point for the Agentic Team Dashboard.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.dashboard.app import app

if __name__ == "__main__":
    from src.config import config

    print(f"Starting dashboard on {config.FLASK_HOST}:{config.FLASK_PORT}")
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        threaded=True,
    )

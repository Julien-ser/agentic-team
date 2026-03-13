#!/usr/bin/env python3
"""
Agentic Team Worker Manager - Main entry point

This script starts and manages the three specialized agents:
- Security Agent
- Software Development Agent
- Frontend Agent

It provides:
- Automatic agent lifecycle management
- Health monitoring with auto-restart
- graceful shutdown
- Status reporting
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from orchestrator.worker_manager import WorkerManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("worker_manager.log"),
    ],
)

logger = logging.getLogger(__name__)


class WorkerManagerRunner:
    """Runs the worker manager with signal handling."""

    def __init__(self):
        self.worker_manager: Optional[WorkerManager] = None
        self._shutdown = False

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown = True

    async def run(self):
        """Main run loop."""
        logger.info("=" * 60)
        logger.info("Agentic Team Worker Manager")
        logger.info("=" * 60)

        try:
            # Create worker manager
            self.worker_manager = WorkerManager()

            # Run until shutdown
            await self.worker_manager.run_forever()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            return 1

        return 0


def main():
    """Main entry point."""
    runner = WorkerManagerRunner()

    try:
        # Run the async event loop
        exit_code = asyncio.run(runner.run())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(0)


if __name__ == "__main__":
    main()

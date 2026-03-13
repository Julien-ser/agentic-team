#!/usr/bin/env python3
"""
Simple test for WorkerManager - verifies basic instantiation and agent creation.

Run with: python -m orchestrator.test_worker
"""

import asyncio
import sys
from pathlib import Path

# Add project src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator.worker_manager import WorkerManager
from state.state_manager import StateManager


async def test_basic():
    """Test basic WorkerManager functionality."""
    print("=" * 60)
    print("Testing WorkerManager Basic Functionality")
    print("=" * 60)

    # Create a temporary database for testing
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print("\n1. Creating StateManager...")
        state_manager = StateManager(db_path=db_path)
        print("   ✓ StateManager created")

        print("\n2. Creating WorkerManager...")
        wm = WorkerManager(state_manager=state_manager)
        print("   ✓ WorkerManager created")

        print("\n3. Initializing agents...")
        await wm.initialize()
        print(f"   ✓ Created {len(wm._agents)} agents")

        print("\n4. Agent details:")
        for agent_id, agent in wm._agents.items():
            print(f"   - {agent.role.value}: {agent_id}")

        print("\n5. Getting status...")
        status = wm.get_status()
        print(f"   ✓ Total agents: {status['total_agents']}")
        print(f"   ✓ Metrics: {status['metrics']}")

        print("\n6. Testing get_health_status...")
        health = await wm.get_health_status()
        print(f"   ✓ Health status for {len(health)} agents")

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        print("\nNote: Full agent startup requires Redis connection.")
        print("To run the worker manager: python -m orchestrator.main")

    finally:
        # Cleanup
        try:
            Path(db_path).unlink(missing_ok=True)
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test_basic())

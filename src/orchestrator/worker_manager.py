"""
Worker Manager - Agent orchestration and health monitoring.

This module provides the WorkerManager class that coordinates the three
specialized agent workers (Security, SW_DEV, FRONTEND), manages their
lifecycle, monitors health, and provides status reporting.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional

from src.agents.security_agent import SecurityAgent
from src.agents.dev_agent import SoftwareDevAgent
from src.agents.frontend_agent import FrontendAgent
from src.agents.lifecycle import LifecycleManager
from src.state.state_manager import StateManager
from src.messaging.redis_broker import RedisMessageBroker
from src.config import config

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    Manages the agent worker pool with health monitoring.

    This class is responsible for:
    - Creating and configuring the three agent workers
    - Starting/stopping all workers
    - Monitoring agent health and automatic restart
    - Reporting status to the dashboard
    """

    def __init__(
        self,
        auto_restart: bool = True,
        max_restarts: int = 3,
        health_check_interval: int = 30,
        state_manager: Optional[StateManager] = None,
        broker: Optional[RedisMessageBroker] = None,
    ):
        """
        Initialize the WorkerManager.

        Args:
            auto_restart: Whether to automatically restart crashed agents
            max_restarts: Maximum restart attempts per agent
            health_check_interval: Seconds between health checks
            state_manager: Shared state manager instance (created if None)
            broker: Redis broker instance (created if None)
        """
        self.state_manager = state_manager or StateManager()
        self.broker = broker or RedisMessageBroker()

        # Create lifecycle manager
        self.lifecycle_manager = LifecycleManager(
            auto_restart=auto_restart,
            max_restarts=max_restarts,
            health_check_interval=health_check_interval,
        )

        # Will hold agent references
        self._agents: Dict[str, Any] = {}

        logger.info(
            f"WorkerManager initialized (auto_restart={auto_restart}, "
            f"max_restarts={max_restarts})"
        )

    async def initialize(self) -> None:
        """Initialize all agents and their dependencies."""
        logger.info("Initializing worker agents...")

        # Create agent instances
        agents_to_create = [
            (SecurityAgent, "security"),
            (SoftwareDevAgent, "dev"),
            (FrontendAgent, "frontend"),
        ]

        for agent_class, role_name in agents_to_create:
            try:
                agent = agent_class(
                    broker=self.broker,
                    state_manager=self.state_manager,
                )
                self._agents[agent.agent_id] = agent
                logger.info(f"Created {role_name} agent: {agent.agent_id}")
            except Exception as e:
                logger.error(f"Failed to create {role_name} agent: {e}")
                raise

        # Register all agents with lifecycle manager
        for agent in self._agents.values():
            self.lifecycle_manager.register_agent(agent)

        logger.info(f"WorkerManager initialized with {len(self._agents)} agents")

    async def start(self) -> None:
        """Start all agent workers."""
        logger.info("Starting all agent workers...")

        # Connect shared resources first
        try:
            await self.broker.connect()
            logger.info("Connected to Redis message broker")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Initialize agents if not already done
        if not self._agents:
            await self.initialize()

        # Start all agents via lifecycle manager
        results = await self.lifecycle_manager.start_all()

        # Log results
        successful = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"Started {successful}/{total} agents")

        if successful < total:
            failed = [aid for aid, success in results.items() if not success]
            logger.warning(f"Failed to start agents: {failed}")

    async def stop(self) -> None:
        """Stop all agent workers gracefully."""
        logger.info("Stopping all agent workers...")

        # Stop lifecycle manager (stops all agents)
        if self.lifecycle_manager:
            await self.lifecycle_manager.stop_all(graceful=True)

        # Disconnect broker
        try:
            await self.broker.disconnect()
            logger.info("Disconnected from Redis")
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")

        logger.info("All workers stopped")

    async def restart(self, agent_id: Optional[str] = None) -> Dict[str, bool]:
        """
        Restart agent(s).

        Args:
            agent_id: Specific agent ID to restart, or None for all

        Returns:
            Dictionary of agent_id to success status
        """
        if agent_id:
            return {agent_id: await self.lifecycle_manager.restart_agent(agent_id)}
        else:
            results = {}
            for aid in self._agents:
                results[aid] = await self.lifecycle_manager.restart_agent(aid)
            return results

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all agents.

        Returns:
            Dictionary with agent statuses and overall metrics
        """
        status = {
            "agents": {},
            "metrics": self.lifecycle_manager.get_metrics(),
            "total_agents": len(self._agents),
        }

        # Get individual agent statuses
        for agent_id, agent in self._agents.items():
            try:
                info = self.lifecycle_manager.get_agent_info(agent_id)
                if info:
                    status["agents"][agent_id] = {
                        "role": info.role.value,
                        "is_running": info.is_running,
                        "is_healthy": info.is_healthy,
                        "restart_count": info.restart_count,
                        "last_error": info.last_error,
                    }
            except Exception as e:
                logger.debug(f"Error getting status for {agent_id}: {e}")

        return status

    async def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed health status for all agents."""
        return await self.lifecycle_manager.get_health_status()

    async def run_forever(self) -> None:
        """Run the worker manager until interrupted."""
        logger.info("Starting worker manager (run_forever mode)...")

        try:
            await self.start()

            # Keep running until stopped
            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Worker manager cancelled")
            await self.stop()
        except KeyboardInterrupt:
            logger.info("Worker manager interrupted")
            await self.stop()
        except Exception as e:
            logger.error(f"Worker manager error: {e}")
            await self.stop()
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()

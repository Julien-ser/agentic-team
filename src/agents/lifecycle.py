"""
Agent lifecycle manager for starting, stopping, and monitoring multiple agents.

This module provides the LifecycleManager class that coordinates the operation
of multiple agents, handling startup, shutdown, health monitoring, and graceful
degradation when agents fail.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.base_agent import BaseAgent
from src.protocols.agent_specs import AgentRole

logger = logging.getLogger(__name__)


@dataclass
class AgentLifecycleInfo:
    """Information tracked for each managed agent."""

    agent: BaseAgent
    agent_id: str
    role: AgentRole
    start_time: Optional[datetime] = None
    is_running: bool = False
    is_healthy: bool = True
    restart_count: int = 0
    last_error: Optional[str] = None
    task: Optional[asyncio.Task] = None


class LifecycleManager:
    """
    Manages lifecycle operations for multiple agents.

    Features:
    - Start and stop agents gracefully
    - Automatic restart of crashed agents (configurable)
    - Health monitoring and reporting
    - Graceful shutdown of all agents
    - Agent state persistence tracking
    """

    def __init__(
        self,
        auto_restart: bool = True,
        max_restarts: int = 3,
        health_check_interval: int = 30,
    ):
        """
        Initialize lifecycle manager.

        Args:
            auto_restart: Whether to automatically restart crashed agents
            max_restarts: Maximum number of restart attempts per agent
            health_check_interval: Seconds between health checks
        """
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        self.health_check_interval = health_check_interval

        # Agent registry
        self._agents: Dict[str, AgentLifecycleInfo] = {}
        self._role_to_agents: Dict[AgentRole, List[str]] = {
            AgentRole.SECURITY: [],
            AgentRole.SW_DEV: [],
            AgentRole.FRONTEND: [],
        }

        # Manager state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        logger.info(
            f"LifecycleManager initialized (auto_restart={auto_restart}, "
            f"max_restarts={max_restarts})"
        )

    def register_agent(self, agent: BaseAgent) -> str:
        """
        Register an agent for lifecycle management.

        Args:
            agent: The agent instance to manage

        Returns:
            Agent ID
        """
        agent_id = agent.agent_id
        role = agent.role

        if agent_id in self._agents:
            logger.warning(f"Agent {agent_id} already registered, skipping")
            return agent_id

        info = AgentLifecycleInfo(
            agent=agent,
            agent_id=agent_id,
            role=role,
        )

        self._agents[agent_id] = info
        self._role_to_agents[role].append(agent_id)

        logger.info(
            f"Registered agent {agent_id} (role: {role.value}) with lifecycle manager"
        )

        return agent_id

    def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from lifecycle management.

        Args:
            agent_id: ID of agent to unregister

        Returns:
            True if agent was registered and removed, False otherwise
        """
        if agent_id not in self._agents:
            return False

        info = self._agents[agent_id]
        role = info.role

        # Remove from role mapping
        if agent_id in self._role_to_agents[role]:
            self._role_to_agents[role].remove(agent_id)

        # Stop agent if running
        if info.is_running:
            asyncio.create_task(self._stop_agent_internal(info))

        # Remove from registry
        del self._agents[agent_id]

        logger.info(f"Unregistered agent {agent_id}")
        return True

    async def start_agent(self, agent_id: str) -> bool:
        """
        Start a specific agent.

        Args:
            agent_id: ID of agent to start

        Returns:
            True if started successfully, False otherwise
        """
        async with self._lock:
            if agent_id not in self._agents:
                logger.error(f"Cannot start: Agent {agent_id} not found")
                return False

            info = self._agents[agent_id]

            if info.is_running:
                logger.warning(f"Agent {agent_id} is already running")
                return True

            try:
                logger.info(f"Starting agent {agent_id}")
                await info.agent.start()

                info.is_running = True
                info.start_time = datetime.utcnow()
                info.restart_count += 1
                info.last_error = None

                logger.info(f"Agent {agent_id} started successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to start agent {agent_id}: {e}")
                info.is_healthy = False
                info.last_error = str(e)
                return False

    async def stop_agent(self, agent_id: str, graceful: bool = True) -> bool:
        """
        Stop a specific agent.

        Args:
            agent_id: ID of agent to stop
            graceful: If True, wait for current task to complete

        Returns:
            True if stopped successfully, False otherwise
        """
        async with self._lock:
            if agent_id not in self._agents:
                logger.error(f"Cannot stop: Agent {agent_id} not found")
                return False

            info = self._agents[agent_id]

            if not info.is_running:
                logger.warning(f"Agent {agent_id} is not running")
                return True

            success = await self._stop_agent_internal(info, graceful=graceful)
            return success

    async def _stop_agent_internal(
        self, info: AgentLifecycleInfo, graceful: bool = True
    ) -> bool:
        """
        Internal method to stop an agent.

        Args:
            info: Agent lifecycle info
            graceful: Wait for current task to complete

        Returns:
            True if stopped successfully
        """
        try:
            logger.info(f"Stopping agent {info.agent_id} (graceful={graceful})")
            await info.agent.stop()

            info.is_running = False
            info.is_healthy = False

            logger.info(f"Agent {info.agent_id} stopped")
            return True

        except Exception as e:
            logger.error(f"Error stopping agent {info.agent_id}: {e}")
            return False

    async def restart_agent(self, agent_id: str) -> bool:
        """
        Restart a specific agent.

        Args:
            agent_id: ID of agent to restart

        Returns:
            True if restarted successfully, False otherwise
        """
        logger.info(f"Restarting agent {agent_id}")

        # Stop first (forceful to restart quickly)
        await self.stop_agent(agent_id, graceful=False)

        # Small delay
        await asyncio.sleep(1.0)

        # Start again
        success = await self.start_agent(agent_id)

        if success:
            logger.info(f"Agent {agent_id} restarted successfully")
        else:
            logger.error(f"Failed to restart agent {agent_id}")

        return success

    async def start_all(self) -> Dict[str, bool]:
        """
        Start all registered agents.

        Returns:
            Dictionary mapping agent_id to success status
        """
        logger.info("Starting all agents")
        results = {}

        # Start agents in parallel
        tasks = []
        for agent_id in self._agents:
            tasks.append(self._safe_start_agent(agent_id))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for agent_id, result in zip(self._agents.keys(), results_list):
            if isinstance(result, Exception):
                results[agent_id] = False
                logger.error(f"Error starting agent {agent_id}: {result}")
            else:
                results[agent_id] = result

        logger.info(f"Started {sum(results.values())}/{len(results)} agents")
        return results

    async def stop_all(self, graceful: bool = True) -> None:
        """
        Stop all registered agents.

        Args:
            graceful: Wait for current tasks to complete
        """
        logger.info(f"Stopping all agents (graceful={graceful})")

        # Stop all agents in parallel
        tasks = []
        for agent_id in self._agents:
            if self._agents[agent_id].is_running:
                tasks.append(self.stop_agent(agent_id, graceful=graceful))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("All agents stopped")

    async def reload_all(self) -> Dict[str, bool]:
        """
        Reload all registered agents (reconfiguration).

        Returns:
            Dictionary mapping agent_id to success status
        """
        logger.info("Reloading all agents")
        results = {}

        for agent_id, info in self._agents.items():
            try:
                await info.agent.reload()
                results[agent_id] = True
            except Exception as e:
                logger.error(f"Error reloading agent {agent_id}: {e}")
                results[agent_id] = False

        return results

    async def start_monitoring(self) -> None:
        """
        Start the health monitoring loop.

        This spawns a background task that periodically checks agent health
        and restarts crashed agents if auto_restart is enabled.
        """
        if self._running:
            logger.warning("Monitoring already running")
            return

        logger.info("Starting health monitoring loop")
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        """Stop the health monitoring loop."""
        if not self._running:
            return

        logger.info("Stopping health monitoring loop")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("Health monitoring stopped")

    def get_agent_ids_by_role(self, role: AgentRole) -> List[str]:
        """Get all agent IDs with a specific role."""
        return self._role_to_agents.get(role, [])

    def get_agent_info(self, agent_id: str) -> Optional[AgentLifecycleInfo]:
        """Get lifecycle info for a specific agent."""
        return self._agents.get(agent_id)

    def get_all_agent_info(self) -> Dict[str, AgentLifecycleInfo]:
        """Get lifecycle info for all agents."""
        return self._agents.copy()

    async def get_health_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health status for all managed agents.

        Returns:
            Dictionary mapping agent_id to health status dict
        """
        health_status = {}

        for agent_id, info in self._agents.items():
            try:
                health = await info.agent.health_check()
                health["is_running"] = info.is_running
                health["restart_count"] = info.restart_count
                health["last_error"] = info.last_error
                health_status[agent_id] = health
            except Exception as e:
                health_status[agent_id] = {
                    "agent_id": agent_id,
                    "role": info.role.value,
                    "healthy": False,
                    "error": str(e),
                    "is_running": info.is_running,
                    "restart_count": info.restart_count,
                }

        return health_status

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get aggregate metrics for all agents.

        Returns:
            Dictionary with summary statistics
        """
        total_tasks_processed = 0
        total_tasks_failed = 0
        total_messages_sent = 0
        total_messages_received = 0
        running_agents = 0
        healthy_agents = 0

        for info in self._agents.values():
            metrics = info.agent.get_metrics()
            total_tasks_processed += metrics["tasks_processed"]
            total_tasks_failed += metrics["tasks_failed"]
            total_messages_sent += metrics["messages_sent"]
            total_messages_received += metrics["messages_received"]

            if info.is_running:
                running_agents += 1
            if info.is_healthy:
                healthy_agents += 1

        return {
            "total_agents": len(self._agents),
            "running_agents": running_agents,
            "healthy_agents": healthy_agents,
            "total_tasks_processed": total_tasks_processed,
            "total_tasks_failed": total_tasks_failed,
            "total_messages_sent": total_messages_sent,
            "total_messages_received": total_messages_received,
            "agents_by_role": {
                role.value: len(agents) for role, agents in self._role_to_agents.items()
            },
        }

    # Internal methods

    async def _safe_start_agent(self, agent_id: str) -> bool:
        """
        Start agent with exception handling.

        Args:
            agent_id: Agent to start

        Returns:
            True if started successfully
        """
        try:
            return await self.start_agent(agent_id)
        except Exception as e:
            logger.error(f"Exception starting agent {agent_id}: {e}")
            return False

    async def _monitor_loop(self) -> None:
        """Background task that monitors agent health and restarts if needed."""
        logger.info("Agent monitoring loop started")

        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)

                if not self._running:
                    break

                # Check all agents
                for agent_id, info in list(self._agents.items()):
                    if not info.is_running:
                        continue

                    try:
                        health = await info.agent.health_check()

                        if not health.get("healthy", False):
                            logger.warning(f"Agent {agent_id} health check failed")
                            info.is_healthy = False

                            # Attempt restart if auto-restart enabled
                            if (
                                self.auto_restart
                                and info.restart_count < self.max_restarts
                            ):
                                logger.info(f"Attempting to restart agent {agent_id}")
                                restart_success = await self.restart_agent(agent_id)
                                if not restart_success:
                                    logger.error(
                                        f"Failed to restart agent {agent_id} "
                                        f"(attempt {info.restart_count}/{self.max_restarts})"
                                    )
                        else:
                            info.is_healthy = True
                            info.last_error = None

                    except Exception as e:
                        logger.error(f"Error checking health of agent {agent_id}: {e}")
                        info.is_healthy = False

            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")

    # Context manager support

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_all()
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with proper cleanup."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        await self.stop_all(graceful=True)

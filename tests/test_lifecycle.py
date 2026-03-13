"""
Unit tests for LifecycleManager.

Tests cover agent registration, start/stop operations, health monitoring,
auto-restart functionality, and metrics collection.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.base_agent import BaseAgent
from src.agents.lifecycle import LifecycleManager, AgentLifecycleInfo
from src.protocols.agent_specs import AgentRole, Task


# Concrete agent for testing
class MockAgent(BaseAgent):
    """Mock agent for lifecycle testing."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        healthy: bool = True,
        role: Optional[AgentRole] = None,
        **kwargs,
    ):
        # Determine role - use provided or default to SW_DEV
        if role is None:
            self._role = AgentRole.SW_DEV
        else:
            self._role = role
        # Ensure agent_id is a string if None
        if agent_id is None:
            agent_id = f"mock-{uuid.uuid4().hex[:8]}"
        super().__init__(agent_id=agent_id, **kwargs)
        self._healthy = healthy
        self._started = False
        self._stopped = False
        self._reloaded = False

    def get_role(self) -> AgentRole:
        return self._role

    async def process_task(self, task: Task) -> dict:
        return {"success": True}

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["healthy"] = self._healthy
        return base

    async def reload(self):
        self._reloaded = True


@pytest.fixture
def lifecycle_manager():
    """Create LifecycleManager instance."""
    return LifecycleManager(auto_restart=True, max_restarts=2)


@pytest.fixture
def agent_instances():
    """Create multiple agent instances."""
    return [
        MockAgent(agent_id="sec-1", role=AgentRole.SECURITY),
        MockAgent(agent_id="dev-1", role=AgentRole.SW_DEV),
        MockAgent(agent_id="frontend-1", role=AgentRole.FRONTEND),
    ]


class TestLifecycleManagerInitialization:
    """Test lifecycle manager initialization."""

    def test_init_defaults(self):
        """Test default initialization."""
        manager = LifecycleManager()
        assert manager.auto_restart is True
        assert manager.max_restarts == 3
        assert manager.health_check_interval == 30
        assert manager._running is False
        assert len(manager._agents) == 0

    def test_init_custom(self):
        """Test custom initialization."""
        manager = LifecycleManager(
            auto_restart=False, max_restarts=5, health_check_interval=60
        )
        assert manager.auto_restart is False
        assert manager.max_restarts == 5
        assert manager.health_check_interval == 60


class TestAgentRegistration:
    """Test agent registration."""

    def test_register_agent(self, lifecycle_manager, agent_instances):
        """Test registering agents."""
        for agent in agent_instances:
            agent_id = lifecycle_manager.register_agent(agent)
            assert agent_id == agent.agent_id

        assert len(lifecycle_manager._agents) == 3
        assert len(lifecycle_manager._role_to_agents[AgentRole.SECURITY]) == 1
        assert len(lifecycle_manager._role_to_agents[AgentRole.SW_DEV]) == 1
        assert len(lifecycle_manager._role_to_agents[AgentRole.FRONTEND]) == 1

    def test_register_duplicate_agent(self, lifecycle_manager, agent_instances):
        """Test registering duplicate agent."""
        agent = agent_instances[0]
        lifecycle_manager.register_agent(agent)
        lifecycle_manager.register_agent(agent)  # Duplicate

        assert len(lifecycle_manager._agents) == 1

    def test_unregister_agent(self, lifecycle_manager, agent_instances):
        """Test unregistering agent."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)

        # Stop first agent
        agent_instances[0]._running = True  # Simulate running
        lifecycle_manager.unregister_agent("sec-1")

        assert "sec-1" not in lifecycle_manager._agents
        assert len(lifecycle_manager._agents) == 2

    def test_unregister_nonexistent(self, lifecycle_manager):
        """Test unregistering non-existent agent."""
        result = lifecycle_manager.unregister_agent("nonexistent")
        assert result is False


class TestAgentStartStop:
    """Test agent start/stop operations."""

    @pytest.mark.asyncio
    async def test_start_agent(self, lifecycle_manager):
        """Test starting an agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        with patch.object(agent, "start", new_callable=AsyncMock) as mock_start:
            success = await lifecycle_manager.start_agent("test-agent")

        assert success is True
        mock_start.assert_called_once()
        info = lifecycle_manager.get_agent_info("test-agent")
        assert info.is_running is True
        assert info.start_time is not None

    @pytest.mark.asyncio
    async def test_start_agent_already_running(self, lifecycle_manager):
        """Test starting already running agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)
        info = lifecycle_manager.get_agent_info("test-agent")
        info.is_running = True

        success = await lifecycle_manager.start_agent("test-agent")
        assert success is True  # Still returns success

    @pytest.mark.asyncio
    async def test_start_agent_failure(self, lifecycle_manager):
        """Test agent start failure."""
        agent = MockAgent(agent_id="test-agent")

        async def failing_start():
            raise RuntimeError("Start failed")

        agent.start = failing_start
        lifecycle_manager.register_agent(agent)

        success = await lifecycle_manager.start_agent("test-agent")
        assert success is False

        info = lifecycle_manager.get_agent_info("test-agent")
        assert info.is_running is False
        assert info.is_healthy is False
        assert "Start failed" in (info.last_error or "")

    @pytest.mark.asyncio
    async def test_stop_agent(self, lifecycle_manager):
        """Test stopping an agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        # Mark as running
        info = lifecycle_manager.get_agent_info("test-agent")
        info.is_running = True

        with patch.object(agent, "stop", new_callable=AsyncMock) as mock_stop:
            success = await lifecycle_manager.stop_agent("test-agent")

        assert success is True
        mock_stop.assert_called_once()
        info = lifecycle_manager.get_agent_info("test-agent")
        assert info.is_running is False

    @pytest.mark.asyncio
    async def test_stop_agent_not_running(self, lifecycle_manager):
        """Test stopping non-running agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        success = await lifecycle_manager.stop_agent("test-agent")
        assert success is True

    @pytest.mark.asyncio
    async def test_restart_agent(self, lifecycle_manager):
        """Test restarting an agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        with (
            patch.object(agent, "start", new_callable=AsyncMock) as mock_start,
            patch.object(agent, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            success = await lifecycle_manager.restart_agent("test-agent")

        assert success is True
        mock_stop.assert_called_once()
        mock_start.assert_called_once()

        info = lifecycle_manager.get_agent_info("test-agent")
        assert info.restart_count == 1


class TestBatchOperations:
    """Test batch operations on agents."""

    @pytest.mark.asyncio
    async def test_start_all(self, lifecycle_manager, agent_instances):
        """Test starting all agents."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)

        with patch.object(MockAgent, "start", new_callable=AsyncMock) as mock_start:
            results = await lifecycle_manager.start_all()

        assert len(results) == 3
        assert all(results.values())
        assert mock_start.call_count == 3

    @pytest.mark.asyncio
    async def test_start_all_with_failures(self, lifecycle_manager):
        """Test starting all with some failures."""
        agents = [
            MockAgent(agent_id="agent-1"),
            MockAgent(agent_id="agent-2"),
        ]
        agents[1].start = AsyncMock(side_effect=RuntimeError("Start failed"))

        for agent in agents:
            lifecycle_manager.register_agent(agent)

        results = await lifecycle_manager.start_all()

        assert results["agent-1"] is True
        assert results["agent-2"] is False

    @pytest.mark.asyncio
    async def test_stop_all(self, lifecycle_manager, agent_instances):
        """Test stopping all agents."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)
            # Mark as running
            info = lifecycle_manager.get_agent_info(agent.agent_id)
            info.is_running = True

        with patch.object(MockAgent, "stop", new_callable=AsyncMock) as mock_stop:
            await lifecycle_manager.stop_all(graceful=True)

        assert mock_stop.call_count == 3

    @pytest.mark.asyncio
    async def test_reload_all(self, lifecycle_manager, agent_instances):
        """Test reloading all agents."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)
            agent._reloaded = False

        with patch.object(MockAgent, "reload", new_callable=AsyncMock) as mock_reload:
            results = await lifecycle_manager.reload_all()

        assert len(results) == 3
        assert all(results.values())
        assert mock_reload.call_count == 3


class TestHealthMonitoring:
    """Test health monitoring functionality."""

    @pytest.mark.asyncio
    async def test_get_health_status(self, lifecycle_manager):
        """Test getting health status for all agents."""
        agents = [
            MockAgent(agent_id="agent-1", healthy=True),
            MockAgent(agent_id="agent-2", healthy=False),
        ]

        for agent in agents:
            lifecycle_manager.register_agent(agent)
            info = lifecycle_manager.get_agent_info(agent.agent_id)
            info.is_running = True

        health = await lifecycle_manager.get_health_status()

        assert len(health) == 2
        assert health["agent-1"]["healthy"] is True
        assert health["agent-2"]["healthy"] is False

    def test_get_metrics(self, lifecycle_manager):
        """Test getting aggregate metrics."""
        agents = [
            MockAgent(agent_id="agent-1"),
            MockAgent(agent_id="agent-2"),
        ]

        for agent in agents:
            lifecycle_manager.register_agent(agent)
            agent.tasks_processed = 5
            agent.tasks_failed = 1
            agent.messages_sent = 10
            agent.messages_received = 8

        metrics = lifecycle_manager.get_metrics()

        assert metrics["total_agents"] == 2
        assert metrics["total_tasks_processed"] == 10
        assert metrics["total_tasks_failed"] == 2
        assert metrics["total_messages_sent"] == 20
        assert metrics["total_messages_received"] == 16
        assert metrics["agents_by_role"]["software_developer"] == 2


class TestAgentQuerying:
    """Test agent querying methods."""

    def test_get_agent_ids_by_role(self, lifecycle_manager, agent_instances):
        """Test getting agent IDs by role."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)

        sec_agents = lifecycle_manager.get_agent_ids_by_role(AgentRole.SECURITY)
        assert len(sec_agents) == 1
        assert "sec-1" in sec_agents

        dev_agents = lifecycle_manager.get_agent_ids_by_role(AgentRole.SW_DEV)
        assert len(dev_agents) == 1
        assert "dev-1" in dev_agents

    def test_get_agent_info(self, lifecycle_manager):
        """Test getting info for specific agent."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        info = lifecycle_manager.get_agent_info("test-agent")
        assert info is not None
        assert info.agent_id == "test-agent"
        assert info.role == AgentRole.SW_DEV

    def test_get_agent_info_nonexistent(self, lifecycle_manager):
        """Test getting info for non-existent agent."""
        info = lifecycle_manager.get_agent_info("nonexistent")
        assert info is None

    def test_get_all_agent_info(self, lifecycle_manager, agent_instances):
        """Test getting info for all agents."""
        for agent in agent_instances:
            lifecycle_manager.register_agent(agent)

        all_info = lifecycle_manager.get_all_agent_info()
        assert len(all_info) == 3
        for agent in agent_instances:
            assert agent.agent_id in all_info


class TestContextManager:
    """Test context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_start_stop(self, lifecycle_manager):
        """Test context manager starts and stops agents."""
        agent = MockAgent(agent_id="test-agent")
        lifecycle_manager.register_agent(agent)

        with (
            patch.object(agent, "start", new_callable=AsyncMock) as mock_start,
            patch.object(agent, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            async with lifecycle_manager:
                # Inside context
                assert lifecycle_manager._running is True
                assert lifecycle_manager._monitor_task is not None
                mock_start.assert_called_once()

            # Outside context
            assert lifecycle_manager._running is False
            mock_stop.assert_called_once()

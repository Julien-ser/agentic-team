"""
Unit tests for BaseAgent.

Tests cover agent initialization, lifecycle management, message handling,
task processing, and health checks.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.agents.base_agent import BaseAgent
from src.agents.lifecycle import LifecycleManager, AgentLifecycleInfo
from src.messaging.redis_broker import RedisMessageBroker
from src.protocols.agent_specs import (
    AgentRole,
    Task,
    TaskStatus,
    MessageType,
    AgentMessage,
)


# Concrete agent implementation for testing
class TestAgent(BaseAgent):
    """Concrete agent implementation for testing."""

    def get_role(self) -> AgentRole:
        return AgentRole.SW_DEV

    async def process_task(self, task: Task) -> dict:
        """Test task processor."""
        await asyncio.sleep(0.01)  # Simulate work
        return {
            "success": True,
            "output": {"result": f"Processed: {task.description}"},
            "execution_time": 0.01,
        }


@pytest.fixture
def test_agent():
    """Create a test agent instance."""
    return TestAgent(agent_id="test-agent-1")


@pytest.fixture
def mock_broker():
    """Create mock Redis broker."""
    broker = MagicMock(spec=RedisMessageBroker)
    broker.connect = AsyncMock()
    broker.disconnect = AsyncMock()
    broker.subscribe = AsyncMock(return_value=True)
    broker.unsubscribe = AsyncMock(return_value=True)
    broker.publish = AsyncMock(return_value=True)
    broker.start_listening = AsyncMock()
    broker.stop_listening = AsyncMock()
    return broker


class TestBaseAgentInitialization:
    """Test agent initialization."""

    def test_init_with_defaults(self):
        """Test agent initialization with auto-generated ID."""
        agent = TestAgent()
        assert agent.agent_id.startswith("software_developer-")
        assert agent.role == AgentRole.SW_DEV
        assert agent.broker is not None

    def test_init_with_custom_id(self):
        """Test agent initialization with custom ID."""
        agent = TestAgent(agent_id="custom-id")
        assert agent.agent_id == "custom-id"

    def test_init_with_custom_broker(self, mock_broker):
        """Test agent initialization with custom broker."""
        agent = TestAgent(broker=mock_broker)
        assert agent.broker == mock_broker

    def test_get_role_abstract(self):
        """Test that get_role must be implemented."""
        # Should fail if subclass doesn't implement get_role
        with pytest.raises(TypeError):
            BaseAgent()  # type: ignore


class TestBaseAgentLifecycle:
    """Test agent lifecycle methods."""

    @pytest.mark.asyncio
    async def test_initialize(self, test_agent):
        """Test agent initialization."""
        await test_agent.initialize()
        assert test_agent._initialized is True
        assert test_agent._start_time is not None

    @pytest.mark.asyncio
    async def test_start(self, test_agent, mock_broker):
        """Test agent start."""
        with patch(
            "src.agents.base_agent.RedisMessageBroker", return_value=mock_broker
        ):
            await test_agent.start()

            assert test_agent._running is True
            mock_broker.connect.assert_called_once()
            mock_broker.subscribe.assert_called()
            mock_broker.start_listening.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, test_agent, mock_broker):
        """Test agent stop."""
        test_agent._running = True
        test_agent._initialized = True
        test_agent.broker = mock_broker

        await test_agent.stop()

        assert test_agent._running is False
        mock_broker.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_running(self, test_agent):
        """Test starting an already running agent."""
        test_agent._running = True
        await test_agent.start()
        # Should not raise error, just warn

    @pytest.mark.asyncio
    async def test_stop_not_running(self, test_agent):
        """Test stopping an already stopped agent."""
        test_agent._running = False
        await test_agent.stop()
        # Should not raise error, just warn

    @pytest.mark.asyncio
    async def test_reload_default(self, test_agent):
        """Test default reload implementation."""
        await test_agent.reload()  # Should not raise


class TestBaseAgentTaskProcessing:
    """Test task processing."""

    @pytest.mark.asyncio
    async def test_process_task_success(self, test_agent):
        """Test successful task processing."""
        task = Task(description="Test task", role=AgentRole.SW_DEV)
        result = await test_agent.process_task(task)

        assert result["success"] is True
        assert "Processed: Test task" in result["output"]["result"]

    @pytest.mark.asyncio
    async def test_task_processing_loop(self, test_agent, mock_broker):
        """Test the task processing loop."""
        task = Task(description="Test task", id="task-123", role=AgentRole.SW_DEV)
        test_agent._task_queue.put_nowait(task)

        with patch(
            "src.agents.base_agent.RedisMessageBroker", return_value=mock_broker
        ):
            # Start agent
            await test_agent.start()
            await asyncio.sleep(0.1)

            # Check metrics
            assert test_agent.tasks_processed == 1
            assert test_agent.tasks_failed == 0

            # Stop agent
            await test_agent.stop()

    @pytest.mark.asyncio
    async def test_task_processing_failure(self, test_agent, mock_broker):
        """Test task processing with failure."""

        class FailingAgent(TestAgent):
            async def process_task(self, task: Task) -> dict:
                raise ValueError("Task failed")

        failing_agent = FailingAgent(agent_id="failing-agent")

        task = Task(description="Test task", id="task-456", role=AgentRole.SW_DEV)
        failing_agent._task_queue.put_nowait(task)

        with patch(
            "src.agents.base_agent.RedisMessageBroker", return_value=mock_broker
        ):
            await failing_agent.start()
            await asyncio.sleep(0.1)

            assert failing_agent.tasks_processed == 0
            assert failing_agent.tasks_failed == 1

            await failing_agent.stop()


class TestBaseAgentMessaging:
    """Test A2A messaging."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, test_agent, mock_broker):
        """Test sending a message successfully."""
        test_agent.broker = mock_broker

        with patch("src.agents.base_agent.config") as mock_config:
            mock_config.REDIS_CHANNEL_PREFIX = "wiggum:agentic:"
            success = await test_agent.send_message(
                recipient=AgentRole.FRONTEND,
                message_type=MessageType.API_SPEC_REQUEST,
                payload={"endpoint": "/api/test"},
            )

        assert success is True
        mock_broker.publish.assert_called_once()
        assert test_agent.messages_sent == 1

    @pytest.mark.asyncio
    async def test_send_message_failure(self, test_agent):
        """Test sending message with disconnected broker."""
        test_agent.broker = MagicMock()
        test_agent.broker.publish = AsyncMock(return_value=False)

        success = await test_agent.send_message(
            recipient=AgentRole.FRONTEND,
            message_type=MessageType.API_SPEC_REQUEST,
            payload={},
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_broadcast_message(self, test_agent, mock_broker):
        """Test broadcasting to all agents."""
        test_agent.broker = mock_broker

        with patch("src.agents.base_agent.config") as mock_config:
            mock_config.REDIS_CHANNEL_PREFIX = "wiggum:agentic:"
            count = await test_agent.broadcast_message(
                message_type=MessageType.COMPONENT_READY,
                payload={"component": "TestComp"},
            )

        assert count == 2  # Should send to SECURITY and FRONTEND
        assert mock_broker.publish.call_count == 2

    @pytest.mark.asyncio
    async def test_receive_message(self, test_agent):
        """Test receiving a message."""
        message = AgentMessage(
            sender=AgentRole.FRONTEND,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.API_SPEC_REQUEST,
            payload={"endpoint": "/api/test"},
        )

        await test_agent.receive_message(message)

        assert test_agent.messages_received == 1
        assert test_agent.last_heartbeat is not None

    def test_register_message_handler(self, test_agent):
        """Test registering a message handler."""
        handler = AsyncMock()
        test_agent.register_message_handler(MessageType.API_SPEC_REQUEST, handler)

        assert MessageType.API_SPEC_REQUEST in test_agent._message_handlers
        assert test_agent._message_handlers[MessageType.API_SPEC_REQUEST] == handler


class TestBaseAgentHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_running(self, test_agent):
        """Test health check when agent is running."""
        test_agent._running = True
        test_agent._initialized = True
        test_agent._start_time = datetime.utcnow()
        test_agent.tasks_processed = 5
        test_agent.tasks_failed = 1
        test_agent.messages_sent = 10
        test_agent.messages_received = 8
        test_agent.last_heartbeat = datetime.utcnow()

        health = await test_agent.health_check()

        assert health["healthy"] is True
        assert health["uptime"] >= 0
        assert health["tasks_processed"] == 5
        assert health["messages_sent"] == 10
        assert health["last_heartbeat"] is not None

    @pytest.mark.asyncio
    async def test_health_check_not_running(self, test_agent):
        """Test health check when agent is not running."""
        test_agent._running = False
        health = await test_agent.health_check()
        assert health["healthy"] is False

    def test_get_metrics(self, test_agent):
        """Test getting agent metrics."""
        test_agent.tasks_processed = 8
        test_agent.tasks_failed = 2
        test_agent.messages_sent = 15
        test_agent.messages_received = 12

        metrics = test_agent.get_metrics()

        assert metrics["success_rate"] == 80.0
        assert metrics["tasks_processed"] == 8
        assert metrics["tasks_failed"] == 2


class TestBaseAgentMessageHandlers:
    """Test internal message handling."""

    @pytest.mark.asyncio
    async def test_handle_task_message(self, test_agent, mock_broker):
        """Test handling incoming task message."""
        message_dict = {
            "sender": AgentRole.FRONTEND.value,
            "recipient": AgentRole.SW_DEV.value,
            "message_type": MessageType.TASK_ASSIGNMENT.value,
            "payload": {
                "task": {
                    "id": "task-123",
                    "description": "Test task",
                    "role": AgentRole.SW_DEV.value,
                    "status": TaskStatus.PENDING.value,
                }
            },
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": "test-correlation",
        }

        with patch("src.agents.base_agent.config") as mock_config:
            mock_config.REDIS_CHANNEL_PREFIX = "wiggum:agentic:"
            await test_agent._handle_task_message(message_dict)

        # Task should be queued
        assert not test_agent._task_queue.empty()
        queued_task = await test_agent._task_queue.get()
        assert queued_task.id == "task-123"

    @pytest.mark.asyncio
    async def test_handle_broadcast_message(self, test_agent):
        """Test handling broadcast message."""
        message = AgentMessage(
            sender=AgentRole.SECURITY,
            recipient=AgentRole.SW_DEV,
            message_type=MessageType.SECURITY_ALERT,
            payload={"severity": "high"},
        )

        # Should call receive_message
        await test_agent._handle_broadcast_message(message.dict())
        assert test_agent.messages_received == 1

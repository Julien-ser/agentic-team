"""
Base agent class for all specialized agents in the system.

This module provides the abstract BaseAgent class that all role-specific agents
must inherit from. It defines the standard interface for agent initialization,
task processing, A2A communication, and lifecycle management.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from src.config import config
from src.messaging.redis_broker import RedisMessageBroker
from src.protocols.agent_specs import (
    AgentMessage,
    AgentRole,
    Task,
    TaskStatus,
    MessageType,
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the system.

    Provides common functionality for:
    - A2A message communication via Redis
    - Task queue management
    - Health monitoring and heartbeats
    - Metrics tracking
    - Lifecycle management

    Specialized agents must implement the `process_task` method.
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        broker: Optional[RedisMessageBroker] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if None)
            broker: Redis message broker instance (created if None)
        """
        self.agent_id = agent_id or f"{self.get_role().value}-{uuid.uuid4().hex[:8]}"
        self.role = self.get_role()
        self.broker = broker or RedisMessageBroker()

        # Task queue for incoming tasks
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._current_task: Optional[Task] = None

        # Lifecycle state
        self._running = False
        self._initialized = False
        self._start_time: Optional[datetime] = None

        # Metrics
        self.tasks_processed = 0
        self.tasks_failed = 0
        self.messages_sent = 0
        self.messages_received = 0
        self.last_heartbeat: Optional[datetime] = None

        # Message handlers
        self._message_handlers: Dict[MessageType, Any] = {}

        logger.info(f"Agent {self.agent_id} initialized with role {self.role.value}")

    @abstractmethod
    def get_role(self) -> AgentRole:
        """
        Return the agent's role.

        Must be implemented by subclasses to specify their role.
        Returns:
            AgentRole enum value (SECURITY, SW_DEV, or FRONTEND)
        """
        pass

    @abstractmethod
    async def process_task(self, task: Task) -> Dict[str, Any]:
        """
        Process a task and return results.

        This is the main work method that must be implemented by each agent.
        It should execute the task logic and return a dictionary with results.

        Args:
            task: The task to process

        Returns:
            Dictionary with task results, should include:
            - 'success': bool indicating success
            - 'output': Dict with task output data
            - 'artifacts': List of file paths/URLs (optional)
            - 'errors': List of error messages (optional)
        """
        pass

    async def initialize(self) -> None:
        """
        Initialize agent resources.

        Override this method to perform setup operations like:
        - Connecting to external services
        - Loading models or configurations
        - Initializing state

        Called before the agent starts processing tasks.
        """
        logger.info(f"Initializing agent {self.agent_id}")
        self._start_time = datetime.utcnow()
        self._initialized = True
        logger.info(f"Agent {self.agent_id} initialized successfully")

    async def start(self) -> None:
        """
        Start the agent.

        - Connects to message broker
        - Subscribes to task channels
        - Starts task processing loop
        - Begins heartbeat monitoring
        """
        if self._running:
            logger.warning(f"Agent {self.agent_id} is already running")
            return

        logger.info(f"Starting agent {self.agent_id}")

        try:
            # Initialize if not already
            if not self._initialized:
                await self.initialize()

            # Connect to broker
            await self.broker.connect()

            # Subscribe to role-specific task channel
            task_channel = (
                f"{config.REDIS_CHANNEL_PREFIX}{self.role.value}/task.assignment"
            )
            await self.broker.subscribe(task_channel, self._handle_task_message)

            # Also subscribe to broadcast channel
            broadcast_channel = f"{config.REDIS_CHANNEL_PREFIX}broadcast"
            await self.broker.subscribe(
                broadcast_channel, self._handle_broadcast_message
            )

            # Start listening for messages
            await self.broker.start_listening()

            # Start heartbeat task
            self._running = True
            asyncio.create_task(self._heartbeat_loop())
            asyncio.create_task(self._task_processing_loop())

            logger.info(f"Agent {self.agent_id} started successfully")

        except Exception as e:
            logger.error(f"Failed to start agent {self.agent_id}: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """
        Stop the agent gracefully.

        - Cancels running tasks
        - Disconnects from broker
        - Stops heartbeat and processing loops
        """
        if not self._running:
            logger.warning(f"Agent {self.agent_id} is not running")
            return

        logger.info(f"Stopping agent {self.agent_id}")
        self._running = False

        # Wait for current task to complete (with timeout)
        if self._current_task:
            try:
                await asyncio.wait_for(asyncio.shield(self._current_task), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Agent {self.agent_id} task timed out during stop")

        # Disconnect from broker
        try:
            await self.broker.disconnect()
        except Exception as e:
            logger.error(f"Error during broker disconnect: {e}")

        logger.info(f"Agent {self.agent_id} stopped successfully")

    async def reload(self) -> None:
        """
        Reload agent configuration and resources.

        Override this method to implement dynamic reconfiguration.
        Default implementation just logs the reload.
        """
        logger.info(f"Reloading agent {self.agent_id}")
        # Can be overridden to reload configs, models, etc.

    async def send_message(
        self,
        recipient: AgentRole,
        message_type: MessageType,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Send a message to another agent via Redis.

        Args:
            recipient: Target agent role
            message_type: Type of message (from MessageType enum)
            payload: Message payload dictionary
            correlation_id: Optional correlation ID for request/response tracking

        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            message = AgentMessage(
                sender=self.role,
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id or str(uuid.uuid4()),
            )

            # Serialize message
            message_dict = message.dict()
            message_dict["timestamp"] = message.timestamp.isoformat()

            # Determine channel - use direct queue for role
            channel = (
                f"{config.REDIS_CHANNEL_PREFIX}{recipient.value}/{message_type.value}"
            )

            success = await self.broker.publish(channel, message_dict)
            if success:
                self.messages_sent += 1
                logger.debug(
                    f"Sent message {message_type.value} to {recipient.value} "
                    f"(correlation: {message.correlation_id[:8]})"
                )
            else:
                logger.error(f"Failed to send message to {recipient.value}")

            return success

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def broadcast_message(
        self,
        message_type: MessageType,
        payload: Dict[str, Any],
        exclude: Optional[list[AgentRole]] = None,
    ) -> int:
        """
        Broadcast message to all agents.

        Args:
            message_type: Type of message
            payload: Message payload
            exclude: List of agent roles to exclude from broadcast

        Returns:
            Number of agents the message was sent to
        """
        sent_count = 0
        for role in AgentRole:
            if exclude and role in exclude:
                continue
            if role != self.role:  # Don't send to self
                success = await self.send_message(role, message_type, payload)
                if success:
                    sent_count += 1
        return sent_count

    async def receive_message(self, message: AgentMessage) -> None:
        """
        Handle incoming message from another agent.

        This method is called when a message arrives for this agent.
        It routes the message to appropriate handler based on type.

        Args:
            message: The received AgentMessage
        """
        self.messages_received += 1
        self.last_heartbeat = datetime.utcnow()

        logger.debug(
            f"Received message {message.message_type.value} from {message.sender.value}"
        )

        # Check if we have a handler for this message type
        if message.message_type in self._message_handlers:
            handler = self._message_handlers[message.message_type]
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
        else:
            logger.debug(f"No handler for message type {message.message_type.value}")

    def register_message_handler(self, message_type: MessageType, handler: Any) -> None:
        """
        Register a handler for a specific message type.

        Args:
            message_type: The MessageType to handle
            handler: Async function that takes AgentMessage as argument
        """
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type.value} on {self.agent_id}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check and return status.

        Override this method to add custom health checks.

        Returns:
            Dictionary with health status:
            - 'healthy': bool
            - 'uptime': seconds
            - 'tasks_processed': int
            - 'messages_sent': int
            - 'messages_received': int
        """
        uptime = (
            (datetime.utcnow() - self._start_time).total_seconds()
            if self._start_time
            else 0
        )

        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "healthy": self._running and self._initialized,
            "uptime": uptime,
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "last_heartbeat": self.last_heartbeat.isoformat()
            if self.last_heartbeat
            else None,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get agent performance metrics."""
        total_tasks = self.tasks_processed + self.tasks_failed
        success_rate = (
            (self.tasks_processed / total_tasks * 100) if total_tasks > 0 else 0
        )

        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "tasks_processed": self.tasks_processed,
            "tasks_failed": self.tasks_failed,
            "success_rate": success_rate,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
        }

    # Internal handlers

    async def _handle_task_message(self, message_dict: Dict[str, Any]) -> None:
        """
        Handle incoming task assignment message from Redis.

        Args:
            message_dict: Raw message dictionary from Redis
        """
        try:
            # Parse message
            message = AgentMessage(**message_dict)

            # Validate it's a task assignment
            if message.message_type != MessageType.TASK_ASSIGNMENT:
                logger.debug(f"Ignoring non-task message: {message.message_type.value}")
                return

            # Extract task from payload
            task_data = message.payload.get("task", {})
            if not task_data:
                logger.warning("Task assignment message missing task data")
                return

            task = Task(**task_data)

            # Put task in queue for processing
            await self._task_queue.put(task)
            logger.debug(
                f"Queued task {task.id[:8]} for {self.agent_id} "
                f"(role: {self.role.value})"
            )

        except Exception as e:
            logger.error(f"Error handling task message: {e}")

    async def _handle_broadcast_message(self, message_dict: Dict[str, Any]) -> None:
        """
        Handle broadcast messages.

        Args:
            message_dict: Raw message dictionary from Redis
        """
        try:
            message = AgentMessage(**message_dict)
            await self.receive_message(message)
        except Exception as e:
            logger.error(f"Error handling broadcast message: {e}")

    async def _task_processing_loop(self) -> None:
        """Main task processing loop (runs in background)."""
        logger.info(f"Task processing loop started for {self.agent_id}")

        while self._running:
            try:
                # Wait for task with timeout
                try:
                    task = await asyncio.wait_for(self._task_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Process the task
                self._current_task = task
                try:
                    logger.info(
                        f"Processing task {task.id[:8]}: {task.description[:50]}..."
                    )

                    # Call agent-specific processing
                    result = await self.process_task(task)

                    # Record success
                    self.tasks_processed += 1
                    logger.info(
                        f"Task {task.id[:8]} completed successfully "
                        f"(duration: {result.get('execution_time', 0):.2f}s)"
                    )

                except Exception as e:
                    # Record failure
                    self.tasks_failed += 1
                    logger.error(
                        f"Task {task.id[:8]} failed: {e}",
                        exc_info=True,
                    )

                    # Send failure notification if broker available
                    try:
                        await self.send_message(
                            recipient=AgentRole.SW_DEV,  # Default to SW_DEV for errors
                            message_type=MessageType.TASK_FAILED,
                            payload={
                                "task_id": task.id,
                                "agent_id": self.agent_id,
                                "error": str(e),
                            },
                        )
                    except:
                        pass

                finally:
                    self._current_task = None
                    self._task_queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Task processing loop cancelled for {self.agent_id}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in task loop: {e}")
                await asyncio.sleep(1.0)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats (runs in background)."""
        logger.debug(f"Heartbeat loop started for {self.agent_id}")

        while self._running:
            try:
                await asyncio.sleep(config.AGENT_HEARTBEAT_INTERVAL)

                if not self._running:
                    break

                # Send heartbeat message
                health = await self.health_check()
                await self.send_message(
                    recipient=AgentRole.SW_DEV,  # Send to orchestrator/dev agent
                    message_type=MessageType.HEARTBEAT,
                    payload=health,
                )

                self.last_heartbeat = datetime.utcnow()

            except asyncio.CancelledError:
                logger.debug(f"Heartbeat loop cancelled for {self.agent_id}")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

"""
Message protocol definitions and handlers registry.

This module defines the standard message types and provides a registry
for message handlers that agents can use to process incoming messages.
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

from src.config import config
from src.protocols.agent_specs import AgentMessage, AgentRole, MessageType

logger = logging.getLogger(__name__)


class MessageProtocol:
    """
    Standard message protocol constants for A2A communication.

    These constants define the message types used for agent coordination
    and provide suggested channel naming conventions.
    """

    # Task coordination
    TASK_ASSIGNMENT = "task.assignment"
    TASK_UPDATE = "task.update"
    TASK_COMPLETE = "task.complete"
    TASK_FAILED = "task.failed"

    # Code review workflow
    CODE_REVIEW_REQUEST = "code.review.request"
    CODE_REVIEW_RESPONSE = "code.review.response"

    # Security workflow
    SECURITY_SCAN_REQUEST = "security.scan.request"
    SECURITY_ALERT = "security.alert"
    SECURITY_REPORT = "security.report"
    SECURITY_APPROVAL = "security.approval"

    # API/Component integration
    API_SPEC_REQUEST = "api.spec.request"
    API_SPEC_RESPONSE = "api.spec.response"
    COMPONENT_READY = "component.ready"
    COMPONENT_UPDATE = "component.update"

    # Cross-agent coordination
    DEPENDENCY_UPDATE = "dependency.update"
    SHARED_KNOWLEDGE_UPDATE = "shared_knowledge.update"
    REFACTORING_REQUEST = "refactoring.request"

    # System messages
    HEALTH_CHECK = "health.check"
    HEARTBEAT = "heartbeat"
    BROADCAST = "broadcast"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_RELOAD = "system.reload"

    # Frontend specific
    UI_DESIGN_REQUEST = "ui.design.request"
    UI_DESIGN_RESPONSE = "ui.design.response"
    ACCESSIBILITY_REPORT = "accessibility.report"

    # Dev specific
    TEST_RESULTS = "test.results"
    CODE_QUALITY_REPORT = "code.quality.report"
    DEPENDENCY_VULNERABILITY = "dependency.vulnerability"


class MessageRouter:
    """
    Router for intelligent message delivery with queuing and correlation.

    Features:
    - Route messages to appropriate agents based on role and message type
    - Queue messages for offline agents
    - Correlate request/response pairs using correlation_id
    - Support broadcast messages
    - Track message delivery status
    """

    def __init__(self, broker, state_manager=None):
        """
        Initialize message router.

        Args:
            broker: RedisMessageBroker instance
            state_manager: StateManager for persisting queued messages
        """
        self.broker = broker
        self.state_manager = state_manager
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._offline_queues: Dict[AgentRole, list] = {}
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._running = False

    async def initialize(self) -> None:
        """Initialize router and restore pending messages from state."""
        await self._load_queued_messages()
        self._running = True

    async def route_message(self, message: Any) -> bool:
        """
        Route a message to its intended recipient.

        Args:
            message: AgentMessage to route

        Returns:
            True if message was routed successfully (or queued), False otherwise
        """
        try:
            # Determine target channel based on recipient and message type
            channel = self._get_channel_for_message(message)

            # Check if recipient agent is online (via health check or state)
            if await self._is_agent_online(message.recipient):
                # Send directly via broker
                success = await self.broker.publish(channel, message.dict())
                if success:
                    logger.debug(
                        f"Routed message to {message.recipient.value} via {channel}"
                    )
                return success
            else:
                # Queue for offline agent
                await self._queue_offline_message(message)
                logger.info(f"Agent {message.recipient.value} offline, queued message")
                return True

        except Exception as e:
            logger.error(f"Error routing message: {e}")
            return False

    def _get_channel_for_message(self, message: Any) -> str:
        """
        Determine the appropriate Redis channel for a message.

        Args:
            message: AgentMessage to route

        Returns:
            Redis channel name
        """
        # Base channel prefix
        prefix = (
            config.REDIS_CHANNEL_PREFIX
            if hasattr(config, "REDIS_CHANNEL_PREFIX")
            else "wiggum:agentic:"
        )

        # Special case: broadcast messages go to broadcast channel
        if message.message_type == MessageType.BROADCAST:
            return f"{prefix}broadcast"

        # Standard routing: recipient role + message type
        return f"{prefix}{message.recipient.value}/{message.message_type.value}"

    async def _is_agent_online(self, role: AgentRole) -> bool:
        """
        Check if an agent with the given role is currently online.

        Args:
            role: AgentRole to check

        Returns:
            True if agent appears to be online
        """
        # Check agent state from state manager if available
        if self.state_manager:
            agent_state = self.state_manager.get_agent_state(role.value)
            if agent_state:
                # Check last heartbeat (assume offline if no heartbeat for 2x interval)
                import time
                from datetime import datetime, timedelta

                last_heartbeat = agent_state.get("last_heartbeat")
                if last_heartbeat:
                    try:
                        hb_time = datetime.fromisoformat(last_heartbeat)
                        time_diff = datetime.utcnow() - hb_time
                        if time_diff < timedelta(
                            seconds=config.AGENT_HEARTBEAT_INTERVAL * 2
                        ):
                            return True
                    except:
                        pass

        # Fallback: assume online (optimistic routing)
        # In production, could use Redis presence detection or agent registry
        return True

    async def _queue_offline_message(self, message: Any) -> None:
        """
        Store message for delivery when agent comes back online.

        Args:
            message: AgentMessage to queue
        """
        # Add to in-memory queue
        if message.recipient not in self._offline_queues:
            self._offline_queues[message.recipient] = []
        self._offline_queues[message.recipient].append(message.dict())

        # Persist to state manager if available
        if self.state_manager:
            await self.state_manager.store_queued_message(
                recipient=message.recipient.value, message=message.dict()
            )

    async def _load_queued_messages(self) -> None:
        """Load previously queued messages from persistent storage."""
        if not self.state_manager:
            return

        queued = await self.state_manager.get_queued_messages()
        for msg_data in queued:
            try:
                recipient = AgentRole(msg_data["recipient"])
                await self._queue_offline_message(AgentMessage(**msg_data))
                # Mark as loaded (could delete or mark as pending)
            except Exception as e:
                logger.error(f"Error loading queued message: {e}")

    async def deliver_queued_messages(self, role: AgentRole) -> int:
        """
        Attempt to deliver all queued messages for an agent that just came online.

        Args:
            role: AgentRole that came online

        Returns:
            Number of messages delivered
        """
        delivered = 0
        if role in self._offline_queues:
            queue = self._offline_queues[role].copy()
            self._offline_queues[role] = []  # Clear queue

            for msg_data in queue:
                try:
                    message = AgentMessage(**msg_data)
                    channel = self._get_channel_for_message(message)
                    success = await self.broker.publish(channel, message.dict())
                    if success:
                        delivered += 1
                        # Remove from persistent storage
                        if self.state_manager:
                            await self.state_manager.remove_queued_message(
                                msg_data.get("id")
                            )
                    else:
                        # Re-queue if delivery fails
                        await self._queue_offline_message(message)
                except Exception as e:
                    logger.error(f"Error delivering queued message: {e}")

        return delivered

    async def send_request(
        self,
        recipient: AgentRole,
        message_type: MessageType,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a request and wait for correlated response.

        Args:
            recipient: Target agent role
            message_type: Type of request message
            payload: Request payload
            timeout: Time to wait for response in seconds

        Returns:
            Response payload dict, or None if timeout/failure
        """
        import uuid

        correlation_id = str(uuid.uuid4())

        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[correlation_id] = future

        try:
            # Send request
            from src.protocols.agent_specs import AgentMessage

            message = AgentMessage(
                sender=AgentRole.SW_DEV,  # Should be sender's role
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )

            success = await self.route_message(message)
            if not success:
                self._pending_responses.pop(correlation_id, None)
                return None

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout: {message_type.value} to {recipient.value}"
            )
            self._pending_responses.pop(correlation_id, None)
            return None
        except Exception as e:
            logger.error(f"Error in send_request: {e}")
            self._pending_responses.pop(correlation_id, None)
            return None

    async def handle_response(self, message: Any) -> None:
        """
        Handle an incoming response message by resolving pending request.

        Args:
            message: AgentMessage that is a response to a previous request
        """
        if not message.correlation_id:
            logger.debug("Response message missing correlation_id")
            return

        if message.correlation_id in self._pending_responses:
            future = self._pending_responses[message.correlation_id]
            if not future.done():
                future.set_result(message.payload)
            self._pending_responses.pop(message.correlation_id, None)
            logger.debug(f"Resolved pending request {message.correlation_id[:8]}")
        else:
            logger.debug(
                f"Received response for unknown correlation_id: {message.correlation_id[:8]}"
            )

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:
        """
        Register a handler for a specific message type.

        Args:
            message_type: MessageType enum value
            handler: Async function that accepts AgentMessage
        """
        self._message_handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type.value}")

    async def handle_message(self, message: Any) -> None:
        """
        Process an incoming message through registered handlers.

        Args:
            message: AgentMessage to process
        """
        try:
            # Check if this is a response to a pending request
            if message.correlation_id and message.message_type in [
                MessageType.CODE_REVIEW_RESPONSE,
                MessageType.API_SPEC_RESPONSE,
                MessageType.SECURITY_REPORT,
                MessageType.COMPONENT_READY,
            ]:
                await self.handle_response(message)
                return

            # Route to appropriate handler
            if message.message_type in self._message_handlers:
                handler = self._message_handlers[message.message_type]
                await handler(message)
            else:
                logger.debug(
                    f"No handler for message type: {message.message_type.value}"
                )

        except Exception as e:
            logger.error(f"Error in message handler: {e}")

    async def broadcast(
        self,
        sender: AgentRole,
        message_type: MessageType,
        payload: Dict[str, Any],
        exclude: Optional[list[AgentRole]] = None,
    ) -> int:
        """
        Broadcast message to all agents except sender and excluded.

        Args:
            sender: Agent sending broadcast
            message_type: Type of message
            payload: Message payload
            exclude: Optional list of roles to exclude

        Returns:
            Number of agents message was sent to
        """
        from src.protocols.agent_specs import AgentMessage

        sent_count = 0
        exclude_set = set(exclude or [])
        exclude_set.add(sender)  # Don't send to self

        for role in AgentRole:
            if role in exclude_set:
                continue

            message = AgentMessage(
                sender=sender,
                recipient=role,
                message_type=message_type,
                payload=payload,
            )

            if await self.route_message(message):
                sent_count += 1

        logger.info(f"Broadcast {message_type.value} sent to {sent_count} agents")
        return sent_count

    def get_queued_count(self, role: AgentRole) -> int:
        """Get number of queued messages for an agent."""
        return len(self._offline_queues.get(role, []))

    def get_pending_requests_count(self) -> int:
        """Get number of pending request/response pairs."""
        return len(self._pending_responses)

    async def shutdown(self) -> None:
        """Clean shutdown of router."""
        self._running = False

        # Cancel any pending futures
        for future in self._pending_responses.values():
            if not future.done():
                future.cancel()
        self._pending_responses.clear()

        logger.info("Message router shutdown complete")

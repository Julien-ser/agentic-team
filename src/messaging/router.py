"""
Message router for intelligent A2A communication.

This module implements the MessageRouter class which provides:
- Intelligent message routing based on recipient and message type
- Offline message queuing for unavailable agents
- Request/response correlation tracking
- Broadcast message handling
- Integration with state manager for persistence
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from src.config import config
from src.protocols.agent_specs import AgentMessage, AgentRole, MessageType

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    Intelligent message routing with queuing and correlation.

    The MessageRouter acts as an intermediary between agents and the
    Redis message broker, providing:
    - Dynamic channel routing based on message type and recipient
    - Offline agent detection and message queuing
    - Request/response correlation with timeout handling
    - Broadcast message delivery to all online agents
    - Persistent message storage for reliability
    """

    def __init__(self, broker, state_manager=None):
        """
        Initialize message router.

        Args:
            broker: RedisMessageBroker instance for message delivery
            state_manager: Optional StateManager for persistent queuing
        """
        self.broker = broker
        self.state_manager = state_manager

        # Pending request/response tracking
        self._pending_responses: Dict[str, asyncio.Future] = {}

        # Offline message queues per role
        self._offline_queues: Dict[AgentRole, List[Dict[str, Any]]] = {}

        # Message handler registry
        self._message_handlers: Dict[MessageType, List[Callable]] = {}

        # Running state
        self._running = False
        self._initialized = False

        logger.info("MessageRouter initialized")

    async def initialize(self) -> None:
        """Initialize router and restore queued messages from persistent storage."""
        if self._initialized:
            logger.warning("Router already initialized")
            return

        logger.info("Initializing MessageRouter")

        # Load queued messages from state manager if available
        if self.state_manager:
            await self._load_queued_messages()

        self._initialized = True
        logger.info("MessageRouter initialized successfully")

    async def route(self, message: AgentMessage) -> bool:
        """
        Route a message to its intended recipient.

        This method determines the appropriate channel and delivers the
        message, either directly or by queuing if the recipient is offline.

        Args:
            message: AgentMessage to route

        Returns:
            True if message was delivered or queued successfully, False on failure
        """
        try:
            # Determine target channel
            channel = self._get_channel_for_message(message)

            # Check if recipient is online
            if await self._is_recipient_online(message.recipient):
                # Deliver directly
                success = await self.broker.publish(channel, message.dict())
                if success:
                    logger.debug(
                        f"Routed {message.message_type.value} to {message.recipient.value} "
                        f"via {channel} (correlation: {message.correlation_id[:8]})"
                    )
                return success
            else:
                # Queue for later delivery
                await self._queue_message(message)
                logger.info(
                    f"Recipient {message.recipient.value} offline, "
                    f"queued message {message.message_type.value}"
                )
                return True

        except Exception as e:
            logger.error(f"Error routing message: {e}", exc_info=True)
            return False

    def _get_channel_for_message(self, message: AgentMessage) -> str:
        """
        Determine the Redis channel name for a message.

        Args:
            message: AgentMessage to route

        Returns:
            Redis channel string
        """
        # Broadcast messages go to dedicated broadcast channel
        if message.recipient == AgentRole.BROADCAST:
            return f"{config.REDIS_CHANNEL_PREFIX}broadcast"

        # Standard: role-specific channel with message type
        return (
            f"{config.REDIS_CHANNEL_PREFIX}"
            f"{message.recipient.value}/{message.message_type.value}"
        )

    async def _is_recipient_online(self, role: AgentRole) -> bool:
        """
        Check if an agent with the given role is online.

        Uses multiple strategies:
        1. State manager agent heartbeat check
        2. In-memory tracking (could be extended with Redis presence)

        Args:
            role: AgentRole to check

        Returns:
            True if agent appears to be available
        """
        # Check state manager for agent health
        if self.state_manager:
            agent_state = self.state_manager.get_agent_state(role.value)
            if agent_state:
                # Parse last heartbeat and check against timeout
                from datetime import datetime, timedelta

                last_heartbeat_str = agent_state.get("last_heartbeat")
                if last_heartbeat_str:
                    try:
                        last_heartbeat = datetime.fromisoformat(last_heartbeat_str)
                        time_since_hb = datetime.utcnow() - last_heartbeat
                        # Consider offline if no heartbeat for 2x interval
                        if time_since_hb < timedelta(
                            seconds=config.AGENT_HEARTBEAT_INTERVAL * 2
                        ):
                            return True
                        else:
                            logger.debug(
                                f"Agent {role.value} appears offline "
                                f"(last heartbeat: {time_since_hb.total_seconds():.0f}s ago)"
                            )
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"Invalid heartbeat format for {role.value}: {e}"
                        )

        # Optimistic default: assume online (can be made stricter)
        # In production, could use Redis presence or explicit agent registry
        return True

    async def _queue_message(self, message: AgentMessage) -> None:
        """
        Queue a message for offline agent.

        Stores in memory and optionally in persistent storage.

        Args:
            message: AgentMessage to queue
        """
        # Add to in-memory queue
        msg_dict = message.dict()
        msg_dict["timestamp"] = message.timestamp.isoformat()

        if message.recipient not in self._offline_queues:
            self._offline_queues[message.recipient] = []
        self._offline_queues[message.recipient].append(msg_dict)

        # Persist to state manager if available
        if self.state_manager:
            await self.state_manager.store_queued_message(
                recipient=message.recipient.value, message=msg_dict
            )

        logger.debug(
            f"Queued message for {message.recipient.value}, "
            f"queue size: {len(self._offline_queues[message.recipient])}"
        )

    async def _load_queued_messages(self) -> None:
        """Load previously queued messages from persistent storage."""
        if not self.state_manager:
            return

        try:
            queued_messages = await self.state_manager.get_queued_messages()
            for msg_data in queued_messages:
                try:
                    recipient = AgentRole(msg_data["recipient"])
                    message = AgentMessage(**msg_data)
                    await self._queue_message(message)
                except Exception as e:
                    logger.error(f"Failed to load queued message: {e}")

            logger.info(f"Loaded {len(queued_messages)} queued messages from storage")
        except Exception as e:
            logger.error(f"Error loading queued messages: {e}")

    async def deliver_queued(self, role: AgentRole) -> int:
        """
        Attempt to deliver all queued messages for an agent that came online.

        Args:
            role: AgentRole that just became available

        Returns:
            Number of messages delivered successfully
        """
        if role not in self._offline_queues or not self._offline_queues[role]:
            return 0

        queue = self._offline_queues[role].copy()
        self._offline_queues[role] = []  # Clear in-memory queue

        delivered = 0
        for msg_dict in queue:
            try:
                message = AgentMessage(**msg_dict)
                channel = self._get_channel_for_message(message)
                success = await self.broker.publish(channel, message.dict())

                if success:
                    delivered += 1
                    # Remove from persistent storage
                    if self.state_manager and "id" in msg_dict:
                        await self.state_manager.remove_queued_message(msg_dict["id"])
                else:
                    # Re-queue if delivery fails
                    await self._queue_message(message)

            except Exception as e:
                logger.error(f"Error delivering queued message to {role.value}: {e}")

        logger.info(
            f"Delivered {delivered}/{len(queue)} queued messages to {role.value}"
        )
        return delivered

    async def send_request(
        self,
        sender: AgentRole,
        recipient: AgentRole,
        message_type: MessageType,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a request and wait for correlated response.

        Uses correlation_id to match request/response pairs.

        Args:
            sender: Agent sending request
            recipient: Target agent role
            message_type: Type of request message
            payload: Request payload dictionary
            timeout: Time to wait for response in seconds

        Returns:
            Response payload dict, or None on timeout/failure
        """
        import uuid

        correlation_id = str(uuid.uuid4())

        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[correlation_id] = future

        try:
            # Construct message
            message = AgentMessage(
                sender=sender,
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )

            # Route the message
            success = await self.route(message)
            if not success:
                self._pending_responses.pop(correlation_id, None)
                logger.error(
                    f"Failed to send request {message_type.value} to {recipient.value}"
                )
                return None

            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout: {message_type.value} to {recipient.value} "
                f"(correlation: {correlation_id[:8]})"
            )
            self._pending_responses.pop(correlation_id, None)
            return None
        except Exception as e:
            logger.error(f"Error in send_request: {e}", exc_info=True)
            self._pending_responses.pop(correlation_id, None)
            return None

    async def handle_response(self, message: AgentMessage) -> None:
        """
        Process an incoming response message by resolving pending request.

        Args:
            message: AgentMessage containing response
        """
        if not message.correlation_id:
            logger.debug("Response message missing correlation_id")
            return

        correlation_id = message.correlation_id
        if correlation_id in self._pending_responses:
            future = self._pending_responses[correlation_id]
            if not future.done():
                future.set_result(message.payload)
                logger.debug(f"Resolved pending request {correlation_id[:8]}")
            # Remove from pending after resolution
            self._pending_responses.pop(correlation_id, None)
        else:
            logger.debug(f"Unmatched response for correlation_id: {correlation_id[:8]}")

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable[[AgentMessage], asyncio.Future],
    ) -> None:
        """
        Register a handler for a specific message type.

        Args:
            message_type: MessageType enum to handle
            handler: Async function that accepts AgentMessage parameter
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []

        self._message_handlers[message_type].append(handler)
        logger.debug(f"Registered handler for {message_type.value}")

    def unregister_handler(self, message_type: MessageType, handler: Callable) -> bool:
        """
        Remove a message handler.

        Args:
            message_type: MessageType to unregister from
            handler: Handler function to remove

        Returns:
            True if handler was removed, False if not found
        """
        if message_type in self._message_handlers:
            try:
                self._message_handlers[message_type].remove(handler)
                logger.debug(f"Unregistered handler for {message_type.value}")
                return True
            except ValueError:
                pass
        return False

    async def process_message(self, message: AgentMessage) -> None:
        """
        Process an incoming message through appropriate handlers.

        Args:
            message: AgentMessage to process
        """
        try:
            # Check if this is a response to a pending request
            if message.correlation_id and self._is_response_message_type(
                message.message_type
            ):
                await self.handle_response(message)
                return

            # Invoke registered handlers for this message type
            if message.message_type in self._message_handlers:
                handlers = self._message_handlers[message.message_type]
                for handler in handlers:
                    try:
                        # Schedule handler execution (don't await to allow parallel processing)
                        asyncio.create_task(handler(message))
                    except Exception as e:
                        logger.error(
                            f"Error in handler for {message.message_type.value}: {e}",
                            exc_info=True,
                        )
            else:
                logger.debug(
                    f"No handlers for message type: {message.message_type.value}"
                )

        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}", exc_info=True)

    def _is_response_message_type(self, message_type: MessageType) -> bool:
        """
        Determine if a message type is typically a response.

        Args:
            message_type: MessageType to check

        Returns:
            True if this is a response-type message
        """
        response_patterns = [
            MessageType.CODE_REVIEW_RESPONSE,
            MessageType.API_SPEC_RESPONSE,
            MessageType.SECURITY_REPORT,
            MessageType.SECURITY_APPROVAL,
            MessageType.COMPONENT_READY,
            MessageType.TASK_COMPLETE,
            MessageType.TASK_FAILED,
            MessageType.HEARTBEAT,
        ]
        return message_type in response_patterns

    async def broadcast(
        self,
        sender: AgentRole,
        message_type: MessageType,
        payload: Dict[str, Any],
        exclude: Optional[List[AgentRole]] = None,
        correlation_id: Optional[str] = None,
    ) -> int:
        """
        Broadcast message to all agents (optionally excluding some).

        Args:
            sender: Agent sending broadcast
            message_type: Type of message to broadcast
            payload: Message payload
            exclude: Optional list of roles to exclude from broadcast
            correlation_id: Optional correlation ID

        Returns:
            Number of agents message was successfully sent to
        """
        from src.protocols.agent_specs import AgentMessage

        exclude_set = set(exclude or [])
        exclude_set.add(sender)  # Don't send to self

        sent_count = 0
        for role in AgentRole:
            if role in exclude_set:
                continue

            message = AgentMessage(
                sender=sender,
                recipient=role,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )

            if await self.route(message):
                sent_count += 1

        logger.info(
            f"Broadcast {message_type.value} from {sender.value} "
            f"sent to {sent_count} agents"
        )
        return sent_count

    def get_queue_sizes(self) -> Dict[str, int]:
        """Get message queue sizes for all roles."""
        return {role.value: len(queue) for role, queue in self._offline_queues.items()}

    def get_pending_requests_count(self) -> int:
        """Get number of pending request/response operations."""
        return len(self._pending_responses)

    async def cancel_pending_requests(self) -> None:
        """Cancel all pending request futures (e.g., on shutdown)."""
        for correlation_id, future in self._pending_responses.items():
            if not future.done():
                future.cancel()
                logger.debug(f"Cancelled pending request {correlation_id[:8]}")
        self._pending_responses.clear()

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the router.

        Cancels pending operations and logs final statistics.
        """
        if not self._running:
            return

        logger.info("Shutting down MessageRouter")
        self._running = False

        # Cancel pending futures
        await self.cancel_pending_requests()

        # Log final queue statistics
        total_queued = sum(len(q) for q in self._offline_queues.values())
        logger.info(f"Router shutdown: {total_queued} messages remain queued")

        logger.info("MessageRouter shutdown complete")

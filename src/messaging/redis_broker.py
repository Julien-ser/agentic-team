"""
Redis-based message broker for A2A communication.
Implements pub/sub pattern with direct queues for agent routing.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
import redis.asyncio as redis

from src.config import config

logger = logging.getLogger(__name__)


class RedisMessageBroker:
    """Message broker using Redis pub/sub for agent communication."""

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._subscribers = {}
        self._running = False
        self._listen_task = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._redis = await redis.from_url(
                config.get_redis_url(), decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            logger.info("Connected to Redis at %s", config.get_redis_url())
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup."""
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("Disconnected from Redis")

    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """
        Publish message to a channel/topic.

        Args:
            channel: Target channel name
            message: Dictionary message to serialize and send

        Returns:
            True if published successfully, False otherwise
        """
        try:
            payload = json.dumps(message)
            result = await self._redis.publish(channel, payload)
            logger.debug("Published to %s: %s", channel, message.get("type", "unknown"))
            return result > 0
        except Exception as e:
            logger.error("Failed to publish to %s: %s", channel, e)
            return False

    async def subscribe(
        self, channel: str, callback: Callable[[Dict[str, Any]], None]
    ) -> bool:
        """
        Subscribe to a channel with callback for message handling.

        Args:
            channel: Channel to subscribe to
            callback: Async function to call when message arrives

        Returns:
            True if subscribed successfully
        """
        try:
            await self._pubsub.subscribe(channel)
            self._subscribers[channel] = callback
            logger.info("Subscribed to channel: %s", channel)
            return True
        except Exception as e:
            logger.error("Failed to subscribe to %s: %s", channel, e)
            return False

    async def unsubscribe(self, channel: str) -> bool:
        """Unsubscribe from a channel."""
        try:
            await self._pubsub.unsubscribe(channel)
            self._subscribers.pop(channel, None)
            logger.info("Unsubscribed from channel: %s", channel)
            return True
        except Exception as e:
            logger.error("Failed to unsubscribe from %s: %s", channel, e)
            return False

    async def create_direct_queue(self, agent_role: str) -> str:
        """
        Create a dedicated queue/channel for an agent role.

        Args:
            agent_role: The agent role (e.g., 'security', 'software_developer')

        Returns:
            Queue/channel name
        """
        queue_name = f"agent:{agent_role}:queue"
        logger.info("Created direct queue for role %s: %s", agent_role, queue_name)
        return queue_name

    async def start_listening(self) -> None:
        """Start background task to listen for messages."""
        if self._listen_task and not self._listen_task.done():
            logger.warning("Already listening for messages")
            return

        self._running = True
        self._listen_task = asyncio.create_task(self._message_listener())
        logger.info("Started message listener")

    async def stop_listening(self) -> None:
        """Stop the background message listener."""
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped message listener")

    async def _message_listener(self) -> None:
        """Background task that listens for messages and dispatches to callbacks."""
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]

                    try:
                        parsed = json.loads(data)
                        if channel in self._subscribers:
                            callback = self._subscribers[channel]
                            await callback(parsed)
                        else:
                            logger.debug("No subscriber for channel: %s", channel)
                    except json.JSONDecodeError as e:
                        logger.error("Failed to parse message on %s: %s", channel, e)
                    except Exception as e:
                        logger.error("Error in message callback for %s: %s", channel, e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in message listener: %s", e)
                await asyncio.sleep(1.0)

    async def broadcast(
        self, message: Dict[str, Any], exclude: Optional[list[str]] = None
    ) -> int:
        """
        Broadcast message to all agent direct queues.

        Args:
            message: Message to broadcast
            exclude: List of agent roles to exclude from broadcast

        Returns:
            Number of queues the message was sent to
        """
        roles = ["security", "software_developer", "frontend"]
        if exclude:
            roles = [r for r in roles if r not in exclude]

        queue_name = "agent:broadcast"
        # For simplicity, broadcast to a broadcast channel
        # In production, might iterate over individual queues
        await self.publish(queue_name, message)
        return len(roles)

    async def send_to_role(self, role: str, message: Dict[str, Any]) -> bool:
        """
        Send message directly to an agent role's queue.

        Args:
            role: Target agent role
            message: Message to send

        Returns:
            True if sent successfully
        """
        queue_name = await self.create_direct_queue(role)
        return await self.publish(queue_name, message)

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            if self._redis:
                await self._redis.ping()
                return True
            return False
        except Exception:
            return False

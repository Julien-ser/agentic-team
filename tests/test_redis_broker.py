"""
Unit tests for RedisMessageBroker.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.messaging.redis_broker import RedisMessageBroker


@pytest.fixture
def broker():
    """Create broker instance for testing."""
    return RedisMessageBroker()


@pytest.fixture
def mock_redis():
    """Create mock Redis instance."""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.publish = AsyncMock(return_value=1)
    redis_mock.pubsub.return_value = AsyncMock()
    redis_mock.close = AsyncMock()
    return redis_mock


@pytest.mark.asyncio
async def test_connect_success(broker, mock_redis):
    """Test successful Redis connection."""
    mock_from_url = AsyncMock(return_value=mock_redis)
    with patch("src.messaging.redis_broker.redis.from_url", mock_from_url):
        await broker.connect()
        assert broker._redis is not None
        assert broker._pubsub is not None
        mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure(broker):
    """Test Redis connection failure."""
    with patch(
        "src.messaging.redis_broker.redis.from_url",
        side_effect=Exception("Connection error"),
    ):
        with pytest.raises(Exception):
            await broker.connect()


@pytest.mark.asyncio
async def test_publish_success(broker, mock_redis):
    """Test successful message publishing."""
    broker._redis = mock_redis
    message = {"type": "test.message", "data": "hello"}
    result = await broker.publish("test_channel", message)
    assert result is True
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == "test_channel"
    parsed_data = json.loads(call_args[0][1])
    assert parsed_data["type"] == "test.message"


@pytest.mark.asyncio
async def test_publish_failure(broker):
    """Test message publishing failure."""
    broker._redis = None
    message = {"type": "test.message"}
    result = await broker.publish("test_channel", message)
    assert result is False


@pytest.mark.asyncio
async def test_subscribe_success(broker, mock_redis):
    """Test successful subscription."""
    broker._pubsub = mock_redis.pubsub.return_value
    callback = AsyncMock()

    result = await broker.subscribe("test_channel", callback)
    assert result is True
    assert "test_channel" in broker._subscribers
    assert broker._subscribers["test_channel"] == callback
    mock_redis.pubsub.return_value.subscribe.assert_called_once_with("test_channel")


@pytest.mark.asyncio
async def test_unsubscribe_success(broker, mock_redis):
    """Test successful unsubscription."""
    broker._pubsub = mock_redis.pubsub.return_value
    broker._subscribers["test_channel"] = AsyncMock()

    result = await broker.unsubscribe("test_channel")
    assert result is True
    assert "test_channel" not in broker._subscribers
    mock_redis.pubsub.return_value.unsubscribe.assert_called_once_with("test_channel")


@pytest.mark.asyncio
async def test_create_direct_queue(broker):
    """Test direct queue creation for agent roles."""
    queue_name = await broker.create_direct_queue("security")
    assert queue_name == "agent:security:queue"

    queue_name = await broker.create_direct_queue("software_developer")
    assert queue_name == "agent:software_developer:queue"


@pytest.mark.asyncio
async def test_start_listening(broker, mock_redis):
    """Test starting message listener."""
    broker._pubsub = mock_redis.pubsub.return_value
    broker._redis = mock_redis

    await broker.start_listening()
    assert broker._running is True
    assert broker._listen_task is not None

    await broker.stop_listening()
    assert broker._running is False


@pytest.mark.asyncio
async def test_message_listener_dispatch(broker, mock_redis):
    """Test that listener correctly dispatches messages to callbacks."""
    broker._pubsub = mock_redis.pubsub.return_value
    broker._redis = mock_redis
    broker._subscribers["test_channel"] = AsyncMock()

    # Simulate incoming message
    test_message = {"type": "test.message", "payload": "data"}
    mock_message = {
        "type": "message",
        "channel": "test_channel",
        "data": json.dumps(test_message),
    }

    # Mock get_message to return our test message then None to exit
    mock_redis.pubsub.return_value.get_message.side_effect = [
        mock_message,
        None,
        asyncio.CancelledError(),
    ]

    broker._running = True
    try:
        await broker._message_listener()
    except asyncio.CancelledError:
        pass

    # Verify callback was called with parsed message
    broker._subscribers["test_channel"].assert_called_once_with(test_message)


@pytest.mark.asyncio
async def test_message_listener_invalid_json(broker, mock_redis):
    """Test listener handles invalid JSON gracefully."""
    broker._pubsub = mock_redis.pubsub.return_value
    broker._redis = mock_redis
    broker._subscribers["test_channel"] = AsyncMock()

    # Simulate message with invalid JSON
    mock_message = {
        "type": "message",
        "channel": "test_channel",
        "data": "invalid json",
    }
    mock_redis.pubsub.return_value.get_message.return_value = mock_message

    broker._running = True
    # Should not raise exception
    await asyncio.sleep(0.1)
    broker._running = False

    # Callback should not be called
    broker._subscribers["test_channel"].assert_not_called()


@pytest.mark.asyncio
async def test_broadcast(broker, mock_redis):
    """Test broadcast to all agents."""
    broker._redis = mock_redis
    message = {"type": "broadcast.message"}
    result = await broker.broadcast(message)
    assert result == 3
    mock_redis.publish.assert_called_once()


@pytest.mark.asyncio
async def test_send_to_role(broker, mock_redis):
    """Test sending message to specific role."""
    broker._redis = mock_redis
    message = {"type": "role.message"}
    result = await broker.send_to_role("frontend", message)
    assert result is True
    # Should publish to agent:frontend:queue
    call_args = mock_redis.publish.call_args
    assert "agent:frontend:queue" in call_args[0][0]


@pytest.mark.asyncio
async def test_health_check_connected(broker, mock_redis):
    """Test health check when connected."""
    broker._redis = mock_redis
    result = await broker.health_check()
    assert result is True
    mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_disconnected(broker):
    """Test health check when not connected."""
    broker._redis = None
    result = await broker.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_disconnect(broker, mock_redis):
    """Test proper cleanup on disconnect."""
    broker._redis = mock_redis
    broker._pubsub = mock_redis.pubsub.return_value

    # Create a cancellable task that runs indefinitely
    cancel_flag = False

    async def long_running_task():
        nonlocal cancel_flag
        try:
            while not cancel_flag:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(long_running_task())
    broker._listen_task = task

    await broker.disconnect()
    mock_redis.close.assert_called_once()
    assert task.cancelled()

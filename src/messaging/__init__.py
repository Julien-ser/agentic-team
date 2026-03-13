"""
Messaging subsystem for A2A communication.

Provides:
- RedisMessageBroker: Pub/sub message transport
- MessageRouter: Intelligent routing with queuing and correlation
- Protocol: Message type definitions and handlers registry
"""

from .redis_broker import RedisMessageBroker
from .router import MessageRouter
from .protocol import MessageProtocol, MessageRouter as _MR

__all__ = [
    "RedisMessageBroker",
    "MessageRouter",
    "MessageProtocol",
]

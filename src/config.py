"""
Centralized configuration management for the Agentic Team system.
Loads environment variables with defaults.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration with environment variable fallbacks."""

    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

    # SQLite Configuration
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "agentic_team.db")

    # OpenRouter Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    WIGGUM_MODEL: str = os.getenv(
        "WIGGUM_MODEL", "openrouter/stepfun/step-3.5-flash:free"
    )

    # Flask Configuration
    FLASK_HOST: str = os.getenv("FLASK_HOST", "localhost")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", 5000))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Agent Configuration
    AGENT_HEARTBEAT_INTERVAL: int = int(os.getenv("AGENT_HEARTBEAT_INTERVAL", 30))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", 3))
    REDIS_CHANNEL_PREFIX: str = os.getenv("REDIS_CHANNEL_PREFIX", "wiggum:agentic:")

    # JWT Authentication Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_DELTA: int = int(os.getenv("JWT_EXPIRATION_DELTA", 3600))
    JWT_REFRESH_EXPIRATION_DELTA: int = int(
        os.getenv("JWT_REFRESH_EXPIRATION_DELTA", 604800)
    )
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", 12))

    # Rate Limiting Configuration
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = int(
        os.getenv("RATE_LIMIT_LOGIN_MAX_ATTEMPTS", 5)
    )
    RATE_LIMIT_LOGIN_WINDOW: int = int(
        os.getenv("RATE_LIMIT_LOGIN_WINDOW", 900)  # 15 minutes in seconds
    )
    RATE_LIMIT_REGISTER_MAX_ATTEMPTS: int = int(
        os.getenv("RATE_LIMIT_REGISTER_MAX_ATTEMPTS", 10)
    )
    RATE_LIMIT_REGISTER_WINDOW: int = int(
        os.getenv("RATE_LIMIT_REGISTER_WINDOW", 3600)  # 1 hour in seconds
    )
    RATE_LIMIT_DEFAULT_STORAGE: str = os.getenv(
        "RATE_LIMIT_DEFAULT_STORAGE", "memory"
    )  # Options: "memory", "redis"

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration values."""
        errors = []
        if not cls.OPENROUTER_API_KEY:
            errors.append("OPENROUTER_API_KEY is required")
        return errors

    @classmethod
    def get_redis_url(cls) -> str:
        """Build Redis connection URL."""
        auth = f":{cls.REDIS_PASSWORD}@" if cls.REDIS_PASSWORD else ""
        return f"redis://{auth}{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"


# Global config instance
config = Config()

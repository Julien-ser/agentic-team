from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime
from typing import Dict, List, Any, Optional
import uuid


class AgentRole(str, Enum):
    """Agent roles in the system."""

    SECURITY = "security"
    SW_DEV = "software_developer"
    FRONTEND = "frontend_developer"


class MessageType(str, Enum):
    """Standard message types for A2A communication."""

    # Task-related messages
    TASK_ASSIGNMENT = "task.assignment"
    TASK_UPDATE = "task.update"
    TASK_COMPLETE = "task.complete"
    TASK_FAILED = "task.failed"

    # Code review and security
    CODE_REVIEW_REQUEST = "code.review.request"
    CODE_REVIEW_RESPONSE = "code.review.response"
    SECURITY_SCAN_REQUEST = "security.scan.request"
    SECURITY_ALERT = "security.alert"
    SECURITY_REPORT = "security.report"

    # API and component integration
    API_SPEC_REQUEST = "api.spec.request"
    API_SPEC_RESPONSE = "api.spec.response"
    COMPONENT_READY = "component.ready"
    COMPONENT_UPDATE = "component.update"

    # Cross-agent coordination
    DEPENDENCY_UPDATE = "dependency.update"
    SHARED_KNOWLEDGE_UPDATE = "shared_knowledge.update"
    HEALTH_CHECK = "health.check"
    HEARTBEAT = "heartbeat"
    BROADCAST = "broadcast"


class AgentMessage(BaseModel):
    """Standard message format for agent-to-agent communication."""

    sender: AgentRole
    recipient: AgentRole
    message_type: MessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    @validator("payload")
    def validate_payload_size(cls, v):
        """Ensure payload is not too large."""
        import json

        size = len(json.dumps(v))
        if size > 1_048_576:  # 1MB limit
            raise ValueError("Payload too large (max 1MB)")
        return v


class TaskStatus(str, Enum):
    """Task lifecycle statuses."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(int, Enum):
    """Task priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class Task(BaseModel):
    """Task representation in the system."""

    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    role: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_to: Optional[AgentRole] = None
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_effort: Optional[int] = None  # story points or hours
    tags: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)  # Task-specific parameters

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

    def assign_to(self, agent_role: AgentRole):
        """Assign task to an agent."""
        self.assigned_to = agent_role
        self.assigned_at = datetime.utcnow()
        self.status = TaskStatus.ASSIGNED

    def mark_in_progress(self):
        """Mark task as in progress."""
        self.status = TaskStatus.IN_PROGRESS

    def mark_completed(self):
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def mark_failed(self):
        """Mark task as failed."""
        self.status = TaskStatus.FAILED


class Result(BaseModel):
    """Result representation for completed tasks."""

    task_id: str
    agent_role: AgentRole
    status: TaskStatus
    output: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[str] = Field(default_factory=list)  # file paths or URLs
    metrics: Dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SecurityFinding(BaseModel):
    """Security vulnerability finding."""

    severity: str  # critical, high, medium, low, info
    category: str  # e.g., 'hardcoded_secret', 'sql_injection', 'xss'
    file_path: str
    line_number: Optional[int] = None
    description: str
    recommendation: str
    cwe_id: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ApiSpec(BaseModel):
    """API specification for frontend-backend integration."""

    endpoint: str
    method: str  # GET, POST, PUT, DELETE, etc.
    description: str
    request_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    authentication_required: bool = False
    rate_limit: Optional[int] = None


class ProtocolConstants:
    """Protocol-level constants and default values."""

    MESSAGE_MAX_SIZE = 1_048_576  # 1MB
    HEARTBEAT_INTERVAL = 30  # seconds
    TASK_TIMEOUT = 3600  # 1 hour
    MAX_RETRIES = 3
    REDIS_CHANNEL_PREFIX = "wiggum:agentic:"

    # Role-specific configuration
    ROLE_CAPABILITIES = {
        AgentRole.SECURITY: [
            "vulnerability_scanning",
            "dependency_audit",
            "security_review",
            "compliance_check",
        ],
        AgentRole.SW_DEV: [
            "code_generation",
            "refactoring",
            "testing",
            "api_development",
        ],
        AgentRole.FRONTEND: [
            "ui_component_creation",
            "responsive_design",
            "accessibility_audit",
            "api_integration",
        ],
    }

    ROLE_DEPENDENCIES = {
        AgentRole.FRONTEND: [AgentRole.SW_DEV],
        AgentRole.SW_DEV: [],
        AgentRole.SECURITY: [],
    }

    # Message routing rules
    DIRECT_ROUTES = {
        AgentRole.SECURITY: [
            MessageType.SECURITY_ALERT,
            MessageType.SECURITY_SCAN_REQUEST,
        ],
        AgentRole.SW_DEV: [
            MessageType.CODE_REVIEW_REQUEST,
            MessageType.API_SPEC_REQUEST,
            MessageType.SECURITY_REPORT,
        ],
        AgentRole.FRONTEND: [
            MessageType.COMPONENT_READY,
            MessageType.API_SPEC_RESPONSE,
        ],
    }


def validate_message_schema(message: AgentMessage) -> bool:
    """Validate that a message conforms to protocol requirements."""
    # Check payload structure based on message type
    required_payload_fields = {
        MessageType.CODE_REVIEW_REQUEST: ["code", "language"],
        MessageType.API_SPEC_REQUEST: ["component_name", "requirements"],
        MessageType.SECURITY_ALERT: ["findings", "severity"],
        MessageType.TASK_UPDATE: ["task_id", "progress"],
        MessageType.COMPONENT_READY: ["component_name", "code", "dependencies"],
    }

    if message.message_type in required_payload_fields:
        for field in required_payload_fields[message.message_type]:
            if field not in message.payload:
                raise ValueError(
                    f"Missing required field '{field}' for message type "
                    f"{message.message_type.value}"
                )

    return True


def get_redis_channel(recipient: AgentRole, message_type: MessageType) -> str:
    """Generate Redis channel name for message routing."""
    return f"{ProtocolConstants.REDIS_CHANNEL_PREFIX}{recipient.value}/{message_type.value}"


def get_broadcast_channel() -> str:
    """Get the broadcast channel name."""
    return f"{ProtocolConstants.REDIS_CHANNEL_PREFIX}broadcast"

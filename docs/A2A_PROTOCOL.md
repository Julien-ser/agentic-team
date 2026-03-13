# A2A Protocol Specification

## 1. Overview

This document defines the Agent-to-Agent (A2A) communication protocol used in the Agentic Team system. All inter-agent communication follows this specification to ensure consistency, reliability, and interoperability.

The protocol defines:
- Message envelope structure
- Message types and their payload schemas
- Routing rules and channel naming
- Error handling and retry semantics
- Correlation and tracing

## 2. Message Envelope

Every message transmitted via the Redis broker follows this Pydantic schema defined in `src/protocols/agent_specs.py`:

```python
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum
import uuid

class AgentMessage(BaseModel):
    """
    Standard message envelope for all A2A communication.
    
    All fields are required unless marked optional.
    """
    sender: AgentRole                    # Role of sending agent
    recipient: AgentRole                 # Role of receiving agent
    message_type: MessageType            # Type of message (see section 3)
    payload: Dict[str, Any] = Field(default_factory=dict)  # Message body
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = Field(default=1, ge=1, le=10)  # 1=lowest, 10=highest
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    @validator("payload")
    def validate_payload_size(cls, v):
        """Enforce 1MB payload limit."""
        import json
        size = len(json.dumps(v))
        if size > 1_048_576:  # 1MB
            raise ValueError("Payload too large (max 1MB)")
        return v
```

### 2.1 Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sender` | `AgentRole` | Yes | Role of sending agent (e.g., "security", "software_developer") |
| `recipient` | `AgentRole` | Yes | Role of intended recipient (or "broadcast" for all) |
| `message_type` | `MessageType` | Yes | Type of message, determines required payload fields |
| `payload` | `dict` | No (default `{}`) | Message body with type-specific fields |
| `timestamp` | `datetime` | Auto | UTC timestamp when message was created |
| `correlation_id` | `str` (UUID4) | Auto | Unique ID for correlating request/response pairs |
| `priority` | `int [1-10]` | No (default 1) | Message priority; higher = delivered first |

### 2.2 Serialization

Messages are serialized to JSON for transmission over Redis:

```python
message = AgentMessage(
    sender=AgentRole.FRONTEND,
    recipient=AgentRole.SW_DEV,
    message_type=MessageType.API_SPEC_REQUEST,
    payload={"component_name": "LoginForm", "requirements": [...]}
)

# Serialize:
json_str = message.model_dump_json()

# Deserialize:
received = AgentMessage.model_validate_json(json_str)
```

All datetime fields are serialized as ISO 8601 strings (e.g., `"2024-01-15T10:30:45.123456"`).

### 2.3 Validation

Before publishing, messages are validated by `validate_message_schema()` in `src/protocols/agent_specs.py`:

```python
def validate_message_schema(message: AgentMessage) -> bool:
    """Validate payload structure based on message type."""
    required_payload_fields = {
        MessageType.CODE_REVIEW_REQUEST: ["code", "language"],
        MessageType.API_SPEC_REQUEST: ["component_name", "requirements"],
        MessageType.SECURITY_ALERT: ["findings", "severity"],
        MessageType.TASK_UPDATE: ["task_id", "progress"],
        MessageType.COMPONENT_READY: ["component_name", "code", "dependencies"],
        # ...
    }
    
    if message.message_type in required_payload_fields:
        for field in required_payload_fields[message.message_type]:
            if field not in message.payload:
                raise ValueError(
                    f"Missing required field '{field}' for {message.message_type.value}"
                )
    return True
```

Agents must call this validation before sending messages. The Message Router also validates incoming messages.

## 3. Message Types

The `MessageType` enum defines all valid message types:

### 3.1 Task Management Messages

#### `task.assignment`
**Direction**: System → Agent  
**Payload**:
```json
{
  "task_id": "string (UUID)",
  "description": "string",
  "priority": 1-4,
  "estimated_effort": "integer (story points)",
  "tags": ["array of strings"],
  "acceptance_criteria": ["array of strings"]
}
```
**Use**: System assigns a task to an agent via wiggum loop.

---

#### `task.update`
**Direction**: Agent → System  
**Payload**:
```json
{
  "task_id": "string (UUID)",
  "status": "in_progress|blocked|completed|failed",
  "progress": 0-100,
  "message": "string (optional progress note)",
  "estimated_completion": "ISO8601 datetime (optional)"
}
```
**Use**: Agent reports task progress.

---

#### `task.complete`
**Direction**: Agent → System  
**Payload**:
```json
{
  "task_id": "string (UUID)",
  "output": {
    "artifact_urls": ["array of file paths or URLs"],
    "summary": "string",
    "test_results": {"passed": 10, "failed": 0}  (optional)
  },
  "metrics": {
    "time_seconds": 45.2,
    "tokens_used": 1234,
    "lines_of_code": 150
  },
  "warnings": ["array of warning strings (optional)"]
}
```
**Use**: Agent signals successful task completion with artifacts.

---

#### `task.failed`
**Direction**: Agent → System  
**Payload**:
```json
{
  "task_id": "string (UUID)",
  "error": "string (error message)",
  "stack_trace": "string (optional)",
  "retry_count": 0-3,
  "can_retry": true/false,
  "blocking_issue": "string (if another agent must resolve)"
}
```
**Use**: Agent reports task failure with diagnostic info.

---

### 3.2 Code Review & Integration Messages

#### `code.review.request`
**Direction**: Any Agent → Developer Agent  
**Payload**:
```json
{
  "code": "string (full source code)",
  "language": "python|javascript|typescript|html|css",
  "context": "string (what this code is for)",
  "review_aspects": ["array: security, performance, style, testing"],
  "deadline": "ISO8601 datetime (optional)"
}
```
**Use**: Request code review or refactoring from Developer Agent.

---

#### `code.review.response`
**Direction**: Developer Agent → Requesting Agent  
**Payload**:
```json
{
  "original_code_hash": "sha256 hash of input code",
  "refactored_code": "string (improved code)",
  "changes": [
    {
      "type": "security_fix|performance_improvement|style|test_added",
      "description": "string",
      "severity": "critical|high|medium|low"
    }
  ],
  "explanation": "string (summary of improvements)",
  "metrics": {
    "cyclomatic_complexity_before": 15,
    "cyclomatic_complexity_after": 12,
    "lines_added": 5,
    "lines_removed": 12
  }
}
```
**Use**: Return reviewed/refactored code with change log.

---

#### `api.contract.update`
**Direction**: Developer Agent → Frontend Agent  
**Payload**:
```json
{
  "api_spec": {
    "endpoint": "/api/v1/auth/login",
    "method": "POST",
    "description": "Authenticate user and return JWT token",
    "request_schema": {"type": "object", "properties": {...}},
    "response_schema": {"type": "object", "properties": {...}},
    "authentication_required": false,
    "rate_limit": 5
  },
  "version": "1.0",
  "deprecated": false,
  "breaking_changes": ["list of changes from previous version"]
}
```
**Use**: Publish or update API specification for frontend consumption.

---

#### `component.ready`
**Direction**: Frontend Agent → Developer Agent  
**Payload**:
```json
{
  "component_name": "LoginForm",
  "code": "<!DOCTYPE html>... (full HTML/CSS/JS code)",
  "dependencies": ["Tailwind CSS via CDN"],
  "accessibility_score": 95,
  "responsive_breakpoints": ["mobile", "tablet", "desktop"],
  "api_contracts_used": [
    {
      "endpoint": "/api/v1/auth/login",
      "integration_points": ["form submit handler"]
    }
  ],
  "artifacts": ["/artifacts/login_form.zip"]  (optional file references)
}
```
**Use**: Frontend sends completed UI component for backend integration.

---

### 3.3 Security Messages

#### `security.alert`
**Direction**: Security Agent → Any Agent  
**Payload**:
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "hardcoded_secret|sql_injection|xss|csrf|dos|cwe-XXX",
  "findings": [
    {
      "file_path": "string",
      "line_number": 42,
      "description": "string",
      "recommendation": "string",
      "cwe_id": "CWE-798",
      "confidence": 0.0-1.0,
      "code_snippet": "the vulnerable code line"
    }
  ],
  "summary": "Overall assessment message",
  "scan_timestamp": "ISO8601 datetime"
}
```
**Use**: Report security vulnerabilities found in code or dependencies.

---

#### `security.scan.request`
**Direction**: Any Agent → Security Agent  
**Payload**:
```json
{
  "code_path": "/path/to/file.py",
  "scan_type": "quick|comprehensive|compliance",
  "context": "string (what the code does)",
  "deadline": "ISO8601 datetime (optional)",
  "languages": ["python", "javascript"]  (optional, default from file extension)
}
```
**Use**: Request security scan of code.

---

#### `security.scan.response`
**Direction**: Security Agent → Requesting Agent  
**Payload**:
```json
{
  "scan_id": "uuid",
  "files_scanned": 5,
  "total_vulnerabilities": 3,
  "findings": [...],  // Same structure as security.alert findings array
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 0,
    "info": 0
  },
  "recommendations": [
    "Fix HIGH severity finding on line 42 (hardcoded secret)",
    "Review MEDIUM finding on line 89 (SQL injection risk)"
  ],
  "scan_duration_seconds": 12.5
}
```
**Use**: Return complete security scan results.

---

#### `security.report`
**Direction**: Security Agent → System/Dashboard  
**Payload**:
```json
{
  "report_type": "daily|weekly|privacy|compliance",
  "period": {
    "start": "ISO8601 datetime",
    "end": "ISO8601 datetime"
  },
  "metrics": {
    "scans_performed": 15,
    "vulnerabilities_found": 23,
    "mean_time_to_remediate": "PT2H30M"  // ISO 8601 duration
  },
  "top_findings": [
    {"category": "hardcoded_secret", "count": 10},
    {"category": "sql_injection", "count": 5}
  ],
  "compliance_status": {
    "pci_dss": "compliant",
    "owasp_top_10": "partial"
  }
}
```
**Use**: Periodic security reporting to management.

---

### 3.4 Coordination & System Messages

#### `heartbeat`
**Direction**: Agent → System (broadcast on `agent.{role}.heartbeat`)  
**Payload**:
```json
{
  "agent_id": "frontend-01",
  "status": "healthy|degraded|offline",
  "current_task_id": "task-uuid-if-any",
  "uptime_seconds": 3600,
  "memory_usage_mb": 128.5,
  "tasks_completed_session": 12
}
```
**Use**: Liveness detection and health monitoring. Sent every 30 seconds.

---

#### `health.check`
**Direction**: System/Dashboard → Agent (or Agent → Agent)  
**Payload**:
```json
{
  "check_id": "uuid (for response correlation)",
  "requested_at": "ISO8601 datetime"
}
```
**Use**: Explicit health check request. Agent should respond with `health.response`.

---

#### `health.response`
**Direction**: Agent → System/Dashboard (in response to `health.check`)  
**Payload**:
```json
{
  "check_id": "uuid (from request)",
  "responded_at": "ISO8601 datetime",
  "status": "healthy|degraded|unhealthy",
  "metrics": {
    "response_time_ms": 5,
    "memory_usage_mb": 128.5,
    "cpu_percent": 2.3,
    "database_connections": 5
  },
  "errors": []  // any recent errors
}
```
**Use**: Response to health check query.

---

#### `dependency.update`
**Direction**: Developer Agent → Frontend Agent (or vice versa)  
**Payload**:
```json
{
  "component_name": "LoginForm",
  "dependencies": [
    {
      "name": "auth-api",
      "version": "v1.2.0",
      "location": "https://api.example.com/v1",
      "status": "ready|deprecated|broken",
      "updated_at": "ISO8601 datetime"
    }
  ],
  "notification": "string (human-readable summary)"
}
```
**Use**: Notify dependent agent about dependency changes.

---

#### `shared_knowledge.update`
**Direction**: Any Agent → System (indirect via StateManager)  
**Payload**:
```json
{
  "key": "string (knowledge store key)",
  "value": "any JSON-serializable value",
  "source_agent": "sender role",
  "ttl_seconds": 3600,  // optional, default no expiry
  "description": "string (human-readable, optional)"
}
```
**Use**: Store/update shared knowledge artifact (API spec, code snippet, config).

---

#### `broadcast`
**Direction**: System → All Agents  
**Payload**:
```json
{
  "message": "string (announcement text)",
  "type": "info|warning|maintenance|shutdown",
  "scheduled_for": "ISO8601 datetime (if maintenance)",
  "duration_minutes": 30  // if maintenance
}
```
**Use**: System-wide announcements (e.g., "Maintenance in 5 minutes").

---

## 4. Message Routing

### 4.1 Channel Naming Convention

Messages are routed through Redis channels named using this pattern:

```
{prefix}{recipient}/{message_type}
```

Where:
- `{prefix}` = `"wiggum:agentic:"` (configurable via `REDIS_CHANNEL_PREFIX`)
- `{recipient}` = Agent role value (e.g., `"software_developer"`, `"security"`)
- `{message_type}` = Message type with slashes (e.g., `"security.alert"`, `"api.spec.request"`)

**Examples**:
- `wiggum:agentic:security/security.alert` → Security agent receives security alerts
- `wiggum:agentic:software_developer/api.spec.request` → Dev agent receives API spec requests
- `wiggum:agentic:frontend_developer/component.ready` → Frontend agent receives components

### 4.2 Direct Routing

Most messages use **direct routing**: sender specifies recipient role, and the broker publishes to that recipient's channel.

**Flow**:
1. Agent A calls `broker.publish(AgentMessage(recipient=AgentRole.B, ...))`
2. Broker computes channel: `{prefix}B/{message_type}`
3. Message published to that channel
4. Agent B (subscribed to `{prefix}B/*`) receives all messages addressed to it

### 4.3 Broadcast Routing

For system-wide messages, use broadcast channel:

```
{prefix}broadcast
```

All agents should subscribe to this channel in addition to their own direct channels.

**Example**: System shutdown notification:
```python
msg = AgentMessage(
    sender=AgentRole.SYSTEM,
    recipient=AgentRole.BROADCAST,
    message_type=MessageType.BROADCAST,
    payload={"message": "Shutting down in 60 seconds", "type": "maintenance"}
)
```

### 4.4 Message Router

The `MessageRouter` class (`src/messaging/router.py`) handles:

- **Validation**: Ensures messages conform to schema before routing
- **Logging**: Persists all messages to SQLite `messages` table
- **Queueing**: If recipient is offline, message is queued for later delivery (in-memory)
- **Broadcast**: Expands broadcast to all known agents
- **Correlation**: Tracks correlation IDs for request/response matching

### 4.5 Routing Rules

The router enforces these rules (configurable):

| Rule | Description | Enforcement |
|------|-------------|-------------|
| **Sender Authorization** | Agent can only send as its own role | Verified by broker; rejects if `sender != agent.role` |
| **Recipient Existence** | Recipient must be known agent role | Accepts `AgentRole` enum values + `broadcast` |
| **Payload Validation** | Payload must match message type schema | Raises `ValidationError` if invalid |
| **Size Limit** | Message ≤ 1MB | Enforced by Pydantic validator |
| **Priority Range** | Priority 1-10 inclusive | Enforced by Pydantic validator |

**Route Decision**:
```python
def route_message(message: AgentMessage) -> str:
    if message.recipient == AgentRole.BROADCAST:
        return f"{config.REDIS_CHANNEL_PREFIX}broadcast"
    else:
        return f"{config.REDIS_CHANNEL_PREFIX}{message.recipient.value}/{message.message_type.value}"
```

## 5. Error Handling

### 5.1 Message-Level Errors

When a message fails validation or processing:

1. **Sender Validation Error** (Pydantic raises before sending):
   ```python
   try:
       validate_message_schema(message)
   except ValueError as e:
       logger.error(f"Invalid message: {e}")
       # Don't send; fix the bug
   ```

2. **Broker/Redis Error** (connection failure):
   ```python
   try:
       await broker.publish(message)
   except RedisConnectionError:
       # Queue locally for retry
       await local_queue.put(message)
       await reconnect_with_backoff()
   ```

3. **Recipient Processing Error** (agent crashes or malformed):
   - Message is ACK'd by Redis (removed from queue) regardless
   - Exception logged to agent's error log
   - System may send `task.failed` if message was task-related
   - No automatic retry (at-least-once delivery, not exactly-once)

### 5.2 Retry Semantics

**Retryable errors** (apply to transient failures):
- Redis connection loss: exponential backoff (1s, 2s, 4s, 8s, 16s, then give up after 5 attempts)
- Database connection pool exhausted: wait and retry after 100ms
- HTTP timeout to OpenRouter: retry with jitter up to 3 attempts

**Non-retryable errors** (log and escalate):
- Message validation failure (bug in sender)
- Authentication/authorization failure
- Payload too large
- Unsupported message type

### 5.3 Dead Letter Queue (Planned)

Currently, failed messages are simply logged. Future enhancement: dead letter queue (DLQ) for manual inspection:

```
{prefix}dlq  (Redis list)
```

Messages moved to DLQ after max retries. Operators can inspect and reprocess.

### 5.4 Error Message Pattern

When agent cannot process a message due to error, it should:

1. Log the error with full context (message ID, correlation ID, payload)
2. Optionally send `task.failed` if task-related
3. Update agent health status if error is systemic
4. Continue processing next message (don't crash)

**Do NOT**:
- Retry indefinitely (causes cascade failures)
- Crash the agent process (keep alive to handle other messages)
- Swallow errors silently (always log)

## 6. Correlation and Tracing

### 6.1 Correlation ID

Every message gets a unique `correlation_id` (UUID4) upon creation. This ID is preserved across message chains:

```
Frontend → Dev:  api.spec.request (corr=abc123)
Dev → Frontend:  api.spec.response (corr=abc123)  ← same correlation ID
```

**Usage**:
- Link request and response messages
- Trace complete workflow across multiple hops
- Debug message routing issues
- Reconstruct conversation history

### 6.2 Trace Context (Future)

Planned enhancement: Distributed tracing with OpenTelemetry.

Each message would carry:
```json
{
  "trace_id": "uuid (root span)",
  "span_id": "uuid (current span)",
  "parent_span_id": "uuid (if any)",
  "sampling_decision": "always|never|rate-limited"
}
```

This would enable full end-to-end latency analysis.

## 7. Message Priority

Messages have `priority` field (1-10, default 1). The broker **does not currently prioritize**—all messages delivered FIFO per channel.

**Future enhancement**: Priority queues using Redis sorted sets.

**Current interpretation**: Priority field is informational only; agents can use it to decide which messages to process first if multiple arrive in same inbox.

**Best practice**:
- Priority 1-3: Normal workflow messages (component.ready, api.spec.request)
- Priority 4-6: Urgent responses (security.alert, task.update)
- Priority 7-10: System paging (maintenance alerts, critical failures)

## 8. Security Considerations

### 8.1 Message Integrity

Currently, **no cryptographic signatures**. All messages trusted based on Redis authentication (single-tenant deployment).

**Future**: Add HMAC signature:

```python
# On send:
signature = hmac_sha256(shared_secret, f"{timestamp}{payload}")
message.signature = signature

# On receive:
expected = hmac_sha256(shared_secret, f"{message.timestamp}{message.payload}")
if not hmac_compare(signature, expected):
    raise SecurityError("Message signature invalid")
```

### 8.2 Confidentiality

Redis traffic is plaintext by default. In production:
- Use `rediss://` (TLS) for Redis connections
- Enable Redis AUTH with strong password
- Consider message payload encryption for highly sensitive data (e.g., credentials in code)

### 8.3 Authorization

Agents should verify:
1. Sender role is appropriate for message type (e.g., only Security can send `security.alert`)
2. Sender is authorized to perform action (optional, based on business logic)

Currently, **no sender verification beyond Redis connection** (trusted network assumed).

### 8.4 Input Validation

All payloads validated via Pydantic schemas **before processing** to prevent:
- Malformed JSON causing crashes
- Injection attacks (SQL, command injection)
- Type confusion bugs

**Defense in depth**: Also validate at database boundary with parameterized queries.

## 9. Performance Guidelines

### 9.1 Message Size

**Keep payloads small** (< 10KB ideal). Avoid sending:
- Full source code repositories (send file paths or git SHAs)
- Large binary files (store in shared filesystem, send URL)
- Redundant data (use shared knowledge cache instead)

**If must send large data**:
- Compress with gzip (ancestors to 10% of original)
- Split into chunks with sequence numbers
- Consider out-of-band transfer (shared storage, S3)
- Include checksum for integrity verification

### 9.2 Message Rate

**Expected rates**:
- Normal operation: 1-10 messages/sec total
- Peak (all agents collaborating): 50-100 messages/sec

**Bottleneck**: Database writes for message persistence. Batch inserts if > 100 msg/sec.

**Recommendation**: Aggregate metrics and send batched updates (e.g., send 10 message summary every 5 seconds vs. 10 individual messages).

### 9.3 Latency

**Target**: < 100ms end-to-end for request/response patterns.

**Components**:
- Redis pub/sub: < 1ms (local) or < 10ms (networked)
- Agent processing: 10-500ms (depends on AI API call)
- Database write: 5-20ms

**Realistic total**: 50-500ms for most messages. AI-based messages (code generation) will be seconds.

## 10. Protocol Evolution

### 10.1 Versioning Strategy

**Current version**: 1.0

**Backward compatibility**:
- New fields may be added to payloads (agents should ignore unknown fields)
- Required fields may NOT be removed (only marked optional)
- Message types may NOT be reused for different purposes
- If breaking change needed (e.g., changing field types), create new message type:
  - `api.spec.request.v2`
  - Keep old type for legacy agents

**Version negotiation**: Not yet implemented. All agents must run same protocol version.

### 10.2 Deprecation Policy

When deprecating message type or field:
1. Announce via `broadcast` message with 30-day notice
2. Mark in schema with `deprecated=True` in docstring
3. Remove in next major version after grace period
4. Support both old and new for 1-2 releases

### 10.3 Change Management

Proposed changes should:
1. Update this specification document (A2A_PROTOCOL.md)
2. Update `src/protocols/agent_specs.py` Pydantic models
3. Update agent implementations to handle new message types
4. Add integration tests demonstrating new functionality
5. Update this changelog:

```
## v1.1 (YYYY-MM-DD)
- Added security.report message type for periodic reporting
- Added TTL support for shared_knowledge.update
- Changed task.update payload: added 'estimated_completion' field

## v1.0 (YYYY-MM-DD)
- Initial protocol specification
```

## 11. Implementation Checklist for Agents

Every agent implementation **must**:

- [ ] Subscribe to direct inbox: `{prefix}{agent.role.value}/*`
- [ ] Subscribe to broadcast channel: `{prefix}broadcast`
- [ ] Validate all incoming messages with `validate_message_schema()`
- [ ] Log message receipt with correlation_id
- [ ] Send heartbeat every 30 seconds (configurable)
- [ ] Use async/await for all broker operations
- [ ] Handle Redis connection loss with exponential backoff
- [ ] Persist all sent/received messages via `StateManager.store_message()`
- [ ] Respond to `health.check` with `health.response`
- [ ] Set `sender=agent.role` on all outgoing messages
- [ ] Include `correlation_id` when responding to requests
- [ ] Observe payload size limit (1MB)
- [ ] Gracefully handle unknown message types (log and ignore)

## 12. Testing Protocol Compliance

### 12.1 Unit Tests

Each agent should have tests for:
- Sending each supported message type
- Handling each received message type
- Validation errors (missing required fields, invalid types)
- Priority handling
- Correlation ID propagation

Example test (pytest):
```python
@pytest.mark.asyncio
async def test_security_agent_handles_scan_request(security_agent, mock_redis):
    msg = AgentMessage(
        sender=AgentRole.SW_DEV,
        recipient=AgentRole.SECURITY,
        message_type=MessageType.SECURITY_SCAN_REQUEST,
        payload={"code_path": "/tmp/test.py", "scan_type": "quick"}
    )
    
    await security_agent.receive_message(msg)
    
    # Expect response
    response = await mock_redis.get_published_message()
    assert response.message_type == MessageType.SECURITY_SCAN_RESPONSE
    assert response.correlation_id == msg.correlation_id
```

### 12.2 Integration Tests

The `test_collaborative_workflow.py` tests full message chains:
- Frontend → Dev: API spec request/response
- Dev → Frontend: Component ready notification
- Dev → Security: Scan request/response
- All messages: Persisted to database

### 12.3 Protocol Conformance

Run this script to verify agent compliance:

```bash
python -m tests.protocol_conformance --agent=frontend
```

It checks:
- All required subscriptions exist
- All required message types handled
- Schema validation before sending
- Heartbeat interval correct
- Correlation ID usage

## 13. Common Pitfalls

### 13.1 Deadlock

**Problem**: Two agents waiting for each other's responses (circular dependency).

**Example**: Frontend waiting for API spec, Dev waiting for component, Security waiting for code.

**Solution**: Add timeout and `task.failed` with `blocking_issue` field. Wiggum loop can reassign blocked tasks.

---

### 13.2 Message Storm

**Problem**: Agent A sends 1000 messages to Agent B in loop (DoS).

**Solution**: Current: None (trusting agents). Future: Rate limiting per sender at broker level (tokens per minute).

---

### 13.3 Correlation ID Loss

**Problem**: Agent forgets to propagate `correlation_id` when responding, making tracing impossible.

**Solution**: Enforce in `send_message()` wrapper:
```python
async def send_message(self, recipient, message_type, payload, correlation_id=None, **kwargs):
    if correlation_id is None:
        # Should we raise error or generate new? Current: generate new
        correlation_id = str(uuid.uuid4())
    msg = AgentMessage(
        sender=self.role,
        recipient=recipient,
        message_type=message_type,
        payload=payload,
        correlation_id=correlation_id,
        **kwargs
    )
    # ...
```

---

### 13.4 Large Payloads

**Problem**: Sending 5MB source code in single message exceeds 1MB limit.

**Solution**: Store code in shared knowledge, send reference:
```json
{
  "code_reference": "shared_knowledge:login_component_v1",
  "metadata": {"size_bytes": 987654, "language": "html"}
}
```
Then recipient retrieves via `StateManager.get_shared_knowledge()`.

---

### 13.5 Clock Skew

**Problem**: Agent A's clock ahead of Agent B's; timestamps appear out of order.

**Solution**: Use UTC everywhere. Accept up to 5 seconds skew. For ordering, rely on insertion order in database, not timestamps.

---

## 14. Appendix: Message Type Index

| Message Type | Direction | Priority | Required Payload Fields |
|--------------|-----------|----------|------------------------|
| `task.assignment` | System → Agent | 3 | `task_id`, `description` |
| `task.update` | Agent → System | 5 | `task_id`, `status` |
| `task.complete` | Agent → System | 4 | `task_id`, `output` |
| `task.failed` | Agent → System | 6 | `task_id`, `error` |
| `code.review.request` | Any → Dev | 2 | `code`, `language` |
| `code.review.response` | Dev → Any | 2 | `original_code_hash`, `refactored_code` |
| `api.spec.request` | Frontend → Dev | 2 | `component_name`, `requirements` |
| `api.spec.response` | Dev → Frontend | 2 | `api_spec` |
| `component.ready` | Frontend → Dev | 3 | `component_name`, `code` |
| `security.alert` | Security → Any | 8 | `findings`, `severity` |
| `security.scan.request` | Any → Security | 4 | `code_path`, `scan_type` |
| `security.scan.response` | Security → Any | 4 | `scan_id`, `findings` |
| `security.report` | Security → System | 6 | `report_type`, `period` |
| `heartbeat` | Agent → Broadcast | 1 | `agent_id`, `status` |
| `health.check` | Any → Agent | 3 | `check_id` |
| `health.response` | Agent → Any | 3 | `check_id`, `status` |
| `dependency.update` | Dev/FE → Peer | 4 | `component_name`, `dependencies` |
| `shared_knowledge.update` | Any → System | 5 | `key`, `value` |
| `broadcast` | System → All | 9 | `message`, `type` |

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15  
**Conformance Level**: Agents must implement 100% of specified message types relevant to their role, plus `heartbeat` and `health.check/response`.

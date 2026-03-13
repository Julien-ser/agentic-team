# System Design Document

## 1. Executive Summary

The Agentic Team System is an autonomous multi-agent development platform built on the wiggum loop concept. Three specialized agents (Security, Software Developer, Frontend) collaborate via Agent-to-Agent (A2A) communication to complete development tasks without human intervention.

**Key Characteristics:**
- Role-based task assignment with clear capability boundaries
- Asynchronous message-driven architecture using Redis pub/sub
- Shared persistent state via SQLite for coordination and audit trail
- Real-time monitoring via Flask dashboard
- Extensible design allowing new agent roles to be added with minimal changes

## 2. Design Principles

### 2.1 Separation of Concerns

Each agent has a well-defined, non-overlapping responsibility:
- **Security Agent**: All security-related tasks (vulnerability scanning, CVE checking, compliance)
- **Software Dev Agent**: Backend code generation, testing, and refactoring
- **Frontend Agent**: UI/UX component creation and API integration

This separation prevents role confusion and enables independent scaling and evolution.

### 2.2 Message-Driven Communication

Agents never call each other directly. All communication goes through the Redis message broker, providing:
- **Decoupling**: Agents don't need to know about each other's existence or availability
- **Queuing**: Messages persist until recipient is ready to process them
- **Observability**: All messages are logged and can be inspected
- **Broadcast**: One-to-many communication for system-wide announcements

### 2.3 Immutable Message Log

All A2A messages are persisted to SQLite with timestamps, creating an immutable audit trail. This enables:
- Debugging and forensic analysis
- Replay of system behavior for testing
- Historical performance analysis
- Compliance verification

### 2.4 Shared Knowledge Store

A key-value store allows agents to share artifacts and context:
- API specifications
- Generated code artifacts
- Configuration data
- Computed results (to avoid redundant work)

### 2.5 Autonomous Operation

The wiggum loop continuously:
1. Parses human-written tasks from TASKS.md
2. Dispatches tasks to appropriate agents based on role tags
3. Monitors agent health automatically
4. Restarts failed agents without intervention
5. Tracks iteration cycles and performance metrics

No human operator is required once the system is started.

## 3. Technology Choices and Rationale

### 3.1 Python 3.12+ with asyncio

**Decision**: Use Python 3.12+ with native asyncio for concurrent agent execution.

**Rationale**:
- Mature async ecosystem with excellent library support (aiohttp, aioredis)
- High developer productivity and readability
- Strong typing with mypy integration
- Rich standard library for file I/O, json, etc.
- Natural fit for event-driven agent loops
- No GIL contention for I/O-bound operations

**Alternatives Considered**:
- **Go**: Excellent concurrency but smaller AI/ML library ecosystem
- **Rust**: Maximum performance but steep learning curve and slower development
- **Node.js**: Good I/O but weaker typing and less suited for CPU-bound code generation

### 3.2 Redis Pub/Sub

**Decision**: Use Redis pub/sub for A2A message broker.

**Rationale**:
- Lightning-fast in-memory message delivery (< 1ms latency)
- Built-in pub/sub pattern with channel-based routing
- Persistence options (RDB/AOF) for message durability
- Simple deployment and maintenance
- Redis Streams available if we need message queues with consumer groups
- Wide language support if we add non-Python agents later

**Alternatives Considered**:
- **RabbitMQ**: More features but heavier operational overhead
- **Apache Kafka**: Overkill for single-machine deployment, complex setup
- **ZeroMQ**: No built-in persistence, requires custom broker implementation
- **PostgreSQL LISTEN/NOTIFY**: Slower, limited message size, database coupling

### 3.3 SQLite for Shared State

**Decision**: Use SQLite for state persistence.

**Rationale**:
- Zero-configuration, file-based database
- ACID transactions with row-level locking
- Adequate performance for < 100 agents
- No external service required (respects "no venv/Docker if unnecessary" guideline)
- Easy backups (just copy the file)
- Portable across platforms
- Can migrate to PostgreSQL later if needed (via SQLAlchemy)

**Alternatives Considered**:
- **PostgreSQL**: Overkill for single-machine setup, requires separate service
- **MySQL**: Same as PostgreSQL
- **Redis hashes**: No query capabilities, data loss on restart without persistence
- **JSON files**: No concurrency control, no query capabilities

### 3.4 Flask for Dashboard

**Decision**: Use Flask for the web monitoring interface.

**Rationale**:
- Minimal dependencies, lightweight
- Easy to integrate with existing Python codebase
- Sufficient for our dashboard needs (no complex SPA required)
- Fast to develop and iterate
- Server-Sent Events (SSE) support for real-time updates
- Can add React/Vue later if needed

**Alternatives Considered**:
- **FastAPI**: More modern but slightly more complex, would be great for API-heavy dashboards
- **Django**: Overkill, too much boilerplate
- **Streamlit**: Limited customization, would force specific UI patterns

### 3.5 Pydantic for Data Validation

**Decision**: Use Pydantic v2 for all data schemas and validation.

**Rationale**:
- Type-safe data structures with runtime validation
- Automatic JSON (de)serialization
- Clear error messages for debugging
- Integration with FastAPI/Flask for request validation
- Great for message schema definitions
- Encourages immutability with model config

## 4. Architectural Patterns

### 4.1 Wiggum Loop Pattern

The system implements an enhanced wiggum loop that:
1. **Parse**: Read TASKS.md and extract role-tagged tasks
2. **Dispatch**: Assign tasks to appropriate agents using round-robin or priority
3. **Monitor**: Track agent health, heartbeats, performance metrics
4. **Iterate**: Continue cycling until all tasks are complete
5. **Report**: Log metrics and update dashboard

The loop runs continuously, allowing agents to work autonomously without human intervention.

### 4.2 Actor Model (Lightweight)

Each agent functions as an independent actor:
- Own state (in agent_states table)
- Own message inbox (Redis channel)
- Processes messages sequentially (async/await ensures one at a time)
- Communicates only via messages (no shared memory)

This prevents race conditions and simplifies reasoning about agent behavior.

### 4.3 Repository Pattern

StateManager acts as a repository for:
- Tasks (CRUD operations with atomic locking)
- Messages (append-only log)
- Agent states (with heartbeat tracking)
- Shared knowledge (key-value store)

This abstracts database logic from agents and enables easy testing with mocks.

### 4.4 Strategy Pattern for Task Dispatch

The TaskDispatcher can use different dispatch strategies:
- **Round-robin**: Distribute tasks evenly among agents of same role
- **Priority-based**: Assign high-priority tasks first
- **Least-loaded**: Assign to agent with fewest pending tasks

Strategy can be swapped without affecting agents.

### 4.5 Observer Pattern for Monitoring

Dashboard subscribes to system metrics via:
- Direct database queries (tasks, messages tables)
- Agent heartbeat polling
- Statistics calculations on-demand

Agents don't need to know about the dashboard's existence.

## 5. Scalability and Extensibility

### 5.1 Horizontal Scaling

Multiple agents of the same role can run concurrently:
- Redis pub/sub naturally supports multiple subscribers on same channel
- StateManager uses atomic `SELECT ... FOR UPDATE` to prevent duplicate task assignment
- Load is distributed automatically as agents compete for tasks

To scale:
```bash
# Start multiple frontend agents
python -m src.agents.frontend_agent --agent-id=frontend-01 &
python -m src.agents.frontend_agent --agent-id=frontend-02 &
python -m src.agents.frontend_agent --agent-id=frontend-03 &
```

All will compete for `[FRONTEND]` tasks from TASKS.md.

### 5.2 Adding New Agent Roles

To add a new role (e.g., "DevOps"):

1. Add to `AgentRole` enum in `src/protocols/agent_specs.py`:
   ```python
   DEVOPS = "devops"
   ```

2. Create `src/agents/devops_agent.py`:
   ```python
   class DevOpsAgent(BaseAgent):
       role = AgentRole.DEVOPS
       # Implement required methods
   ```

3. Add role tag parsing in wiggum loop (`src/core/wiggum_loop.py`):
   ```python
   ROLE_TAGS = {
       '[DEVOPS]': AgentRole.DEVOPS,
       # existing mappings...
   }
   ```

4. Update `ProtocolConstants.ROLE_CAPABILITIES` with new capabilities.

No other system changes needed—the architecture is designed for extensibility.

### 5.3 Multi-Machine Deployment

For production deployments across multiple machines:

1. **Redis**: Deploy Redis on dedicated server or use managed service (ElastiCache, etc.)
2. **SQLite → PostgreSQL**: Replace SQLite with PostgreSQL for better concurrent access across machines
   - Swap `src/state/state_manager.py` to use `asyncpg` instead of `sqlite3`
   - Database schema remains identical
3. **Agent Configuration**: Set unique `AGENT_ID` per machine via environment variable
4. **Network**: Ensure all machines can reach Redis and database

### 5.4 Protocol Evolution

The message protocol is designed for backward compatibility:

- New message types can be added without breaking existing agents
- Unknown message types can be safely ignored by agents (they won't understand them)
- Required payload fields can be made optional in future versions
- Protocol version can be added to `AgentMessage` if breaking changes are needed

## 6. Performance Considerations

### 6.1 Message Throughput

**Expected throughput**: 10-100 messages/second with single Redis instance.

**Bottlenecks**:
- Redis pub/sub: Can handle 100k+ messages/sec, not a bottleneck
- Database I/O: SQLite can handle ~50k writes/sec on SSD, may become bottleneck at scale
- Agent processing: Limited by AI API rate limits (OpenRouter)

**Optimizations**:
- Batch database writes (INSERT multiple messages in one transaction)
- Use Redis pipelining for bulk publishes
- Compress large payloads (> 10KB) with gzip before storing in DB

### 6.2 Memory Usage

Each agent holds:
- OpenRouter API client connection (~50MB)
- StateManager connection pool (~10MB)
- In-memory cache of recent messages (~5MB per agent)

**Total per agent**: ~100MB

With 10 agents: ~1GB RAM sufficient.

### 6.3 Concurrency Model

- **I/O operations**: Fully async (Redis, database, HTTP calls)
- **CPU-bound**: AI calls are remote; local processing minimal
- **Locking**: Database row-level locks during task assignment; < 10ms duration
- **Thread safety**: All code runs in single thread per agent (async event loop)

No mutexes or semaphores required—asyncio provides cooperative multitasking.

## 7. Fault Tolerance and Resilience

### 7.1 Agent Failures

**Detection**: Heartbeat updates every 30 seconds (configurable). Missing 2 consecutive heartbeats = agent marked unhealthy.

**Recovery**: WorkerManager automatically restarts crashed agents with exponential backoff:
- First restart: immediate
- Second restart: 5 seconds
- Third restart: 15 seconds
- Subsequent: 30 seconds (max)

**Logging**: All failures logged to file and reflected in dashboard.

### 7.2 Message Delivery Guarantees

**Best-effort delivery**: 
- Messages published to Redis with `retry=3` on connection loss
- If Redis is down, messages are queued in memory (max 1000 per agent) and sent on reconnect
- No durable message queue (messages in Redis can be lost on restart unless AOF enabled)

**For critical messages**: Use acknowledgment pattern:
1. Sender includes `ack_requested: true` in payload
2. Recipient must send acknowledgment within timeout
3. Sender retries if no ack received (configurable attempts)

**Future enhancement**: Switch to Redis Streams for guaranteed delivery with consumer groups.

### 7.3 Database Corruption

**Backup**: Automated daily backup at 2 AM (can be configured):
```bash
# In src/state/backup.py
sqlite3 agentic_team.db ".backup 'backup/agentic_team_$(date +%Y%m%d).db'"
```

**Recovery**: Restore from most recent backup. Lost messages from last 24 hours acceptable tradeoff for simplicity.

**Prevention**: Use write-ahead logging (WAL mode):
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

### 7.4 Redis Outages

**Handling**: 
- Agents enter "degraded" mode, queue messages locally
- Retry connection every 5 seconds with exponential backoff
- Dashboard shows "Redis Disconnected" warning

**Recovery**: When Redis returns, queued messages flushed to channels.

**Design decision**: No local message persistence beyond memory queue. If Redis is down for > 1 hour, agents continue working but cannot communicate. Operator must intervene.

## 8. Security Model

### 8.1 Threat Model

**Assets to protect**:
- A2A messages (may contain code, credentials)
- Shared knowledge (API specs, generated artifacts)
- Database (audit trail, task definitions)
- Agent identity (prevent impersonation)

**Threats**:
1. **Eavesdropping**: Unencrypted Redis traffic accessible to local attackers
2. **Impersonation**: Malicious agent claiming to be legitimate agent
3. **Tampering**: Attacker modifying messages in transit or at rest
4. **Denial of Service**: Flooding agents with messages, exhausting resources
5. **Code Execution**: AI-generated code may contain vulnerabilities or malware

### 8.2 Security Controls

**Current (Development Stage)**:
- Local deployment only (localhost Redis, local SQLite)
- No encryption (acceptable for dev environment)
- Basic message validation via Pydantic schemas
- Payload size limits (1MB max)
- SQLite parameterized queries prevent injection

**Planned for Production**:
- Redis TLS encryption (`rediss://`)
- Redis AUTH password (strong, unique)
- Agent authentication via JWT tokens in message headers
- Message signing (HMAC) to detect tampering
- Rate limiting on Redis connections (per agent)
- Code sandboxing before execution (Docker containers)
- Secret scanning in generated code (Security Agent already does this)
- File system permissions: agents run under dedicated user accounts
- Audit logging of all security events

### 8.3 Secrets Management

**Never store secrets in code or configuration files**:
- Use environment variables for API keys (OPENROUTER_API_KEY)
- Use `.env` file for local development only (gitignored)
- Generate strong secrets for production:
  ```bash
  openssl rand -hex 32  # For JWT_SECRET
  ```

**For AI API keys**:
- OpenRouter key stored in OPENROUTER_API_KEY
- Rotated regularly (quarterly)
- Scoped to minimal necessary permissions (read-only for code generation)

### 8.4 Agent Authentication (Planned)

Each agent will have a unique identity:

```python
# In message headers:
{
    "agent_id": "frontend-01",
    "signature": "hmac-sha256:abcdef123456...",
    "timestamp": 1234567890
}

# Verification:
expected = hmac_sha256(shared_secret, f"{timestamp}{payload}")
if signature != expected:
    raise SecurityError("Invalid message signature")
```

Shared secrets provisioned via secure vault (HashiCorp Vault, AWS Secrets Manager) in production.

## 9. Data Consistency and Concurrency

### 9.1 Task Assignment Race Conditions

**Problem**: Multiple agents of same role might try to claim the same pending task simultaneously.

**Solution**: Atomic transaction in StateManager:
```sql
BEGIN TRANSACTION;
SELECT * FROM tasks 
WHERE role = ? AND status = 'pending' 
ORDER BY priority DESC, created_at ASC 
LIMIT 1 
FOR UPDATE SKIP LOCKED;

-- If task found
UPDATE tasks 
SET status = 'assigned', assigned_to = ?, assigned_at = CURRENT_TIMESTAMP 
WHERE id = ?;
COMMIT;
```

`FOR UPDATE SKIP LOCKED` ensures only one agent can lock the row. Others skip to next task.

### 9.2 Message Ordering

**Guarantee**: Messages from a single sender to a single recipient are delivered in order (FIFO per channel) thanks to Redis pub/sub.

**Cross-channel ordering**: No guarantees. If Agent A sends to both B and C, B and C may process at different times.

**Solution**: Use correlation IDs to link related messages and reconstruct sequence in shared knowledge if needed.

### 9.3 Shared Knowledge Consistency

**Problem**: Two agents might write different values to same key concurrently.

**Solution**: Last-write-wins based on `updated_at` timestamp. If strict consistency needed, agents should:
1. Read current value with timestamp
2. Compute new value
3. Write back with `WHERE updated_at = old_timestamp` (optimistic locking)
4. Retry if row changed

Current implementation: Simple `INSERT OR REPLACE` with no conflict detection. Acceptable for non-critical data.

### 9.4 Agent State Consistency

Agent state updates (heartbeat, current_task) use individual row locks (PRIMARY KEY). No conflicts—each agent updates only its own row.

## 10. Monitoring and Observability

### 10.1 Metrics Collected

**Agent-level**:
- Health status (healthy/degraded/offline)
- Last heartbeat timestamp
- Current task ID
- Tasks completed count
- Uptime since last restart
- Error count

**System-level**:
- Total messages sent/received per minute
- Average task completion time
- Agent availability percentage
- Queue depth (pending tasks by role)
- Database connection pool usage

### 10.2 Dashboard Features

The Flask dashboard (`src/dashboard/app.py`) provides:

1. **Overview page** (`/`):
   - System health summary (green/yellow/red)
   - Active agents count
   - Message throughput graph (last hour)
   - Recent messages log (auto-refresh)

2. **Agent status API** (`/api/agents`):
   ```json
   [
     {
       "id": "frontend-01",
       "role": "frontend_developer",
       "status": "healthy",
       "current_task": "task-123",
       "last_heartbeat": "2024-01-15T10:30:45Z",
       "tasks_completed": 42
     }
   ]
   ```

3. **Task queue API** (`/api/tasks`):
   - Pending tasks grouped by role
   - Priority sorting
   - Age of oldest pending task

4. **Recent messages API** (`/api/messages?limit=50`):
   - Last 50 A2A messages
   - Sender, recipient, type, timestamp

5. **Metrics API** (`/api/metrics`):
   - Messages/sec
   - Tasks completed/hour
   - Average agent response time

### 10.3 Logging

**Structured logging** with Python's `logging` module:
- Format: `JSON` for easy parsing (or key=value for readability)
- Levels: DEBUG (detailed), INFO (normal), WARNING (agent slow), ERROR (failure)
- Output: Both stdout (Docker logs) and rotating file (`logs/agentic-team.log`)
- Rotation: 10MB max, keep 7 days

**Agent logs include**:
- Agent ID and role
- Task ID when working on task
- Message IDs for A2A communication
- Stack traces on exceptions

**Centralized log aggregation** (future): Ship logs to ELK stack or Datadog.

## 11. Deployment Architecture

### 11.1 Development Deployment

**Single-machine**: All components on one host (localhost):
- Python processes for agents
- Redis running locally (port 6379)
- SQLite file in current directory
- Flask dashboard on http://localhost:5000

**Startup**:
```bash
# Terminal 1: Start orchestrator (spawns all agents)
python -m src.orchestrator.main

# Terminal 2: Start dashboard
python -m src.dashboard.app

# Visit http://localhost:5000
```

### 11.2 Production Deployment

**Multi-machine**:
- Dedicated Redis server (or cluster for HA)
- Shared PostgreSQL database (or managed RDS)
- Multiple agent workers spread across machines
- Load balancer in front of dashboard (nginx)
- Systemd/Docker for process supervision

**Recommended setup**:
```
Machine A: Redis + PostgreSQL (or managed services)
Machine B: 3x Frontend agents + 2x Dev agents + 1x Security agent
Machine C: Dashboard (Flask) behind nginx with TLS
Machine D: Backup agent instances (cold standby)
```

### 11.3 Container Deployment (Docker)

**Dockerfile** (for agents):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "src.orchestrator.main"]
```

**docker-compose.yml**:
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: agentic_team
      POSTGRES_USER: agentic
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data

  orchestrator:
    build: .
    environment:
      REDIS_HOST: redis
      DATABASE_URL: postgresql://agentic:${DB_PASSWORD}@postgres/agentic_team
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
    depends_on:
      - redis
      - postgres

  dashboard:
    build: .
    command: python -m src.dashboard.app
    environment:
      FLASK_HOST: 0.0.0.0
      REDIS_HOST: redis
      DATABASE_URL: postgresql://agentic:${DB_PASSWORD}@postgres/agentic_team
    ports:
      - "5000:5000"
    depends_on:
      - redis
      - postgres

volumes:
  redis-data:
  postgres-data:
```

### 11.4 High Availability

**Redis HA**: Use Redis Sentinel or Redis Cluster
**PostgreSQL HA**: Use streaming replication + failover
**Dashboard HA**: Multiple instances behind load balancer with sticky sessions
**Agent HA**: Run extra agents as hot standby (already stateless, easy to add)

**No single point of failure**:
- ✅ Redis (clustered)
- ✅ Database (replicated)
- ✅ Dashboard (load balanced)
- ❌ Single orchestrator process: add leader election or run multiple (tasks will be duplicated—needs coordination)

## 12. Cost Considerations

### 12.1 OpenRouter API Costs

**Pricing model**: Per token (input + output).

**Estimated costs**:
- Security scan (code review): ~1k tokens = $0.0001 (with step-3.5-flash:free)
- Dev agent code generation: ~2k tokens = $0.0002
- Frontend UI generation: ~1.5k tokens = $0.00015
- **Per feature**: ~$0.0005 in AI costs

**Monthly estimate** (100 features/day):
100 features × $0.0005 × 30 days = $1.50/month

**Optimizations**:
- Cache AI responses in shared knowledge (avoid re-generation)
- Use cheaper models for simple tasks
- Set token limits per agent
- Batch similar requests

### 12.2 Infrastructure Costs

**Cloud deployment** (AWS/GCP/Azure):
- t3.small Redis instance: ~$15/month
- db.t3.micro PostgreSQL: ~$12/month
- t3.micro dashboard instance: ~$10/month
- **Total**: ~$37/month + bandwidth

**Self-hosted**: ~$5/month in electricity for always-on machine

**Cost optimization**: Scale down after hours, use spot instances for non-critical workloads.

## 13. Trade-offs and Alternatives Considered

### 13.1 No Workflow Engine

**Decision**: Implement custom wiggum loop instead of using Camunda/Step Functions.

**Rationale**:
- Simpler, fewer dependencies
- No external service required
- Sufficient for our linear task flow
- Easier to customize logic

**Downside**: No visual workflow designer, no BPMN standard support, harder to model complex branching.

### 13.2 SQLite over Distributed Database

**Decision**: SQLite for simplicity over distributed DB (CockroachDB, Yugabyte).

**Rationale**:
- Single-machine deployment is sufficient for most use cases
- No operational overhead
- ACID compliant
- Easy to migrate later

**Downside**: Not suitable for geo-distributed deployment, limited concurrent writers (though fine for our use case).

### 13.3 Custom Broker vs. Message Queue Service

**Decision**: Self-hosted Redis instead of AWS SQS/Google PubSub.

**Rationale**:
- Free (no per-message cost)
- Faster (sub-millisecond latency)
- Full control over configuration
- Works offline

**Downside**: Self-managed, need to handle HA ourselves.

### 13.4 Flat File Tasks (TASKS.md) vs. Database Tasks

**Decision**: Store tasks in human-editable TASKS.md file.

**Rationale**:
- Human-friendly (developers can read/edit directly)
- Version controlled with git
- No UI needed for task definition
- Markdown format supports comments, sections

**Downside**: Need to parse Markdown, not queryable, requires file rewrite on updates.

**Alternative**: Use YAML or JSON for easier parsing, but lose human-readability.

## 14. Future Enhancements

### 14.1 Near-Term (Next 3 Months)

1. **Redis Streams**: Replace pub/sub with streams for guaranteed delivery and consumer groups
2. **Agent Authentication**: JWT signing of messages
3. **Code Sandboxing**: Run generated code in containers before execution
4. **Prometheus Metrics**: Export metrics for Grafana dashboards
5. **WebSocket Dashboard**: Real-time updates without polling

### 14.2 Medium-Term (3-6 Months)

1. **PostgreSQL Migration**: Support both SQLite and PostgreSQL via configuration
2. **Multi-tenancy**: Support multiple independent teams sharing same infrastructure
3. **Human-in-the-Loop**: Add approval checkpoints for sensitive operations
4. **Task Dependencies**: Express DAG workflows instead of independent tasks
5. **AI Model Selection**: Allow different models per agent role based on need

### 14.3 Long-Term (6-12 Months)

1. **Federated Teams**: Multiple wiggum loops collaborating across organizations
2. **Learning System**: Capture feedback to improve agent prompts over time
3. **Auto-scaling**: Kubernetes operator to scale agents based on queue depth
4. **Plugin Architecture**: Allow community-contributed agent roles
5. **IDE Integration**: VS Code plugin to interact with agentic team from editor

## 15. Success Metrics

The system is considered successful when:

1. **Reliability**: 99.9% uptime, < 1% task failure rate due to system errors
2. **Autonomy**: System can run for 30 days without human intervention
3. **Productivity**: Agents complete tasks 2x faster than human solo developer (considering all 3 agents)
4. **Quality**: Security agent finds > 90% of vulnerabilities (vs. manual review)
5. **Extensibility**: New developer can add new agent role in < 4 hours
6. **Observability**: All system states visible in dashboard, < 5 min MTTR for issues

## 16. References

- **Wiggum Loop**: Original concept from OpenCode agent framework
- **Actor Model**: Carl Hewitt, 1973
- **Message Broker Pattern**: Enterprise Integration Patterns, Hohpe & Woolf
- **Repository Pattern**: Domain-Driven Design, Evans
- **CQRS**: Separate command (state change) and query (read) models

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15  
**Maintained By**: Agentic Team Development

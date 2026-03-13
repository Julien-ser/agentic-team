# Example Usage Guide

This guide provides hands-on examples of using the Agentic Team system. Learn how to define tasks, monitor execution, and interpret results.

## Table of Contents
1. [Quick Start Example](#quick-start-example)
2. [Defining Tasks](#defining-tasks)
3. [Monitoring the System](#monitoring-the-system)
4. [Sample Workflows](#sample-workflows)
5. [Expected Outputs](#expected-outputs)
6. [Troubleshooting](#troubleshooting)

---

## 1. Quick Start Example

### Scenario: Build a Simple API Endpoint

Let's walk through a complete feature: creating a Flask API endpoint for user authentication.

### Step 1: Add Tasks to TASKS.md

```markdown
## Feature: User Authentication

- [ ] [SW_DEV] Design authentication API specification
- [ ] [FRONTEND] Build login form component  
- [ ] [SW_DEV] Implement JWT authentication endpoint
- [ ] [SECURITY] Scan authentication code for vulnerabilities
- [ ] [SW_DEV] Add unit tests for authentication
```

### Step 2: Start the System

```bash
# Terminal 1: Start orchestrator
python -m src.orchestrator.main

# Terminal 2: Start dashboard
python -m src.dashboard.app

# Visit http://localhost:5000
```

### Step 3: Watch the Collaboration

The system will automatically:
1. **Frontend Agent** picks up "Build login form component"
2. **Dev Agent** picks up "Design authentication API specification"
3. Frontend asks Dev for API spec via A2A message
4. Dev sends back API contract (POST /api/auth/login)
5. Frontend builds form based on spec
6. Dev implements the endpoint with JWT
7. Security scans the code
8. Dev fixes any issues
9. Task completes

---

## 2. Defining Tasks

### 2.1 Task Format

Tasks must follow this pattern in `TASKS.md`:

```markdown
- [ ] [ROLE_TAG] Task description
```

**Role Tags** (case-sensitive):
- `[SECURITY]` - Security Agent
- `[SW_DEV]` - Software Developer Agent  
- `[FRONTEND]` - Frontend Developer Agent

**Status Indicators**:
- `[ ]` - Pending (not started)
- `[x]` - Completed
- `[~]` - In progress (agents don't set this; system manages internally)

### 2.2 Task Properties

Optionally include structured properties:

```markdown
- [ ] [SW_DEV] Implement OAuth2 callback handler
  - Priority: high
  - Estimate: 3 story points
  - Dependencies: [SW_DEV] Design OAuth2 flow
  - Acceptance: "Returns access token within 2 seconds"
```

The wiggum loop parses these properties and stores them in the `tasks` table.

### 2.3 Task Examples

**Simple task:**
```markdown
- [ ] [SECURITY] Add rate limiting to login endpoint
```

**Complex task with details:**
```markdown
- [ ] [FRONTEND] Create responsive dashboard layout
  - Priority: medium
  - Estimate: 5
  - Components: Header, Sidebar, MainContent, Footer
  - Acceptance: "Works on mobile, tablet, desktop"
  - Reference: "See Figma design at https://figma.com/file/..."
```

---

## 3. Monitoring the System

### 3.1 Dashboard Overview

Visit `http://localhost:5000` to see:

**Agent Status Cards:**
```
┌─────────────────┬────────────────────┬─────────────┐
│ Agent           │ Status             │ Current Task│
├─────────────────┼────────────────────┼─────────────┤
│ security        │ 🟢 Healthy         │ None        │
│ dev             │ 🟡 Working (65%)   │ auth-api    │
│ frontend        │ 🟢 Healthy         │ login-form  │
└─────────────────┴────────────────────┴─────────────┘
```

**Message Throughput Graph:**
- X-axis: Time (last hour)
- Y-axis: Messages per minute
- Peaks show when agents are actively collaborating

**Recent Activity Log:**
```
10:30:45 │ dev │ frontend │ api.spec.response │ "Auth API spec sent"
10:31:12 │ frontend │ dev │ component.ready │ "LoginForm component"
10:32:03 │ dev │ security │ security.scan.request │ "Scan auth code"
```

### 3.2 API Endpoints

Get JSON data for custom monitoring:

```bash
# List all agents with health
curl http://localhost:5000/api/agents

# Example response:
[
  {
    "id": "dev-01",
    "role": "software_developer",
    "status": "healthy",
    "current_task": "task-123",
    "last_heartbeat": "2024-01-15T10:30:45Z",
    "tasks_completed": 42
  }
]

# View pending tasks by role
curl http://localhost:5000/api/tasks

# Example response:
{
  "security": [],
  "software_developer": [
    {
      "id": "task-456",
      "description": "Implement password reset endpoint",
      "priority": 2,
      "created_at": "2024-01-15T09:00:00Z"
    }
  ],
  "frontend_developer": []
}

# Get recent A2A messages (last 50)
curl http://localhost:5000/api/messages?limit=20

# Get system metrics
curl http://localhost:5000/api/metrics

# Example response:
{
  "messages_per_second": 2.3,
  "tasks_completed_hour": 15,
  "agents_online": 3,
  "avg_response_time_ms": 245,
  "queue_depth": 7
}
```

### 3.3 Database Queries

Direct SQLite access for detailed analysis:

```bash
# Open database
sqlite3 agentic_team.db

# See all pending tasks
SELECT id, description, role, created_at 
FROM tasks 
WHERE status = 'pending' 
ORDER BY priority DESC, created_at ASC;

# View recent messages
SELECT sender, recipient, message_type, timestamp 
FROM messages 
ORDER BY timestamp DESC 
LIMIT 10;

# Check agent heartbeats
SELECT agent_id, role, last_heartbeat, health_status 
FROM agent_states 
WHERE datetime('now') - last_heartbeat < 60;

# Exit
.quit
```

---

## 4. Sample Workflows

### 4.1 Workflow 1: Feature: User Login

**Tasks:**
```markdown
- [ ] [FRONTEND] Build login form component
- [ ] [SW_DEV] Create authentication API endpoint with JWT
- [ ] [SECURITY] Review authentication implementation
- [ ] [SW_DEV] Add unit tests for authentication
```

**Expected Flow:**

1. **Frontend Agent** starts with login form task.
   - Generates HTML/CSS/JS login form with email/password fields.
   - Sends message to Dev: "I need an API spec for authentication."

2. **Dev Agent** receives API spec request.
   - Designs REST API: `POST /api/v1/auth/login`
   - Request: `{email, password}`
   - Response: `{token, user_id, expires_in}`
   - Sends spec back to Frontend.

3. **Frontend Agent** receives API spec.
   - Integrates spec into form's submit handler.
   - Makes `fetch('/api/v1/auth/login', ...)` call.
   - Stores JWT in localStorage.
   - Task complete → sends `component.ready` to Dev.

4. **Dev Agent** receives component.
   - Now has frontend code that calls the API.
   - Implements the actual Flask endpoint with PyJWT.
   - Writes password hashing with bcrypt.
   - Task: "Create authentication API endpoint" completes.

5. **Dev Agent** picks up "Add unit tests" task.
   - Writes pytest tests for login success/failure.
   - Tests pass → task complete.

6. **Security Agent** picks up "Review authentication" task.
   - Scans code for hardcoded secrets (none found).
   - Checks JWT expiration (set to 24h, good).
   - Verifies bcrypt work factor is 12 (adequate).
   - No vulnerabilities → task complete.

**Final Outputs:**
- `frontend/components/login_form.html` - responsive login form
- `backend/api/auth.py` - JWT authentication endpoint
- `backend/tests/test_auth.py` - unit tests (12 tests, all passing)
- Security report: 0 vulnerabilities

### 4.2 Workflow 2: Security Response

**Task:** "Fix critical vulnerability in payment module"

**Flow:**

1. **Security Agent** scans codebase.
   - Finds SQL injection in `payment.py:156`:
     ```python
     query = f"SELECT * FROM payments WHERE id = {payment_id}"
     ```
   - Sends `security.alert` to Dev Agent with severity "critical".

2. **Dev Agent** receives alert.
   - Loads affected file from shared knowledge.
   - Rewrites query using parameterized statements:
     ```python
     query = "SELECT * FROM payments WHERE id = $1"
     cursor.execute(query, (payment_id,))
     ```
   - Sends updated code back.

3. **Security Agent** rescans.
   - SQL injection gone ✓
   - No new issues introduced ✓
   - Task complete.

**Output:** Fixed `payment.py` with safe parameterized queries.

### 4.3 Workflow 3: API Contract Update

**Scenario:** Dev changes API response format, Frontend needs to adapt.

**Messages:**

1. Dev → Frontend: `api.contract.update`
   ```json
   {
     "api_spec": {
       "endpoint": "/api/v1/users",
       "method": "GET",
       "response_schema": {
         "type": "object",
         "properties": {
           "users": {"type": "array"},
           "total": {"type": "integer"}
         }
       }
     },
     "version": "1.1",
     "breaking_changes": ["Response now includes 'total' field"]
   }
   ```

2. Frontend receives update.
   - Adjusts UI to display user count.
   - Regenerates TypeScript types.
   - Sends `component.ready` with updated dashboard.

**Result:** Seamless API evolution without downtime.

---

## 5. Expected Outputs

### 5.1 Generated Artifacts

Each completed task produces outputs stored in the `shared_knowledge` store or filesystem:

**Software Dev Agent outputs:**
- Python source files (`.py`)
- Unit test files (`test_*.py`)
- Requirements updates (`requirements.txt` if needed)
- API documentation (`openapi.yaml`)

**Frontend Agent outputs:**
- HTML/CSS/JS files
- Component libraries (`components/` directory)
- Static assets (images, icons)
- README with usage instructions

**Security Agent outputs:**
- Security scan reports (`security_report_YYYY-MM-DD.md`)
- Vulnerability details (CWE IDs, severity, remediation)
- Compliance status (PCI DSS, OWASP Top 10 coverage)

### 5.2 Task Completion Notification

When a task finishes, the agent sends:

```json
{
  "task_id": "abc-123-def",
  "output": {
    "artifact_urls": [
      "shared_knowledge:auth_api_v1",
      "file:///artifacts/login_form.html"
    ],
    "summary": "Created JWT authentication endpoint with tests",
    "test_results": {"passed": 15, "failed": 0}
  },
  "metrics": {
    "time_seconds": 45.2,
    "tokens_used": 2847,
    "lines_of_code": 156
  }
}
```

These are visible in:
- Dashboard "Recent Messages" panel
- `sqlite3 agentic_team.db "SELECT * FROM messages WHERE message_type='task.complete'`
- `logs/` directory (agent logs)

### 5.3 Database State After Completion

```bash
# Tasks: 1 pending, 8 completed, 0 failed
SELECT status, COUNT(*) FROM tasks GROUP BY status;

# Messages: ~50 total messages exchanged for 8 tasks
SELECT COUNT(*) FROM messages;

# Agent health: all agents healthy
SELECT agent_id, health_status FROM agent_states;

# Shared knowledge: contains API specs, code artifacts
SELECT * FROM shared_knowledge LIMIT 3;
```

### 5.4 Performance Expectations

For a typical feature (3-5 tasks):

| Metric | Expected | Notes |
|--------|----------|-------|
| Total time | 10-30 minutes | Depends on AI model speed |
| Messages exchanged | 20-40 | Including requests/responses |
| AI tokens used | 5,000-15,000 | ~$0.005-0.015 cost |
| Code generated | 200-500 lines | Per task average |
| Test coverage | >80% | Auto-generated tests |

If tasks take >1 hour, check:
- OpenRouter API latency (`curl -o /dev/null -s -w "%{time_total}" https://openrouter.ai`)
- Redis response time (`redis-cli --latency`)
- System resources (`htop`)

---

## 6. Troubleshooting Common Scenarios

### 6.1 "No Tasks Appearing in Dashboard"

**Check:**
1. TASKS.md has unchecked tasks? ✓
2. Role tag spelled correctly? (`[SECURITY]`, not `[SEC]`) ✓
3. Agents are healthy? (check `/api/agents`) ✓
4. Database initialized? (`sqlite3 agentic_team.db .tables`) ✓

**Fix:** Restart orchestrator to force task reload:
```bash
# Stop (Ctrl+C) then restart
python -m src.orchestrator.main
```

### 6.2 "Agent Stuck on Task for Hours"

**Possible causes:**
- AI API rate limit exceeded → check OpenRouter dashboard
- Task too complex → break into smaller subtasks
- Agent crashed → check logs

**Action:** 
- Look at agent logs in `logs/` directory
- Manually fail the task via database:
  ```sql
  UPDATE tasks SET status='failed' WHERE id='task-xyz';
  ```

### 6.3 "Configuration Error: Missing OPENROUTER_API_KEY"

**Fix:**
```bash
echo "OPENROUTER_API_KEY=sk-or-v1-xxxx" >> .env
# Restart orchestrator
```

Get API key from: https://openrouter.ai/keys

### 6.4 "Redis Connection Refused"

**Start Redis:**
```bash
# Linux
sudo systemctl start redis

# macOS
brew services start redis

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 6.5 "Security Alert Not Being Addressed"

If Security finds a vulnerability but Dev doesn't fix it:

1. Check message routing: `SELECT * FROM messages WHERE message_type='security.alert'`
2. Manually reassign task to Dev with higher priority
3. Or send direct message via broker CLI:
   ```bash
   redis-cli PUBLISH wiggum:agentic:software_developer/security.alert '{"findings":...}'
   ```

---

## 7. Advanced Usage

### 7.1 Running Multiple Agents of Same Role

Scale horizontally for better throughput:

```bash
# Terminal 1: First frontend agent
AGENT_ID=frontend-01 python -m src.agents.frontend_agent

# Terminal 2: Second frontend agent  
AGENT_ID=frontend-02 python -m src.agents.frontend_agent

# Both will compete for [FRONTEND] tasks automatically
```

Check dashboard: Both agents appear in `/api/agents`.

### 7.2 Manual Task Injection (Beyond TASKS.md)

Add task directly to database:

```sql
INSERT INTO tasks (id, description, role, status, created_at)
VALUES (
  'manual-task-001', 
  'Generate API docs for auth module',
  'software_developer',
  'pending',
  datetime('now')
);
```

Agent will pick it up on next poll.

### 7.3 Custom Message Testing

Send test message via Redis CLI:

```bash
# Message to Security agent
redis-cli PUBLISH wiggum:agentic:security/security.alert \
'{"sender":"system","recipient":"security","message_type":"security.alert","payload":{"severity":"medium","category":"test","findings":[]}}'
```

Check agent logs to verify receipt.

### 7.4 Database Backup and Restore

**Backup:**
```bash
sqlite3 agentic_team.db ".backup 'backup/agentic_team_2024-01-15.db'"
```

**Restore:**
```bash
# Stop orchestrator first
sqlite3 agentic_team.db ".restore 'backup/agentic_team_2024-01-15.db'"
# Restart orchestrator
```

---

## 8. Integration with CI/CD

### 8.1 Pre-commit Hook

Run security scan on every commit:

```bash
# .git/hooks/pre-commit
#!/bin/bash
python -m src.agents.security_agent --scan-only .
if [ $? -ne 0 ]; then
  echo "Security scan failed. Fix issues before committing."
  exit 1
fi
```

### 8.2 GitHub Actions Workflow

```yaml
name: Agentic CI
on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run integration test
        run: pytest tests/test_collaborative_workflow.py -v
```

---

## 9. Metrics and KPIs

Track these to measure system effectiveness:

### 9.1 Operational Metrics
- **Task completion rate** = (tasks completed / tasks assigned) × 100%  
  Target: >95%

- **Average task duration** = total_time / tasks_completed  
  Target: <30 minutes per task

- **Agent uptime** = (time healthy / total time) × 100%  
  Target: >99.9%

- **Message delivery latency** = time sent → time received  
  Target: <500ms

### 9.2 Quality Metrics
- **Security vulnerability density** = vulnerabilities / KLOC  
  Target: <0.1 (aim for zero)

- **Test coverage** = lines_tested / total_lines × 100%  
  Target: >80%

- **Code review effectiveness** = bugs_caught_in_review / total_bugs  
  Target: >90%

- **Rework rate** = tasks_failing_first_attempt / total_tasks  
  Target: <5%

### 9.3 Business Metrics
- **Features per week** = count of completed feature sets  
  Target: 10+ features/week

- **Developer effort saved** = human_hours_saved / week  
  Target: 40+ hours (1 FTE equivalent)

- **Time to market** = idea → production  
  Target: <48 hours for standard features

---

## 10. Conclusion

This guide covered:
- ✅ Defining tasks with proper role tags
- ✅ Monitoring via dashboard and API
- ✅ Understanding message flows
- ✅ Interpreting outputs and artifacts
- ✅ Troubleshooting common issues
- ✅ Advanced scaling and integration

**Next steps:**
1. Add your project tasks to `TASKS.md`
2. Start the system: `python -m src.orchestrator.main`
3. Watch the dashboard: `http://localhost:5000`
4. Iterate based on agent outputs

**Need help?** See:
- [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) - installation issues
- [`docs/A2A_PROTOCOL.md`](A2A_PROTOCOL.md) - message format details
- [`docs/DESIGN.md`](DESIGN.md) - architecture deep-dive

Happy agentic development!

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15

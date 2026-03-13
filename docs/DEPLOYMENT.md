# Deployment Guide

This guide covers installing, configuring, and deploying the Agentic Team system in development and production environments.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Quick Start (Development)](#quick-start-development)
3. [Configuration](#configuration)
4. [Production Deployment](#production-deployment)
5. [Monitoring and Maintenance](#monitoring-and-maintenance)
6. [Troubleshooting](#troubleshooting)
7. [Upgrade Procedure](#upgrade-procedure)

---

## 1. Prerequisites

### 1.1 System Requirements

**Minimum (Development)**:
- CPU: 2 cores
- RAM: 4 GB (2 GB per agent + overhead)
- Disk: 10 GB free (SQLite + logs)
- OS: Linux, macOS, or Windows with WSL2

**Recommended (Production)**:
- CPU: 8+ cores (to handle 3+ agents concurrently)
- RAM: 16 GB (4 agents × 400MB + Redis + PostgreSQL)
- Disk: 100 GB SSD (for database growth + backups)
- OS: Ubuntu 22.04 LTS or later

### 1.2 Required Software

**Common**:
- Python 3.12+ (check with `python3 --version`)
- Git (for source control)
- `pip` (Python package installer)
- `sqlite3` (usually included with Python)

**Redis** (message broker):
- Redis 7.0+ (recommended) or 6.2+
- Install methods:
  - Ubuntu: `sudo apt-get install redis-server`
  - macOS: `brew install redis`
  - Docker: `docker run -p 6379:6379 redis:7-alpine`
  - Download from https://redis.io/download

**PostgreSQL** (production only, optional for dev):
- PostgreSQL 14+ 
- Install: `sudo apt-get install postgresql`

### 1.3 Optional Tools

- **Docker & Docker Compose**: For containerized deployment
- **Nginx**: For TLS termination and reverse proxy
- **Systemd**: For process supervision (Linux)
- **Prometheus + Grafana**: For metrics collection and visualization

### 1.4 Verify Prerequisites

```bash
# Check Python version
python3 --version  # Should be 3.12+

# Check Redis connection
redis-cli ping  # Should reply with PONG

# Check SQLite
sqlite3 --version  # Should be 3.35+

# Test Python can import required modules
python3 -c "import pydantic, flask, aiohttp, redis"  # No errors = OK
```

---

## 2. Quick Start (Development)

Follow these steps to get the system running on your local machine for development and testing.

### 2.1 Clone Repository

```bash
git clone https://github.com/your-org/agentic-team.git
cd agentic-team
```

### 2.2 Install Dependencies

```bash
pip install --user -r requirements.txt
```

This installs:
- redis==5.0.1 (Redis client)
- pydantic==2.9.2 (data validation)
- flask==3.0.0 (dashboard)
- aiohttp==3.10.0 (async HTTP)
- python-dotenv==1.0.0 (environment config)
- pytest==7.0.0 (testing)
- black==23.0.0 (formatting)
- ruff==0.1.0 (linting)
- safety==3.0.0 (security scanning)
- pip-audit==2.10.0 (vulnerability checking)

**Tip**: Use virtual environment if you prefer:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Even though the guideline says "no venv if unnecessary", we support it if you want isolation.

### 2.3 Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your settings (at minimum, set `OPENROUTER_API_KEY`):

```bash
# Required: Get your API key from https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Change these if not using defaults
REDIS_HOST=localhost
REDIS_PORT=6379
SQLITE_PATH=agentic_team.db
DASHBOARD_PORT=5000
```

### 2.4 Start Redis

If Redis is not already running:

```bash
# Linux (systemd)
sudo systemctl start redis
sudo systemctl enable redis  # Auto-start on boot

# macOS (brew)
brew services start redis

# Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

Verify Redis is running:

```bash
redis-cli ping  # Should print "PONG"
```

### 2.5 Initialize Database

The system uses SQLite (development) or PostgreSQL (production). Initialize the schema:

```bash
# For SQLite (default):
python -m src.state.migrate

# Output should show:
# [INFO] Creating tables: tasks, messages, agent_states, shared_knowledge
# [INFO] Database migration completed successfully
```

This creates `agentic_team.db` (or path specified in `SQLITE_PATH`) with all required tables.

### 2.6 Verify Database

```bash
sqlite3 agentic_team.db ".tables"
# Should list: tasks messages agent_states shared_knowledge

sqlite3 agentic_team.db "SELECT COUNT(*) FROM tasks;"
# Should output: 0
```

### 2.7 Run Tests (Optional but Recommended)

Ensure everything works:

```bash
# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_redis_broker.py -v
pytest tests/test_state_manager.py -v
pytest tests/test_security_agent.py -v
pytest tests/test_dev_agent.py -v
pytest tests/test_frontend_agent.py -v
pytest tests/test_collaborative_workflow.py -v
```

All tests should pass (some may skip if Redis not running).

### 2.8 Start the System

**Option A: Start all agents via orchestrator** (recommended for dev):

```bash
# Terminal 1: Start orchestrator (spawns all 3 agents)
python -m src.orchestrator.main

# You should see logs like:
# [INFO] Starting WorkerManager with 3 agents
# [INFO] Starting agent: security (role=security)
# [INFO] Starting agent: dev (role=software_developer)
# [INFO] Starting agent: frontend (role=frontend_developer)
# [INFO] Agent security health status: healthy
# [INFO] Agent dev health status: healthy
# [INFO] Agent frontend health status: healthy
```

**Option B: Start agents individually** (for debugging):

```bash
# Terminal 1: Security Agent
python -m src.agents.security_agent

# Terminal 2: Dev Agent
python -m src.agents.dev_agent

# Terminal 3: Frontend Agent
python -m src.agents.frontend_agent
```

Agents will:
1. Connect to Redis and SQLite
2. Register themselves in `agent_states` table
3. Start heartbeat loop (every 30s)
4. Begin polling for tasks (every 5s)
5. Wait for A2A messages

### 2.9 Launch Dashboard

In a new terminal:

```bash
python -m src.dashboard.app
```

Output:
```
 * Serving Flask app 'src.dashboard.app'
 * Debug mode: off
 * Running on http://localhost:5000
Press CTRL+C to quit
```

Open browser to http://localhost:5000. You should see:
- Agent status cards (3 agents, all healthy)
- Message throughput chart (likely flat line until tasks arrive)
- Recent activity log

### 2.10 First Task

The system loads tasks from `TASKS.md`. Add a simple task to test:

Edit `TASKS.md` and uncomment or add:

```markdown
## Sample Tasks for Testing

- [ ] [SW_DEV] Create a simple Flask hello world endpoint
- [ ] [FRONTEND] Build a button component with hover effects
```

Save the file. The Wiggum Master Loop polls `TASKS.md` every 60 seconds (configurable) and dispatches new tasks.

**Or manually trigger task load**: Restart the orchestrator.

Watch agent logs as tasks are assigned and processed. Check dashboard for updates.

---

## 3. Configuration

### 3.1 Environment Variables

All configuration is loaded from environment variables (or `.env` file in development). See `src/config.py` for defaults.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `OPENROUTER_API_KEY` | (none) | **Yes** | API key for OpenRouter AI service |
| `REDIS_HOST` | `localhost` | No | Redis server hostname |
| `REDIS_PORT` | `6379` | No | Redis port |
| `REDIS_PASSWORD` | (none) | No | Redis AUTH password (set in production) |
| `REDIS_DB` | `0` | No | Redis database number |
| `SQLITE_PATH` | `agentic_team.db` | No | Path to SQLite database file |
| `DATABASE_URL` | (derived) | No | Full DB URL. For PostgreSQL: `postgresql://user:pass@host/db` |
| `AGENT_HEARTBEAT_INTERVAL` | `30` | No | Seconds between heartbeat updates |
| `MAX_CONCURRENT_TASKS` | `3` | No | Max tasks per agent (future) |
| `FLASK_HOST` | `localhost` | No | Dashboard bind address (use `0.0.0.0` for external) |
| `FLASK_PORT` | `5000` | No | Dashboard port |
| `FLASK_DEBUG` | `false` | No | Enable Flask debug mode (dev only) |
| `REDIS_CHANNEL_PREFIX` | `wiggum:agentic:` | No | Redis channel prefix |

### 3.2 Configuration File Structure

**Development** (`.env`):
```bash
# Local development - DO NOT COMMIT
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxx
REDIS_HOST=localhost
REDIS_PORT=6379
SQLITE_PATH=/tmp/agentic_dev.db
FLASK_DEBUG=true
```

**Production** (system environment or Docker secrets):
```bash
# Managed by systemd or Kubernetes secrets
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxx
REDIS_HOST=redis.internal.example.com
REDIS_PORT=6379
REDIS_PASSWORD=super-secure-password-from-vault
DATABASE_URL=postgresql://agentic:securepass@postgres.internal.example.com/agentic_team
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false
```

### 3.3 Configuration Validation

Run config check:

```bash
python -c "from src.config import config; errors = config.validate(); print('Valid!' if not errors else errors)"
```

Expected output:
- `Valid!` if all required fields present
- Or: `['OPENROUTER_API_KEY is required']`

### 3.4 Agent-Specific Configuration

Agents can be configured individually via environment variables:

```bash
# Set per-agent when starting manually
AGENT_ID=frontend-01 python -m src.agents.frontend_agent
AGENT_ID=dev-01 python -m src.agents.dev_agent
AGENT_ID=security-01 python -m src.agents.security_agent
```

If `AGENT_ID` not set, defaults to `{hostname}-{role}`.

---

## 4. Production Deployment

### 4.1 Infrastructure Options

#### Option A: Bare Metal / VPS

Single server with all components:
- Ubuntu 22.04 LTS
- Redis (installed via apt)
- PostgreSQL (installed via apt)
- Python agents (systemd services)
- Nginx + Gunicorn for dashboard

#### Option B: Docker Compose (Recommended)

All services containerized:
- Redis container
- PostgreSQL container
- Agent containers (1 per role, or multiple scaled)
- Dashboard container
- Nginx container (TLS termination)

See `docker-compose.yml` example in README.

#### Option C: Kubernetes

For large-scale deployments:
- Multiple agent pods with Horizontal Pod Autoscaler
- Redis Cluster or ElastiCache
- Amazon RDS / Cloud SQL for PostgreSQL
- Ingress controller for dashboard

### 4.2 Docker Deployment

**Prerequisites**: Docker 20.10+, Docker Compose 2.0+

#### 4.2.1 Build Images

```bash
# Build agent image
docker build -t agentic-team:latest -f Dockerfile.agent .

# Build dashboard image
docker build -t agentic-dashboard:latest -f Dockerfile.dashboard .
```

Dockerfile.agent:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "src.orchestrator.main"]
```

Dockerfile.dashboard:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "src.dashboard.app:app"]
```

#### 4.2.2 Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # Redis Message Broker
  redis:
    image: redis:7-alpine
    container_name: wigredis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    ports:
      - "127.0.0.1:6379:6379"  # Only localhost for security
    volumes:
      - redis-data:/data
    networks:
      - agentic-network

  # PostgreSQL Database (Production)
  postgres:
    image: postgres:15
    container_name: wigpostgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: agentic_team
      POSTGRES_USER: agentic
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql  # optional init
    ports:
      - "127.0.0.1:5432:5432"
    networks:
      - agentic-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentic"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Agent Orchestrator (spawns all agents in one container)
  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: wigorchestrator
    restart: unless-stopped
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - REDIS_HOST=redis
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - DATABASE_URL=postgresql://agentic:${DB_PASSWORD}@postgres/agentic_team
      - FLASK_DEBUG=false
    depends_on:
      redis:
        condition: service_started
      postgres:
        condition: service_healthy
    networks:
      - agentic-network
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M

  # Dashboard (separate container for independent scaling)
  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    container_name: wigdashboard
    restart: unless-stopped
    environment:
      - REDIS_HOST=redis
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - DATABASE_URL=postgresql://agentic:${DB_PASSWORD}@postgres/agentic_team
      - FLASK_HOST=0.0.0.0
      - FLASK_PORT=5000
      - FLASK_DEBUG=false
    depends_on:
      - redis
      - postgres
      - orchestrator
    ports:
      - "5000:5000"
    networks:
      - agentic-network
    volumes:
      - ./logs:/app/logs

volumes:
  redis-data:
  postgres-data:

networks:
  agentic-network:
    driver: bridge
```

#### 4.2.3 Start with Docker Compose

```bash
# Create .env file with all required variables
cp .env.example .env
# Edit .env and add OPENROUTER_API_KEY, REDIS_PASSWORD, DB_PASSWORD

# Start all services
docker compose up -d

# Check logs
docker compose logs -f orchestrator
docker compose logs -f dashboard
```

Verify running:
```bash
docker compose ps
# All services should show "Up" or "running"
```

Visit http://localhost:5000

#### 4.2.4 Docker Compose Commands

```bash
# View logs
docker compose logs -f          # All services
docker compose logs -f orchestrator

# Stop services
docker compose down

# Stop and remove volumes (WARNING: loses data!)
docker compose down -v

# Restart one service
docker compose restart dashboard

# Scale orchestrator (if multiple instances configured)
docker compose up -d --scale orchestrator=3
```

### 4.3 Systemd Deployment (Bare Metal)

For production VPS without Docker, use systemd to manage processes.

#### 4.3.1 Create System User

```bash
sudo useradd --system --no-create-home --group agentic
sudo mkdir -p /opt/agentic-team
sudo chown agentic:agentic /opt/agentic-team
```

#### 4.3.2 Copy Code to Server

```bash
# On your machine:
tar czf agentic-team.tar.gz agentic-team/

# Transfer to server:
scp agentic-team.tar.gz user@server:/opt/agentic-team/
# Or use git clone if repo is remote

# On server:
sudo -u agentic tar xzf /opt/agentic-team/agentic-team.tar.gz -C /opt/agentic-team
```

#### 4.3.3 Install Dependencies

```bash
sudo -u agentic python3 -m venv /opt/agentic-team/venv
sudo -u agentic /opt/agentic-team/venv/bin/pip install -r /opt/agentic-team/requirements.txt
```

#### 4.3.4 Create Systemd Service Files

**Orchestrator service** (`/etc/systemd/system/wiggum-agentic-team.service`):

```ini
[Unit]
Description=Agentic Team Wiggum Orchestrator
After=network.target redis.service postgresql.service
Wants=redis.service postgresql.service

[Service]
Type=simple
User=agentic
Group=agentic
WorkingDirectory=/opt/agentic-team
EnvironmentFile=/opt/agentic-team/.env
ExecStart=/opt/agentic-team/venv/bin/python -m src.orchestrator.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agentic-orchestrator

[Install]
WantedBy=multi-user.target
```

**Dashboard service** (`/etc/systemd/system/agentic-dashboard.service`):

```ini
[Unit]
Description=Agentic Team Dashboard
After=network.target
Wants=network.target

[Service]
Type=simple
User=agentic
Group=agentic
WorkingDirectory=/opt/agentic-team
EnvironmentFile=/opt/agentic-team/.env
ExecStart=/opt/agentic-team/venv/bin/python -m src.dashboard.app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agentic-dashboard

[Install]
WantedBy=multi-user.target
```

#### 4.3.5 Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable wiggum-agentic-team.service
sudo systemctl enable agentic-dashboard.service

# Start services
sudo systemctl start wiggum-agentic-team.service
sudo systemctl start agentic-dashboard.service

# Check status
sudo systemctl status wiggum-agentic-team.service
sudo systemctl status agentic-dashboard.service

# View logs
sudo journalctl -u wiggum-agentic-team.service -f
sudo journalctl -u agentic-dashboard.service -f
```

#### 4.3.6 Nginx Reverse Proxy (Optional)

For TLS termination and better performance:

Install nginx:
```bash
sudo apt-get install nginx
```

Create site config `/etc/nginx/sites-available/agentic-team`:

```nginx
upstream dashboard {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name agentic.example.com;
    
    # Redirect HTTP to HTTPS (if you have SSL)
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name agentic.example.com;
    
    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/agentic.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentic.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://dashboard;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Enable and restart nginx:
```bash
sudo ln -s /etc/nginx/sites-available/agentic-team /etc/nginx/sites-enabled/
sudo nginx -t  # Test config
sudo systemctl reload nginx
```

Now dashboard is available at https://agentic.example.com

### 4.4 Production Checklist

Before going live, verify:

- [ ] Redis secured with password (`requirepass` config)
- [ ] Redis only bound to localhost or internal network (not public)
- [ ] PostgreSQL password is strong (> 16 chars, random)
- [ ] `OPENROUTER_API_KEY` has appropriate rate limits and spending caps
- [ ] Dashboard is behind TLS (nginx)
- [ ] Dashboard access restricted (basic auth or VPN)
- [ ] Logs are rotated (logrotate config or systemd journal)
- [ ] Database backups configured (daily)
- [ ] Redis persistence enabled (AOF or RDB snapshots)
- [ ] Monitoring alerts setup (disk full, service down, high error rate)
- [ ] Firewall rules restrict ports (6379, 5432, 5000 only from localhost or specific IPs)

---

## 5. Monitoring and Maintenance

### 5.1 Log Management

Logs go to:
- **stdout/stderr**: Captured by systemd journal or Docker logs
- **Agent-specific**: `logs/` directory (rotated manually or via logrotate)

#### View logs:

```bash
# Systemd
sudo journalctl -u wiggum-agentic-team.service -f

# Docker
docker compose logs -f orchestrator

# File
tail -f logs/orchestrator-2024-01-15.log
```

#### Log Rotation (/etc/logrotate.d/agentic-team):

```
/opt/agentic-team/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 agentic agentic
    sharedscripts
    postrotate
        systemctl reload wiggum-agentic-team.service > /dev/null 2>&1 || true
    endscript
}
```

### 5.2 Database Maintenance

**SQLite** (dev):
- Backups: `cp agentic_team.db backup/agentic_team_$(date +%Y%m%d).db`
- Vacuum (reclaim space): `sqlite3 agentic_team.db "VACUUM;"`
- Check integrity: `sqlite3 agentic_team.db "PRAGMA integrity_check;"`

**PostgreSQL** (prod):
```bash
# Backup (daily cron)
pg_dump -U agentic agentic_team > /backups/agentic_$(date +%Y%m%d).sql

# Restore
psql -U agentic agentic_team < backup.sql

# Monitor size
du -h /var/lib/postgresql/12/main/

# Autovacuum tuning (postgresql.conf)
autovacuum = on
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02
```

### 5.3 Redis Maintenance

```bash
# Check memory usage
redis-cli info memory | grep used_memory_human

# Check connected clients
redis-cli info clients | grep connected_clients

# Save snapshot
redis-cli save

# Flush all data (DANGER: clears all messages and state!)
redis-cli FLUSHDB

# Monitor commands in real-time
redis-cli monitor
```

**Redis config tips** (redis.conf):
```conf
# Enable AOF for durability (optional, performance impact)
appendonly yes
appendfsync everysec

# Set memory limit
maxmemory 256mb
maxmemory-policy allkeys-lru

# Require authentication
requirepass your-secure-password

# Bind to localhost only (if same machine)
bind 127.0.0.1
```

### 5.4 Performance Monitoring

**Dashboard built-in metrics**:
- Visit `/api/metrics` for JSON metrics
- Messages/sec
- Tasks completed/hour
- Agent response times

**External monitoring** (optional):

Add Prometheus exporter (`src/metrics/prometheus_exporter.py`):

```python
from prometheus_client import start_http_server, Gauge, Counter

# Define metrics
AGENT_HEALTH = Gauge('agentic_agent_health', 'Agent health status (1=healthy)', ['agent'])
TASKS_COMPLETED = Counter('agentic_tasks_completed', 'Total tasks completed', ['agent'])
MESSAGES_SENT = Counter('agentic_messages_sent', 'Total messages sent', ['sender', 'recipient'])

# Update in agent code:
TASKS_COMPLETED.labels(agent=agent.role.value).inc()

# Start server
start_http_server(8000)  # Metrics at http://localhost:8000/metrics
```

Then configure Prometheus to scrape `http://localhost:8000/metrics` and Grafana dashboards.

### 5.5 Alerting

Set up alerts for:

| Condition | Threshold | Notification |
|-----------|-----------|--------------|
| Agent offline | heartbeat > 90s | Slack/email |
| Task queue depth | pending tasks > 50 | Email |
| Redis memory > 80% | 80% usage | PagerDuty |
| Database size | > 10GB | Email |
| Error rate | > 5% of messages | Slack |

Use simple bash script cron job:

```bash
#!/bin/bash
# /usr/local/bin/agentic-health-check.sh

ALERT_CHANNEL="webhook url or email"

# Check agent heartbeats
INACTIVE=$(sqlite3 agentic_team.db "SELECT COUNT(*) FROM agent_states WHERE datetime('now') - last_heartbeat > 90;")
if [ "$INACTIVE" -gt 0 ]; then
    curl -X POST -H "Content-Type: application/json" -d "{\"text\":\"⚠️ $INACTIVE agents offline\"}" $ALERT_CHANNEL
fi

# Check queue depth
PENDING=$(sqlite3 agentic_team.db "SELECT COUNT(*) FROM tasks WHERE status='pending';")
if [ "$PENDING" -gt 50 ]; then
    curl -X POST -H "Content-Type: application/json" -d "{\"text\":\"⚠️ $PENDING tasks pending\"}" $ALERT_CHANNEL
fi
```

Cron:
```bash
# Run every 5 minutes
*/5 * * * * /usr/local/bin/agentic-health-check.sh
```

### 5.6 Rotating Tasks

The wiggum loop polls `TASKS.md` every 60 seconds. To prevent task spam:

- **Archive completed tasks**: Move done tasks to `TASKS_COMPLETED.md` (manually or script)
- **Throttle polling**: Adjust `TASK_Poll_INTERVAL` in config if needed (default 60s)
- **Task IDs**: Each task load generates new UUID; duplicates are ignored

### 5.7 Rolling Updates

When deploying new code:

1. Stop orchestrator: `sudo systemctl stop wiggum-agentic-team`
2. Pull new code: `git pull origin main`
3. Update dependencies: `pip install -r requirements.txt --upgrade`
4. Run migrations if schema changed: `python -m src.state.migrate`
5. Restart: `sudo systemctl start wiggum-agentic-team`
6. Verify: Check dashboard, logs

**Zero-downtime**: Run multiple orchestrator instances with load balancer (complex, requires task coordination). Simpler: brief downtime acceptable.

---

## 6. Troubleshooting

### 6.1 Redis Connection Errors

**Symptom**: `ConnectionError: Error 111 connecting to localhost:6379. Connection refused.`

**Fix**:
1. Verify Redis running: `redis-cli ping`
2. If not running: `sudo systemctl start redis`
3. Check port: `netstat -tlnp | grep 6379`
4. Verify `REDIS_HOST` and `REDIS_PORT` in `.env` match Redis config

---

### 6.2 Database Locked

**Symptom**: `sqlite3.OperationalError: database is locked`

**Cause**: Multiple writers (unlikely with single instance) or long-running transaction.

**Fix**:
1. Ensure only one orchestrator instance running (check `ps aux | grep orchestrator`)
2. Increase SQLite timeout in config: `DATABASE_TIMEOUT=30`
3. Check for zombie processes holding locks: `lsof | grep agentic_team.db`
4. Run `VACUUM` on database to defragment (during maintenance window)

---

### 6.3 Agent Not Receiving Tasks

**Symptom**: Dashboard shows agent "healthy" but no task activity.

**Fix**:
1. Check TASKS.md has unchecked tasks with correct role tag: `[SW_DEV]`, `[FRONTEND]`, `[SECURITY]`
2. Verify agent role matches task tag (case-sensitive)
3. Check StateManager logs: `sqlite3 agentic_team.db "SELECT * FROM tasks WHERE status='pending';"`
4. Force task reload: Restart orchestrator
5. Check agent's inboxsubscription: Redis channel naming correct?

---

### 6.4 Dashboard Not Updating

**Symptom**: Dashboard shows old data, doesn't refresh.

**Fix**:
1. Verify dashboard connected to same Redis and database as agents
2. Check browser console for JS errors
3. Clear browser cache
4. Verify Flask running: `ps aux | grep dashboard`
5. Check dashboard logs for errors: `journalctl -u agentic-dashboard -f`

---

### 6.5 High Memory Usage

**Symptom**: Process using > 1GB RAM.

**Fix**:
1. Check for memory leak in agent (restart that agent)
2. Reduce number of agents if not needed
3. Increase swap space temporarily: `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`
4. Profile memory: `python -m memory_profiler src/agents/dev_agent.py` (install memory_profiler first)

---

### 6.6 OpenRouter API Errors

**Symptom**: Agents failing with `AuthenticationError` or `RateLimitError`.

**Fix**:
1. Verify API key valid: `curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/chat/completions` (test endpoint)
2. Check quota/billing on OpenRouter dashboard
3. Add rate limiting: Implement exponential backoff in agent code (in progress)
4. Check if model is deprecated; update `WIGGUM_MODEL` in config

---

### 6.7 Agent Crashes on Startup

**Symptom**: Agent process exits immediately with stack trace.

**Fix**:
1. Check permissions: Can agent write to log directory? (`chmod 755 logs/`)
2. Check `.env` file exists and readable
3. Run manually to see stderr: `python -m src.agents.dev_agent` (don't background)
4. Common issue: Missing `OPENROUTER_API_KEY` → Set in `.env`
5. Check Python version: `python3 --version` must be 3.12+

---

### 6.8 Slow Performance

**Symptom**: Tasks taking > 10 minutes, message latency > 5 seconds.

**Diagnosis**:
1. Check CPU: `top` or `htop` (agents should use < 50% CPU when idle)
2. Check Redis latency: `redis-cli --latency` (should be < 1ms on localhost)
3. Check database: `sqlite3 agentic_team.db ".time"` and run queries
4. Network issues? OpenRouter API latency: `curl -w "@curl-format.txt" -o /dev/null -s "https://openrouter.ai/api/v1/models"`

**Fix**:
- Use faster OpenRouter model (e.g., `anthropic/claude-3-haiku` vs `gpt-4`)
- Reduce AI prompt complexity
- Increase agent concurrency (future: async task processing within agents)
- Move Redis/database to faster SSD

---

## 7. Upgrade Procedure

### 7.1 Version Check

Check current version in `src/__init__.py`:
```python
__version__ = "1.0.0"
```

Check release notes in GitHub Releases for breaking changes.

### 7.2 Backup Everything

```bash
# Database
cp agentic_team.db agentic_team.db.backup-$(date +%Y%m%d)

# Redis (if persistence enabled)
redis-cli save
cp /var/lib/redis/dump.rdb redis-backup-$(date +%Y%m%d).rdb

# Code
git stash
git pull origin main
```

### 7.3 Upgrade Dependencies

```bash
pip install -r requirements.txt --upgrade
```

Check for breaking changes in libraries (pydantic, flask, redis).

### 7.4 Run Database Migrations

If schema changed:
```bash
python -m src.state.migrate
```

The migrate script is idempotent—safe to run multiple times.

### 7.5 Smoke Test

```bash
# Start system
python -m src.orchestrator.main

# Wait 10 seconds for agents to connect

# Check health
curl http://localhost:5000/api/agents

# Should return JSON with agent statuses
```

### 7.6 Monitor

Watch logs for 30 minutes:
```bash
tail -f logs/orchestrator-$(date +%Y-%m-%d).log
```

Check:
- No errors
- Heartbeats every 30s
- Tasks being processed

### 7.7 Rollback (if needed)

If upgrade fails:

```bash
# Stop services
sudo systemctl stop wiggum-agentic-team.service

# Restore code
git reset --hard HEAD@{1}  # or specific commit
git stash pop

# Restore database
cp agentic_team.db.backup-YYYYMMDD agentic_team.db

# Restore Redis if needed
redis-cli FLUSHALL
cat redis-backup-YYYYMMDD.rdb | redis-server -

# Reinstall old dependencies (from previous pip freeze)
pip install -r requirements.txt.backup

# Restart
sudo systemctl start wiggum-agentic-team.service
```

---

## 8. Security Hardening

### 8.1 Redis Security

Edit `/etc/redis/redis.conf`:

```conf
# Bind only to localhost or internal interface
bind 127.0.0.1 ::1
# Or: bind 10.0.1.5  # internal network IP

# Require password
requirepass XyZ3$9pLm!2qR

# Disable dangerous commands (optional)
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_ADMIN_ONLY"

# Limit memory
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Restart: `sudo systemctl restart redis`

### 8.2 PostgreSQL Security

Edit `/etc/postgresql/15/main/pg_hba.conf`:

```
# Only allow local connections (or specific IPs)
local   agentic_team    agentic                                peer
host    agentic_team    agentic    127.0.0.1/32            scram-sha-256
host    agentic_team    agentic    10.0.1.0/24            scram-sha-256  # internal network
```

Edit `/etc/postgresql/15/main/postgresql.conf`:

```conf
listen_addresses = 'localhost'  # or internal IP
password_encryption = scram-sha-256
```

### 8.3 File Permissions

```bash
# Restrict .env and database
chmod 600 .env agentic_team.db
chmod 700 logs/

# Agent user should not have sudo
sudo -u agentic -s  # should fail if properly restricted

# Set ownership
chown -R agentic:agentic /opt/agentic-team
```

### 8.4 Network Security

**Firewall** (ufw):
```bash
sudo ufw default deny incoming
sudo ufw allow from 127.0.0.1 to any port 6379  # Redis only local
sudo ufw allow from 10.0.1.0/24 to any port 5432  # PostgreSQL only internal
sudo ufw allow 5000/tcp  # Dashboard (consider restricting to office IP)
sudo ufw enable
```

### 8.5 Secrets Management

**Never commit secrets to git!**

Use solutions:
- **HashiCorp Vault**: Store DB passwords, API keys
- **AWS Secrets Manager**: For AWS deployments
- **Environment variables**: For simple setups (Docker/K8s secrets)
- **Ansible Vault**: For config management

Rotate passwords quarterly.

---

## 9. Upgrade Path to PostgreSQL

When SQLite becomes insufficient (many agents, high write volume):

1. Provision PostgreSQL instance
2. Set `DATABASE_URL=postgresql://agentic:password@host/agentic_team`
3. Ensure schema matches (migrations will create tables)
4. Stop agents → Run `python -m src.state.migrate` → Start agents
5. SQLite file becomes obsolete (archive it)

**No code changes needed** if using `src/config.py` correctly—StateManager reads `DATABASE_URL` and switches drivers automatically (see `src/state/state_manager.py` for asyncpg implementation).

---

## 10. Getting Help

- **Documentation**: See `/docs` directory
- **GitHub Issues**: https://github.com/your-org/agentic-team/issues
- **Community Chat**: Slack/Discord link in README
- **Commercial Support**: Available from Anomaly (see website)

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15

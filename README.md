# Agentic Team

An autonomous multi-agent development system built on the wiggum loop concept. Three specialized agents (Security, Software Developer, Frontend) collaborate via Agent-to-Agent (A2A) communication to complete development tasks autonomously.

## Architecture Overview

The system consists of:
- **3 Specialized Agents**: Security, Software Developer, Frontend
- **Redis Message Broker**: A2A communication backbone
- **SQLite Shared State**: Task persistence and coordination
- **Flask Dashboard**: Real-time monitoring and control
- **Wiggum Master Loop**: Task dispatcher and orchestrator

Read the full architecture documentation in [`docs/architecture.md`](docs/architecture.md).

## Current Progress

**Phase 1 - Planning & Architecture** (Complete)
- ✅ Task 1.1: System architecture and component diagram completed
- ✅ Task 1.2: Define agent role specifications and protocols
- ✅ Task 1.3: Create database schema for shared state
- ✅ Task 1.4: Setup project dependencies and environment configuration

**Phase 2 - Core Infrastructure & Wiggum Loop Enhancement** (In Progress)
- ✅ Task 2.1: Implement the enhanced wiggum loop with role-based agent selection
- [x] Task 2.2: Build the message broker using Redis pub/sub
- [ ] Task 2.3: Create agent base class and lifecycle manager
- [ ] Task 2.4: Implement shared state manager with SQLite

## Quick Start

### Prerequisites
- Python 3.12+
- Redis (running on localhost:6379)
- SQLite (included with Python)

### Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment (optional):
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. Initialize the database:
   ```bash
   python -m src.state.migrate
   ```

4. Start the system:
   ```bash
   python -m src.orchestrator.main
   ```

5. Launch the dashboard (separate terminal):
   ```bash
   python -m src.dashboard.app
   ```

6. Visit `http://localhost:5000` to monitor agent activity

## Project Structure

```
agentic-team/
├── docs/                    # Documentation
│   └── architecture.md     # System design and specifications
├── src/                    # Source code
│   ├── protocols/          # Agent specifications and message protocols
│   ├── agents/            # Specialized agent implementations
│   ├── messaging/         # Redis broker and message router
│   ├── state/             # SQLite state manager
│   ├── core/              # Wiggum loop implementation
│   ├── orchestrator/      # Agent worker orchestration
│   └── dashboard/         # Flask monitoring interface
├── tests/                 # Unit and integration tests
├── requirements.txt       # Python dependencies
├── .env.example          # Environment configuration template
└── TASKS.md             # Development roadmap
```

## How It Works

1. **Task Definition**: Tasks with role tags (`[SECURITY]`, `[SW_DEV]`, `[FRONTEND]`) are defined in `TASKS.md`
2. **Task Dispatch**: Wiggum Master parses tasks and assigns them to appropriate agents
3. **Collaboration**: Agents communicate via Redis pub/sub, exchanging messages and code
4. **Shared State**: All interactions and task status persisted in SQLite
5. **Monitoring**: Flask dashboard displays real-time agent activity and system metrics

## Agent Capabilities

- **Security Agent**: Vulnerability scanning, CVE checking, security recommendations
- **Software Dev Agent**: Code generation, unit testing, code formatting, refactoring
- **Frontend Agent**: UI component generation, responsive design, API integration

## Message Protocol

Agents communicate using typed messages with Pydantic validation. See [`docs/architecture.md`](docs/architecture.md#message-protocol-specification) for complete specification.

## License

MIT

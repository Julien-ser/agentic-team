"""
Database schema for the agentic-team shared state system.

This module defines the SQLite schema for:
- tasks: Task definitions and status tracking
- messages: A2A communication log
- agent_states: Agent health and current work tracking
- shared_knowledge: Key-value store for shared data
"""

# SQL statements to create all tables
CREATE_TABLES_SQL = """
-- Tasks table: stores development tasks with role assignments
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('security', 'software_developer', 'frontend_developer')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'assigned', 'in_progress', 'completed', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    assigned_to TEXT,
    completed_at TEXT
);

-- Messages table: persists all A2A communication
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    correlation_id TEXT
);

-- Agent states table: tracks agent health and current task
CREATE TABLE IF NOT EXISTS agent_states (
    agent_id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN ('security', 'software_developer', 'frontend_developer')),
    current_task_id INTEGER,
    health_status TEXT NOT NULL DEFAULT 'healthy' CHECK(health_status IN ('healthy', 'unhealthy', 'offline')),
    last_heartbeat TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY (current_task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

-- Shared knowledge table: key-value store for inter-agent data sharing
CREATE TABLE IF NOT EXISTS shared_knowledge (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY (source_agent) REFERENCES agent_states(agent_id) ON DELETE CASCADE
);
"""

CREATE_INDEXES_SQL = """
-- Indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_tasks_role_status ON tasks(role, status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
CREATE INDEX IF NOT EXISTS idx_messages_correlation ON messages(correlation_id);
"""


# Helper function to get current timestamp in ISO8601 UTC format
def get_timestamp() -> str:
    """Return current timestamp in ISO8601 format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

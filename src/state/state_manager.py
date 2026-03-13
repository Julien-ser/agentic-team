"""
Shared state manager for agentic-team.

Provides thread-safe access to the shared SQLite database
with proper transaction isolation and row-level locking.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import threading


class StateManager:
    """
    Manages shared state between agents via SQLite with concurrent access support.

    Features:
    - Atomic task assignment with row-level locking
    - Transaction isolation for safe concurrent access
    - Automatic retry on database locks
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize StateManager with database path.

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            project_root = Path(__file__).parent.parent.parent
            db_path = str(project_root / "agentic_team.db")

        self.db_path = db_path
        self._lock = threading.RLock()

    @contextmanager
    def _get_connection(self, timeout: float = 30.0):
        """
        Context manager for database connections with retry logic.

        Uses IMMEDIATE transactions to acquire write locks early
        and prevent deadlocks between concurrent agents.
        """
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=timeout,
                isolation_level=None,  # We'll manage transactions manually
            )
            conn.row_factory = sqlite3.Row

            # Start transaction with write lock
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()

        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def get_next_task(self, agent_role: str) -> Optional[Dict[str, Any]]:
        """
        Atomically fetch and assign the next pending task for the given role.

        Uses row-level locking to ensure only one agent gets each task.

        Args:
            agent_role: Role of the agent requesting a task

        Returns:
            Task dictionary or None if no tasks available
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Find next pending task for this role
                cursor.execute(
                    """
                    SELECT id, description, role, status, created_at
                    FROM tasks
                    WHERE role = ? AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (agent_role,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                task_id = row["id"]

                # Atomically assign the task
                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = 'assigned', assigned_to = ?
                    WHERE id = ?
                    """,
                    (agent_role, task_id),
                )

                # Return the full task details
                return {
                    "id": task_id,
                    "description": row["description"],
                    "role": row["role"],
                    "status": "assigned",
                    "created_at": row["created_at"],
                }

    def assign_task(self, task_id: int, agent_id: str) -> bool:
        """
        Explicitly assign a specific task to an agent.

        Returns True if assignment succeeded, False if task not found
        or already assigned to someone else.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = 'assigned', assigned_to = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (agent_id, task_id),
                )

                return cursor.rowcount > 0

    def complete_task(self, task_id: int) -> bool:
        """Mark a task as completed."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = 'completed', completed_at = ?
                    WHERE id = ?
                    """,
                    (self._get_timestamp(), task_id),
                )

                return cursor.rowcount > 0

    def fail_task(self, task_id: int, reason: str) -> bool:
        """Mark a task as failed with an optional reason."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Store failure reason in shared knowledge
                if reason:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO shared_knowledge (key, value, source_agent, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            f"task_failure:{task_id}",
                            reason,
                            "system",
                            self._get_timestamp(),
                        ),
                    )

                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = 'failed'
                    WHERE id = ?
                    """,
                    (task_id,),
                )

                return cursor.rowcount > 0

    def store_message(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        content: str,
        correlation_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Persist an A2A message to the database.

        Returns:
            Message ID or None if insertion failed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO messages (sender, recipient, message_type, content, timestamp, correlation_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sender,
                        recipient,
                        message_type,
                        content,
                        self._get_timestamp(),
                        correlation_id,
                    ),
                )

                return cursor.lastrowid

    def get_messages(
        self,
        recipient: Optional[str] = None,
        sender: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent messages with optional filtering.

        Args:
            recipient: Filter by recipient
            sender: Filter by sender
            limit: Maximum number of messages to return
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM messages"
                params = []

                if recipient or sender:
                    query += " WHERE "
                    conditions = []
                    if recipient:
                        conditions.append("recipient = ?")
                        params.append(recipient)
                    if sender:
                        conditions.append("sender = ?")
                        params.append(sender)
                    query += " AND ".join(conditions)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [dict(row) for row in rows]

    def update_agent_heartbeat(
        self, agent_id: str, role: str, health_status: str = "healthy"
    ) -> bool:
        """
        Update agent heartbeat and health status.

        Creates agent state if it doesn't exist.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                timestamp = self._get_timestamp()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO agent_states (agent_id, role, current_task_id, health_status, last_heartbeat)
                    VALUES (
                        ?,
                        COALESCE(
                            (SELECT role FROM agent_states WHERE agent_id = ?),
                            ?
                        ),
                        COALESCE(
                            (SELECT current_task_id FROM agent_states WHERE agent_id = ?),
                            0
                        ),
                        ?, ?
                    )
                    """,
                    (agent_id, agent_id, role, agent_id, health_status, timestamp),
                )

                return cursor.rowcount > 0

    def get_agent_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent state by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM agent_states WHERE agent_id = ?", (agent_id,)
                )

                row = cursor.fetchone()
                return dict(row) if row else None

    def get_all_agent_states(self) -> List[Dict[str, Any]]:
        """Get all agent states."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM agent_states ORDER BY last_heartbeat DESC"
                )
                rows = cursor.fetchall()

                return [dict(row) for row in rows]

    def set_shared_knowledge(self, key: str, value: str, source_agent: str) -> None:
        """Store or update a key-value pair in shared knowledge."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO shared_knowledge (key, value, source_agent, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, value, source_agent, self._get_timestamp()),
                )

    def get_shared_knowledge(self, key: str) -> Optional[str]:
        """Retrieve a value from shared knowledge."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT value FROM shared_knowledge WHERE key = ?", (key,)
                )

                row = cursor.fetchone()
                return row["value"] if row else None

    def get_all_shared_knowledge(self) -> List[Dict[str, Any]]:
        """Get all shared knowledge entries."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM shared_knowledge ORDER BY updated_at DESC"
                )
                rows = cursor.fetchall()

                return [dict(row) for row in rows]

    def get_pending_tasks(self, agent_role: str) -> List[Dict[str, Any]]:
        """Get all pending tasks for a role (without assigning them)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM tasks
                    WHERE role = ? AND status = 'pending'
                    ORDER BY created_at ASC
                    """,
                    (agent_role,),
                )

                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def get_tasks_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all tasks with a specific status."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                )

                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO8601 UTC format."""
        return datetime.now(timezone.utc).isoformat()

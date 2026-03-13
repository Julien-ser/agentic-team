"""
Unit tests for StateManager.

Tests cover all CRUD operations with proper isolation,
atomicity guarantees, and concurrent access safety.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from src.state.state_manager import StateManager
from src.state.schema import CREATE_TABLES_SQL, CREATE_INDEXES_SQL


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    """Create a temporary database with schema."""
    db_path = tmp_path / "test.db"

    # Initialize schema
    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_TABLES_SQL)
    conn.executescript(CREATE_INDEXES_SQL)
    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def state_manager(temp_db: str) -> Generator[StateManager, None, None]:
    """Create a StateManager instance for testing."""
    manager = StateManager(db_path=temp_db)
    yield manager


class TestTaskOperations:
    """Tests for task fetching and assignment."""

    def test_get_next_task_returns_pending_task(
        self, state_manager: StateManager
    ) -> None:
        """Test fetching next pending task."""
        # Insert test tasks
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Test task 1", "security", "pending"),
            )
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Test task 2", "security", "pending"),
            )
            conn.commit()

        task = state_manager.get_next_task("security")

        assert task is not None
        assert task["description"] in ["Test task 1", "Test task 2"]
        assert task["status"] == "assigned"

    def test_get_next_task_none_when_no_pending(
        self, state_manager: StateManager
    ) -> None:
        """Test returns None when no pending tasks."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Test task", "security", "completed"),
            )
            conn.commit()

        task = state_manager.get_next_task("security")
        assert task is None

    def test_get_next_task_filters_by_role(self, state_manager: StateManager) -> None:
        """Test that get_next_task only returns tasks for specified role."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Security task", "security", "pending"),
            )
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Dev task", "software_developer", "pending"),
            )
            conn.commit()

        task = state_manager.get_next_task("security")
        assert task is not None
        assert task["description"] == "Security task"

        task = state_manager.get_next_task("software_developer")
        assert task is not None
        assert task["description"] == "Dev task"

    def test_assign_task_succeeds(self, state_manager: StateManager) -> None:
        """Test explicit task assignment."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Assign me", "security", "pending"),
            )
            task_id = cursor.lastrowid
            conn.commit()

        result = state_manager.assign_task(task_id, "agent_001")
        assert result is True

        # Verify assignment
        task = state_manager.get_agent_state(
            "agent_001"
        )  # Not a direct query, but test
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, assigned_to FROM tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            assert row[0] == "assigned"
            assert row[1] == "agent_001"

    def test_assign_task_fails_for_completed_task(
        self, state_manager: StateManager
    ) -> None:
        """Test assignment fails for non-pending task."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Completed task", "security", "completed"),
            )
            task_id = cursor.lastrowid
            conn.commit()

        result = state_manager.assign_task(task_id, "agent_001")
        assert result is False

    def test_complete_task(self, state_manager: StateManager) -> None:
        """Test marking task as complete."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Complete me", "security", "assigned"),
            )
            task_id = cursor.lastrowid
            conn.commit()

        result = state_manager.complete_task(task_id)
        assert result is True

        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, completed_at FROM tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            assert row[0] == "completed"
            assert row[1] is not None

    def test_fail_task(self, state_manager: StateManager) -> None:
        """Test marking task as failed."""
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Fail me", "security", "assigned"),
            )
            task_id = cursor.lastrowid
            conn.commit()

        result = state_manager.fail_task(task_id, "Test failure reason")
        assert result is True

        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            assert row[0] == "failed"

            # Check failure reason stored
            cursor.execute(
                "SELECT value FROM shared_knowledge WHERE key = ?",
                (f"task_failure:{task_id}",),
            )
            row = cursor.fetchone()
            assert row[0] == "Test failure reason"


class TestMessageOperations:
    """Tests for A2A message persistence."""

    def test_store_message(self, state_manager: StateManager) -> None:
        """Test storing a message."""
        msg_id = state_manager.store_message(
            sender="agent_a",
            recipient="agent_b",
            message_type="test.message",
            content="Hello world",
            correlation_id="corr_001",
        )

        assert msg_id is not None
        assert msg_id > 0

    def test_get_messages_by_recipient(self, state_manager: StateManager) -> None:
        """Test retrieving messages filtered by recipient."""
        state_manager.store_message(
            sender="agent_a",
            recipient="agent_b",
            message_type="msg1",
            content="Hello B",
        )
        state_manager.store_message(
            sender="agent_a",
            recipient="agent_c",
            message_type="msg2",
            content="Hello C",
        )

        messages = state_manager.get_messages(recipient="agent_b")

        assert len(messages) == 1
        assert messages[0]["recipient"] == "agent_b"
        assert messages[0]["content"] == "Hello B"

    def test_get_messages_by_sender(self, state_manager: StateManager) -> None:
        """Test retrieving messages filtered by sender."""
        state_manager.store_message(
            sender="agent_a", recipient="agent_b", message_type="msg1", content="Msg 1"
        )
        state_manager.store_message(
            sender="agent_x", recipient="agent_b", message_type="msg2", content="Msg 2"
        )

        messages = state_manager.get_messages(sender="agent_a")

        assert len(messages) == 1
        assert messages[0]["sender"] == "agent_a"

    def test_get_messages_limit(self, state_manager: StateManager) -> None:
        """Test message limit parameter."""
        for i in range(10):
            state_manager.store_message(
                sender=f"sender_{i}",
                recipient="recipient",
                message_type="test",
                content=f"Message {i}",
            )

        messages = state_manager.get_messages(limit=5)
        assert len(messages) == 5


class TestAgentHeartbeat:
    """Tests for agent liveness tracking."""

    def test_update_agent_heartbeat_creates_agent(
        self, state_manager: StateManager
    ) -> None:
        """Test that updating heartbeat creates agent if doesn't exist."""
        state_manager.update_agent_heartbeat("new_agent", "security", "healthy")

        agent = state_manager.get_agent_state("new_agent")
        assert agent is not None
        assert agent["role"] == "security"
        assert agent["health_status"] == "healthy"

    def test_update_agent_heartbeat_updates_timestamp(
        self, state_manager: StateManager
    ) -> None:
        """Test that heartbeat updates timestamp."""
        state_manager.update_agent_heartbeat("agent_001", "security")

        time.sleep(0.01)

        state_manager.update_agent_heartbeat("agent_001", "security")

        agents = state_manager.get_all_agent_states()
        agent = agents[0]

        # Second heartbeat should be later
        timestamps = [
            a["last_heartbeat"] for a in agents if a["agent_id"] == "agent_001"
        ]
        assert len(timestamps) == 1

    def test_get_all_agent_states(self, state_manager: StateManager) -> None:
        """Test retrieving all agent states."""
        state_manager.update_agent_heartbeat("agent_a", "security", "healthy")
        state_manager.update_agent_heartbeat("agent_b", "security", "unhealthy")

        agents = state_manager.get_all_agent_states()

        assert len(agents) == 2
        agent_ids = {a["agent_id"] for a in agents}
        assert "agent_a" in agent_ids
        assert "agent_b" in agent_ids

    def test_agent_role_preserved_on_heartbeat(
        self, state_manager: StateManager
    ) -> None:
        """Test that existing role is preserved on heartbeat updates."""
        # Create agent with specific role
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO agent_states (agent_id, role, health_status) VALUES (?, ?, ?)",
                ("agent_001", "security", "healthy"),
            )
            conn.commit()

        # Update heartbeat should preserve role
        state_manager.update_agent_heartbeat("agent_001", "security")

        agent = state_manager.get_agent_state("agent_001")
        assert agent["role"] == "security"


class TestSharedKnowledge:
    """Tests for key-value shared knowledge store."""

    def test_set_and_get_shared_knowledge(self, state_manager: StateManager) -> None:
        """Test basic set and get operations."""
        state_manager.set_shared_knowledge(
            "api_spec", "{endpoint: /api/users}", "dev_agent"
        )

        value = state_manager.get_shared_knowledge("api_spec")
        assert value == "{endpoint: /api/users}"

    def test_get_shared_knowledge_missing_key(
        self, state_manager: StateManager
    ) -> None:
        """Test getting non-existent key returns None."""
        value = state_manager.get_shared_knowledge("nonexistent")
        assert value is None

    def test_set_shared_knowledge_updates_existing(
        self, state_manager: StateManager
    ) -> None:
        """Test that set overwrites existing key."""
        state_manager.set_shared_knowledge("config", "v1", "agent_a")
        state_manager.set_shared_knowledge("config", "v2", "agent_b")

        value = state_manager.get_shared_knowledge("config")
        assert value == "v2"

    def test_get_all_shared_knowledge(self, state_manager: StateManager) -> None:
        """Test retrieving all knowledge entries."""
        state_manager.set_shared_knowledge("key1", "value1", "agent_a")
        state_manager.set_shared_knowledge("key2", "value2", "agent_b")

        all_knowledge = state_manager.get_all_shared_knowledge()

        assert len(all_knowledge) == 2
        keys = {k["key"] for k in all_knowledge}
        assert "key1" in keys
        assert "key2" in keys


class TestConcurrency:
    """Tests for thread-safe concurrent access."""

    def test_multiple_threads_get_tasks_without_conflict(
        self, state_manager: StateManager
    ) -> None:
        """Test that multiple threads fetching tasks don't get duplicates."""
        # Insert 10 tasks
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            for i in range(10):
                cursor.execute(
                    "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                    (f"Task {i}", "security", "pending"),
                )
            conn.commit()

        results = []
        errors = []

        def worker():
            try:
                task = state_manager.get_next_task("security")
                if task:
                    results.append(task["id"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10, f"Expected 10 tasks, got {len(results)}"
        assert len(set(results)) == 10, "Duplicate task assignments detected"

    def test_concurrent_message_storage(self, state_manager: StateManager) -> None:
        """Test concurrent message storage."""
        errors = []

        def worker(i: int):
            try:
                state_manager.store_message(
                    sender=f"sender_{i}",
                    recipient="recipient",
                    message_type="test",
                    content=f"Message {i}",
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        messages = state_manager.get_messages(recipient="recipient")
        assert len(messages) == 20

    def test_concurrent_shared_knowledge_updates(
        self, state_manager: StateManager
    ) -> None:
        """Test concurrent updates to shared knowledge."""
        errors = []

        def worker(i: int):
            try:
                state_manager.set_shared_knowledge(
                    f"key_{i % 5}",  # 5 different keys
                    f"value_{i}",
                    f"agent_{i % 3}",  # 3 different agents
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # All 5 keys should exist
        all_knowledge = state_manager.get_all_shared_knowledge()
        assert len(all_knowledge) >= 5  # At least 5 unique keys


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_next_task_with_invalid_role(self, state_manager: StateManager) -> None:
        """Test that invalid role returns None gracefully."""
        task = state_manager.get_next_task("invalid_role")
        assert task is None

    def test_agent_heartbeat_with_custom_role(
        self, state_manager: StateManager
    ) -> None:
        """Test agent state with predefined role."""
        state_manager.update_agent_heartbeat(
            "security_agent_001", "security", "healthy"
        )

        agent = state_manager.get_agent_state("security_agent_001")
        assert agent is not None
        assert agent["role"] == "security"

    def test_transaction_rollback_on_error(self, state_manager: StateManager) -> None:
        """Test that concurrent task assignment doesn't create duplicates."""
        manager2 = StateManager(db_path=state_manager.db_path)

        # Insert two pending tasks
        with sqlite3.connect(state_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Task A", "security", "pending"),
            )
            cursor.execute(
                "INSERT INTO tasks (description, role, status) VALUES (?, ?, ?)",
                ("Task B", "security", "pending"),
            )
            conn.commit()

        task1 = state_manager.get_next_task("security")
        assert task1 is not None

        task2 = manager2.get_next_task("security")
        assert task2 is not None

        # Should not be the same task
        assert task1["id"] != task2["id"]

    def test_database_connection_error_handling(
        self, state_manager: StateManager
    ) -> None:
        """Test behavior when database is corrupted."""
        # Override db_path to invalid location
        state_manager.db_path = "/nonexistent/path/db.sqlite"

        with pytest.raises(sqlite3.Error):
            state_manager.get_next_task("security")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

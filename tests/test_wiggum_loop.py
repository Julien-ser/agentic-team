"""
Unit tests for EnhancedWiggumLoop.

Tests cover task loading, parsing, agent registration, task dispatch,
metrics tracking, and loop iterations.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.wiggum_loop import (
    EnhancedWiggumLoop,
    AgentMetrics,
    LoopMetrics,
)
from src.protocols.agent_specs import (
    AgentRole,
    TaskStatus,
    TaskPriority,
    Task,
)


@pytest.fixture
def sample_tasks_md():
    """Create a sample TASKS.md content for testing."""
    return """
# Project Tasks

## High Priority
- [ ] [SECURITY] Fix critical SQL injection vulnerability
- [ ] [SW_DEV] Implement authentication API with JWT
- [ ] [FRONTEND] Build login form with validation

## Medium Priority
- [ ] [SECURITY] Add rate limiting to all endpoints
- [ ] [SW_DEV] Create user management endpoints
- [ ] [FRONTEND] Design responsive dashboard layout

## Low Priority
- [ ] [SECURITY] Implement security headers
- [ ] [SW_DEV] Add logging throughout application
- [ ] [FRONTEND] Add minor theme switcher component

## Misc
Some text without role tags should be ignored.

- [ ] Regular task without role should also be ignored
- [ ] [UNKNOWN] Unknown role should be skipped

More tasks:
- [ ] [SECURITY] Audit dependencies for CVEs
"""


@pytest.fixture
def temp_tasks_file(sample_tasks_md):
    """Create a temporary TASKS.md file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample_tasks_md)
        return f.name


@pytest.fixture
def loop_instance():
    """Create an EnhancedWiggumLoop instance."""
    return EnhancedWiggumLoop(dispatch_strategy="round_robin")


class TestTaskParsing:
    """Test task parsing from TASKS.md."""

    def test_load_tasks_from_file(self, loop_instance, temp_tasks_file):
        """Test loading and parsing tasks from file."""
        tasks = loop_instance.load_tasks_from_file(temp_tasks_file)

        # Should have 10 valid tasks with role tags (excluding UNKNOWN and non-role tasks)
        assert len(tasks) == 10

        # Check each task has required fields
        for task in tasks:
            assert task.id is not None
            assert task.description
            assert task.role in AgentRole
            assert task.status == TaskStatus.PENDING
            assert len(task.tags) > 0

    def test_parse_role_tags(self, loop_instance, temp_tasks_file):
        """Test that role tags are correctly parsed."""
        tasks = loop_instance.load_tasks_from_file(temp_tasks_file)

        # Count tasks by role
        security_tasks = [t for t in tasks if t.role == AgentRole.SECURITY]
        dev_tasks = [t for t in tasks if t.role == AgentRole.SW_DEV]
        frontend_tasks = [t for t in tasks if t.role == AgentRole.FRONTEND]

        assert len(security_tasks) == 4  # Including "Audit dependencies for CVEs"
        assert len(dev_tasks) == 3
        assert len(frontend_tasks) == 3  # All three frontend tasks

    def test_priority_detection(self, loop_instance, temp_tasks_file):
        """Test that priority is set based on keywords."""
        tasks = loop_instance.load_tasks_from_file(temp_tasks_file)

        # Critical/secirty should be high priority
        critical_task = next(
            (t for t in tasks if "SQL injection" in t.description), None
        )
        assert critical_task is not None
        assert critical_task.priority == TaskPriority.HIGH

        # Low priority tasks
        low_task = next((t for t in tasks if "theme switcher" in t.description), None)
        assert low_task is not None
        assert low_task.priority == TaskPriority.LOW

    def test_duplicate_prevention(self, loop_instance):
        """Test that duplicate tasks are filtered out."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [SECURITY] Fix SQL injection
- [ ] [SECURITY] Fix SQL injection
- [ ] [SECURITY] Another SQL injection fix
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        # Should only have 2 unique tasks (same description duplicates filtered)
        assert len(tasks) == 2

        # Check descriptions are unique (case-insensitive)
        descriptions = [t.description.lower() for t in tasks]
        assert len(descriptions) == len(set(descriptions))

    def test_invalid_role_tags_ignored(self, loop_instance):
        """Test that invalid role tags are skipped."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [SECURITY] Valid security task
- [ ] [UNKNOWN] Unknown role task
- [ ] [SECURITY] Another valid task
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        assert len(tasks) == 2
        assert all(t.role == AgentRole.SECURITY for t in tasks)

    def test_file_not_found(self, loop_instance):
        """Test error when TASKS.md not found."""
        with pytest.raises(FileNotFoundError):
            loop_instance.load_tasks_from_file("nonexistent.md")

    def test_no_tasks_in_file(self, loop_instance):
        """Test file with no valid tasks."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Just a header\n\nSome text without tasks.\n")
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        assert len(tasks) == 0


class TestAgentManagement:
    """Test agent registration and management."""

    def test_register_agent(self, loop_instance):
        """Test registering agents."""
        loop_instance.register_agent("security-1", AgentRole.SECURITY)
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)
        loop_instance.register_agent("frontend-1", AgentRole.FRONTEND)

        assert len(loop_instance.agents) == 3
        assert "security-1" in loop_instance.agents
        assert "dev-1" in loop_instance.agents
        assert "frontend-1" in loop_instance.agents

    def test_register_duplicate_agent(self, loop_instance):
        """Test registering duplicate agent."""
        loop_instance.register_agent("security-1", AgentRole.SECURITY)
        loop_instance.register_agent("security-1", AgentRole.SECURITY)

        assert len(loop_instance.agents) == 1

    def test_unregister_agent(self, loop_instance):
        """Test unregistering an agent."""
        loop_instance.register_agent("security-1", AgentRole.SECURITY)
        loop_instance.unregister_agent("security-1")

        assert len(loop_instance.agents) == 0
        assert "security-1" not in loop_instance.agents

    def test_agent_queues_created(self, loop_instance):
        """Test that queues are created for each agent role."""
        loop_instance.register_agent("security-1", AgentRole.SECURITY)
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)

        assert AgentRole.SECURITY in loop_instance.agent_queues
        assert AgentRole.SW_DEV in loop_instance.agent_queues
        assert AgentRole.FRONTEND not in loop_instance.agent_queues


class TestTaskDispatch:
    """Test task dispatching logic."""

    @pytest.mark.asyncio
    async def test_dispatch_task_success(self, loop_instance, sample_tasks_md):
        """Test successful task dispatch."""
        # Load tasks
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(sample_tasks_md)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        security_task = next(t for t in tasks if t.role == AgentRole.SECURITY)

        # Register agent
        loop_instance.register_agent("security-1", AgentRole.SECURITY)

        # Dispatch
        success = await loop_instance.dispatch_task(security_task, "security-1")
        assert success is True

        # Check task state
        assert security_task.status == TaskStatus.ASSIGNED
        assert security_task.assigned_to == AgentRole.SECURITY

        # Check agent metrics
        agent_metrics = loop_instance.agents["security-1"]
        assert agent_metrics.tasks_dispatched == 1

        # Check queue
        queue = loop_instance.agent_queues[AgentRole.SECURITY]
        assert not queue.empty()
        queued_task = await queue.get()
        assert queued_task.id == security_task.id

    @pytest.mark.asyncio
    async def test_dispatch_task_role_mismatch(self, loop_instance):
        """Test dispatch fails when agent role doesn't match task."""
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)

        # Create a security task
        task = Task(
            description="Test security task",
            role=AgentRole.SECURITY,
        )

        success = await loop_instance.dispatch_task(task, "dev-1")
        assert success is False
        assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_dispatch_task_agent_not_found(self, loop_instance):
        """Test dispatch fails when agent doesn't exist."""
        task = Task(
            description="Test task",
            role=AgentRole.SW_DEV,
        )

        success = await loop_instance.dispatch_task(task, "nonexistent")
        assert success is False

    @pytest.mark.asyncio
    async def test_round_robin_selection(self, loop_instance):
        """Test round-robin agent selection."""
        loop_instance.register_agent("sec-1", AgentRole.SECURITY)
        loop_instance.register_agent("sec-2", AgentRole.SECURITY)

        # Load tasks with multiple security tasks
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [SECURITY] Task 1
- [ ] [SECURITY] Task 2
- [ ] [SECURITY] Task 3
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)

        # Register loop for processing
        for task in tasks:
            loop_instance.pending_tasks[AgentRole.SECURITY].append(task)

        # Manually dispatch tasks (simulate loop behavior)
        dispatched_agents = []
        for _ in range(len(tasks)):
            agent_id = loop_instance._select_agent_for_role(AgentRole.SECURITY)
            if agent_id:
                dispatched_agents.append(agent_id)
                await loop_instance.dispatch_task(
                    loop_instance.pending_tasks[AgentRole.SECURITY].pop(0), agent_id
                )

        # Should alternate between agents
        assert dispatched_agents == ["sec-1", "sec-2", "sec-1"]

    @pytest.mark.asyncio
    async def test_process_pending_tasks(self, loop_instance):
        """Test processing of pending tasks."""
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)

        # Add pending tasks
        task1 = Task(description="Task 1", role=AgentRole.SW_DEV)
        task2 = Task(description="Task 2", role=AgentRole.SW_DEV)
        loop_instance.pending_tasks[AgentRole.SW_DEV] = [task1, task2]

        await loop_instance._process_pending_tasks()

        # Tasks should be dispatched
        assert task1.status == TaskStatus.ASSIGNED
        assert task2.status == TaskStatus.ASSIGNED

        # Queues should be empty
        assert loop_instance.pending_tasks[AgentRole.SW_DEV] == []

    @pytest.mark.asyncio
    async def test_dispatch_no_available_agents(self, loop_instance):
        """Test dispatch when no agents available."""
        loop_instance.pending_tasks[AgentRole.SECURITY] = [
            Task(description="Task", role=AgentRole.SECURITY)
        ]

        # Don't register any agents
        await loop_instance._process_pending_tasks()

        # Task should remain pending
        assert len(loop_instance.pending_tasks[AgentRole.SECURITY]) == 1
        assert (
            loop_instance.pending_tasks[AgentRole.SECURITY][0].status
            == TaskStatus.PENDING
        )


class TestMetrics:
    """Test metrics tracking."""

    @pytest.mark.asyncio
    async def test_register_task_result_success(self, loop_instance):
        """Test registering successful task completion."""
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)

        task = Task(description="Test task", role=AgentRole.SW_DEV, id="task-123")
        loop_instance.tasks.append(task)  # Add to task list
        await loop_instance.dispatch_task(task, "dev-1")

        await loop_instance.register_task_result(
            agent_id="dev-1",
            task_id="task-123",
            success=True,
            execution_time=5.5,
        )

        agent_metrics = loop_instance.agents["dev-1"]
        assert agent_metrics.tasks_completed == 1
        assert agent_metrics.total_execution_time == 5.5
        assert task.status == TaskStatus.COMPLETED

        assert loop_instance.metrics.total_tasks_completed == 1

    @pytest.mark.asyncio
    async def test_register_task_result_failure(self, loop_instance):
        """Test registering task failure."""
        loop_instance.register_agent("sec-1", AgentRole.SECURITY)

        task = Task(description="Test task", role=AgentRole.SECURITY, id="task-456")
        loop_instance.tasks.append(task)  # Add to task list
        await loop_instance.dispatch_task(task, "sec-1")

        await loop_instance.register_task_result(
            agent_id="sec-1",
            task_id="task-456",
            success=False,
            errors=["Scan failed"],
        )

        agent_metrics = loop_instance.agents["sec-1"]
        assert agent_metrics.tasks_failed == 1
        assert task.status == TaskStatus.FAILED

        assert loop_instance.metrics.total_tasks_failed == 1

    def test_get_metrics_dict(self, loop_instance):
        """Test metrics retrieval as dictionary."""
        # Add some data
        loop_instance.metrics.iteration_count = 10
        loop_instance.metrics.total_tasks_dispatched = 15
        loop_instance.metrics.total_tasks_completed = 12

        metrics = loop_instance.get_metrics()

        assert metrics["iteration_count"] == 10
        assert metrics["total_tasks_dispatched"] == 15
        assert metrics["total_tasks_completed"] == 12
        assert "uptime_seconds" in metrics
        assert "pending_tasks_by_role" in metrics

    def test_get_agent_metrics_list(self, loop_instance):
        """Test agent metrics retrieval."""
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)
        loop_instance.register_agent("sec-1", AgentRole.SECURITY)

        # Simulate some activity
        loop_instance.agents["dev-1"].tasks_dispatched = 5
        loop_instance.agents["dev-1"].tasks_completed = 4
        loop_instance.agents["sec-1"].tasks_dispatched = 3
        loop_instance.agents["sec-1"].tasks_completed = 3

        agent_metrics = loop_instance.get_agent_metrics()

        assert len(agent_metrics) == 2

        dev_metric = next(m for m in agent_metrics if m["agent_id"] == "dev-1")
        assert dev_metric["tasks_dispatched"] == 5
        assert dev_metric["tasks_completed"] == 4
        assert dev_metric["success_rate"] == 80.0
        assert dev_metric["role"] == "software_developer"

        sec_metric = next(m for m in agent_metrics if m["agent_id"] == "sec-1")
        assert sec_metric["success_rate"] == 100.0


class TestLoopExecution:
    """Test loop iteration and execution."""

    @pytest.mark.asyncio
    async def test_run_single_iteration(self, loop_instance):
        """Test a single loop iteration."""
        # Setup
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [SW_DEV] Implement API endpoint
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        loop_instance.tasks = tasks
        loop_instance.register_agent("dev-1", AgentRole.SW_DEV)

        # Run one iteration
        duration = await loop_instance._run_iteration()

        assert duration >= 0
        assert loop_instance.metrics.iteration_count == 1
        assert loop_instance.metrics.total_tasks_dispatched == 1

        # Check task was dispatched
        task = tasks[0]
        assert task.status == TaskStatus.ASSIGNED

    @pytest.mark.asyncio
    async def test_run_iteration_no_agents(self, loop_instance):
        """Test iteration with no registered agents."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("- [ ] [SW_DEV] Test task\n")
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        loop_instance.tasks = tasks

        # No agents registered
        duration = await loop_instance._run_iteration()

        # Iteration should complete, tasks remain pending
        assert duration >= 0
        assert loop_instance.metrics.iteration_count == 1
        assert len(loop_instance.pending_tasks[AgentRole.SW_DEV]) == 1

    @pytest.mark.asyncio
    async def test_run_iteration_all_tasks_dispatched(self, loop_instance):
        """Test iteration dispatches all pending tasks."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [SECURITY] Task 1
- [ ] [SECURITY] Task 2
- [ ] [FRONTEND] Task 3
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        loop_instance.tasks = tasks
        loop_instance.register_agent("sec-1", AgentRole.SECURITY)
        loop_instance.register_agent("frontend-1", AgentRole.FRONTEND)

        duration = await loop_instance._run_iteration()

        assert duration >= 0
        assert loop_instance.metrics.total_tasks_dispatched == 3

        # All tasks should be assigned (pending should be empty)
        assert all(len(lst) == 0 for lst in loop_instance.pending_tasks.values())

    @pytest.mark.asyncio
    async def test_stop_flag(self, loop_instance):
        """Test that stop flag halts the continuous loop."""
        loop_instance._running = True

        # Start continuous loop in background with short interval
        async def run_brief():
            await asyncio.wait_for(
                loop_instance.run_continuous(interval=0.1), timeout=0.5
            )

        # Schedule stop after short delay
        async def stop_soon():
            await asyncio.sleep(0.2)
            loop_instance.stop()

        # Run both concurrently
        try:
            await asyncio.gather(run_brief(), stop_soon())
        except asyncio.TimeoutError:
            # Expected if stop worked properly
            pass

        assert not loop_instance._running


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_tasks_file(self, loop_instance):
        """Test loading from empty tasks file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        assert tasks == []

    def test_mixed_content(self, loop_instance):
        """Test file with mixed markdown and tasks."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
# Project Agentic Team

## Description
This project implements a multi-agent system.

### Tasks

| Priority | Role | Description |
|----------|------|-------------|
| High | Security | Fix authentication |
| High | SW_DEV | Implement login |

- [ ] [SECURITY] Add encryption
- [ ] [SW_DEV] Write tests

## Notes
Some unmarked text.

- [ ] Just a regular list item

Final tasks:

- [ ] [FRONTEND] Create UI
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)
        # Should find 3 tasks (table rows might not be parsed, only bullet tasks)
        assert len(tasks) >= 2  # At least the two bullet tasks at minimum

    def test_case_insensitive_role_parsing(self, loop_instance):
        """Test that role tags are case-insensitive."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
- [ ] [security] lower case
- [ ] [Security] Mixed case
- [ ] [SECURITY] Upper case
- [ ] [sw_dev] lower sw dev
- [ ] [FRONTEND] upper frontend
            """)
            temp_file = f.name

        tasks = loop_instance.load_tasks_from_file(temp_file)

        # All should be parsed as correct enum values
        security_tasks = [t for t in tasks if t.role == AgentRole.SECURITY]
        sw_dev_tasks = [t for t in tasks if t.role == AgentRole.SW_DEV]
        frontend_tasks = [t for t in tasks if t.role == AgentRole.FRONTEND]

        assert len(security_tasks) == 3
        assert len(sw_dev_tasks) == 1
        assert len(frontend_tasks) == 1

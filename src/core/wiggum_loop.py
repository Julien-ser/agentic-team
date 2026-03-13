"""
Enhanced Wiggum Loop with role-based agent selection.

This module implements the core orchestration loop that reads tasks from TASKS.md,
parses role tags, and dispatches tasks to appropriate specialized agents.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.config import config
from src.protocols.agent_specs import (
    AgentRole,
    Task as TaskModel,
    TaskStatus,
    TaskPriority,
    AgentMessage,
    MessageType,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentMetrics:
    """Performance metrics for an agent."""

    agent_id: str
    role: AgentRole
    tasks_dispatched: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    last_heartbeat: Optional[datetime] = None
    is_healthy: bool = True


@dataclass
class LoopMetrics:
    """Overall loop performance metrics."""

    iteration_count: int = 0
    total_tasks_dispatched: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    start_time: datetime = field(default_factory=datetime.utcnow)
    avg_iteration_time: float = 0.0
    tasks_per_second: float = 0.0


class EnhancedWiggumLoop:
    """
    Main orchestration loop with role-based task dispatch.

    Features:
    - Parses TASKS.md to extract role-tagged tasks
    - Maps tasks to appropriate agents based on role
    - Supports round-robin or priority-based dispatch
    - Tracks agent performance and system metrics
    - Runs continuously with asyncio
    """

    # Regex pattern to match role tags: [SECURITY], [SW_DEV], [FRONTEND]
    # Supports markdown task list format: - [ ] [ROLE] description
    TASK_TAG_PATTERN = re.compile(
        r"^\s*(?:[-*]\s*(?:\[.\]?\])?\s*)?\[(SECURITY|SW_DEV|FRONTEND)\]\s*(.+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        tasks_file: str = "TASKS.md",
        dispatch_strategy: str = "round_robin",
    ):
        """
        Initialize the enhanced wiggum loop.

        Args:
            tasks_file: Path to TASKS.md file
            dispatch_strategy: "round_robin" or "priority"
        """
        self.tasks_file = Path(tasks_file)
        self.dispatch_strategy = dispatch_strategy

        # Task management
        self.tasks: List[TaskModel] = []
        self.pending_tasks: Dict[AgentRole, List[TaskModel]] = {
            AgentRole.SECURITY: [],
            AgentRole.SW_DEV: [],
            AgentRole.FRONTEND: [],
        }
        self.completed_tasks: List[TaskModel] = []
        self.failed_tasks: List[TaskModel] = []

        # Agent management
        self.agents: Dict[str, AgentMetrics] = {}  # agent_id -> metrics
        self.agent_queues: Dict[AgentRole, asyncio.Queue] = {}

        # Metrics
        self.metrics = LoopMetrics()

        # State
        self._running = False
        self._iteration_lock = asyncio.Lock()
        self._last_dispatch_index: Dict[AgentRole, int] = {
            AgentRole.SECURITY: 0,
            AgentRole.SW_DEV: 0,
            AgentRole.FRONTEND: 0,
        }

        logger.info(f"EnhancedWiggumLoop initialized with {dispatch_strategy} dispatch")

    def load_tasks_from_file(self, file_path: Optional[str] = None) -> List[TaskModel]:
        """
        Parse TASKS.md and extract tasks with role tags.

        Args:
            file_path: Optional path to tasks file. If None, uses self.tasks_file.

        Returns:
            List of TaskModel objects with role assignments

        Raises:
            FileNotFoundError: If TASKS.md not found
            ValueError: If task parsing fails
        """
        tasks_file = Path(file_path) if file_path else self.tasks_file
        if not tasks_file.exists():
            raise FileNotFoundError(f"Tasks file not found: {tasks_file}")

        logger.info(f"Loading tasks from {tasks_file}")

        with open(tasks_file, "r", encoding="utf-8") as f:
            content = f.read()

        tasks = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            match = self.TASK_TAG_PATTERN.match(line)

            if match:
                role_str, description = match.groups()
                role_str = role_str.upper()

                # Map role string to AgentRole enum
                role_mapping = {
                    "SECURITY": AgentRole.SECURITY,
                    "SW_DEV": AgentRole.SW_DEV,
                    "FRONTEND": AgentRole.FRONTEND,
                }

                if role_str not in role_mapping:
                    logger.warning(
                        f"Line {line_num}: Unknown role '{role_str}', skipping"
                    )
                    continue

                role = role_mapping[role_str]

                # Determine priority based on task content
                priority = TaskPriority.MEDIUM
                if any(
                    keyword in description.lower()
                    for keyword in ["critical", "urgent", "security"]
                ):
                    priority = TaskPriority.HIGH
                elif any(
                    keyword in description.lower() for keyword in ["low", "minor"]
                ):
                    priority = TaskPriority.LOW

                # Check if task is already in the file (avoid duplicates)
                task_desc_lower = description.lower()
                if any(
                    task_desc_lower in existing.description.lower()
                    for existing in tasks
                ):
                    logger.debug(
                        f"Line {line_num}: Duplicate task '{description}', skipping"
                    )
                    continue

                task = TaskModel(
                    description=description,
                    role=role,
                    priority=priority,
                    status=TaskStatus.PENDING,
                    tags=[role_str.lower()],
                )
                tasks.append(task)
                logger.debug(f"Parsed task: [{role.value}] {description}")

        logger.info(f"Successfully loaded {len(tasks)} tasks")
        return tasks

    def register_agent(self, agent_id: str, role: AgentRole):
        """
        Register an agent with the loop.

        Args:
            agent_id: Unique identifier for the agent
            role: Agent's role (SECURITY, SW_DEV, FRONTEND)
        """
        if agent_id in self.agents:
            logger.warning(f"Agent {agent_id} already registered, skipping")
            return

        self.agents[agent_id] = AgentMetrics(
            agent_id=agent_id,
            role=role,
        )

        # Create queue for the agent's role if not exists
        if role not in self.agent_queues:
            self.agent_queues[role] = asyncio.Queue()

        logger.info(f"Registered agent {agent_id} with role {role.value}")

    def unregister_agent(self, agent_id: str):
        """Unregister an agent from the loop."""
        if agent_id in self.agents:
            role = self.agents[agent_id].role
            del self.agents[agent_id]
            logger.info(f"Unregistered agent {agent_id} from role {role.value}")

    async def dispatch_task(self, task: TaskModel, agent_id: str) -> bool:
        """
        Dispatch a task to a specific agent.

        Args:
            task: The task to dispatch
            agent_id: Target agent ID

        Returns:
            True if task was dispatched successfully
        """
        if agent_id not in self.agents:
            logger.error(
                f"Cannot dispatch task {task.id[:8]}: Agent {agent_id} not found"
            )
            return False

        agent_metrics = self.agents[agent_id]

        # Check if agent's role matches task role
        if agent_metrics.role != task.role:
            logger.error(
                f"Role mismatch: task requires {task.role.value}, "
                f"agent {agent_id} has role {agent_metrics.role.value}"
            )
            return False

        # Put task in agent's queue
        role_queue = self.agent_queues.get(task.role)
        if role_queue is None:
            logger.error(f"No queue found for role {task.role.value}")
            return False

        await role_queue.put(task)

        # Update metrics
        task.status = TaskStatus.ASSIGNED
        task.assigned_to = agent_metrics.role
        task.assigned_at = datetime.utcnow()
        agent_metrics.tasks_dispatched += 1
        self.metrics.total_tasks_dispatched += 1

        logger.info(
            f"Dispatched task {task.id[:8]} to agent {agent_id} "
            f"(role: {task.role.value})"
        )
        return True

    def _select_agent_for_role(self, role: AgentRole) -> Optional[str]:
        """
        Select an agent for a given role using configured dispatch strategy.

        Args:
            role: The required agent role

        Returns:
            Agent ID or None if no suitable agent available
        """
        # Get all agents with matching role
        available_agents = [
            agent_id
            for agent_id, metrics in self.agents.items()
            if metrics.role == role and metrics.is_healthy
        ]

        if not available_agents:
            logger.warning(f"No healthy agents available for role {role.value}")
            return None

        if self.dispatch_strategy == "round_robin":
            # Round-robin selection
            index = self._last_dispatch_index[role]
            selected_agent = available_agents[index % len(available_agents)]
            self._last_dispatch_index[role] = (index + 1) % len(available_agents)
            return selected_agent
        else:
            # Default: pick first available (could be extended with priority)
            return available_agents[0]

    async def _process_pending_tasks(self):
        """Process pending tasks and dispatch to appropriate agents."""
        tasks_to_dispatch = []

        # Collect tasks from all roles
        for role in AgentRole:
            role_tasks = self.pending_tasks[role]
            while role_tasks:
                task = role_tasks.pop(0)
                tasks_to_dispatch.append(task)

        # Dispatch tasks to agents
        for task in tasks_to_dispatch:
            agent_id = self._select_agent_for_role(task.role)
            if agent_id:
                await self.dispatch_task(task, agent_id)
            else:
                # No agent available, put back in pending
                self.pending_tasks[task.role].append(task)
                logger.warning(
                    f"Could not dispatch task {task.id[:8]}, "
                    f"no agent available for role {task.role.value}"
                )

    async def _update_agent_heartbeat(self, agent_id: str, is_healthy: bool = True):
        """Update agent heartbeat and health status."""
        if agent_id in self.agents:
            self.agents[agent_id].last_heartbeat = datetime.utcnow()
            self.agents[agent_id].is_healthy = is_healthy

    async def register_task_result(
        self,
        agent_id: str,
        task_id: str,
        success: bool,
        execution_time: float = 0.0,
        errors: Optional[List[str]] = None,
    ):
        """
        Register the result of a completed task.

        Args:
            agent_id: Agent that completed the task
            task_id: ID of completed task
            success: Whether task completed successfully
            execution_time: Time taken to execute task (seconds)
            errors: List of error messages if failed
        """
        # Find task
        task = None
        for t in self.tasks:
            if t.id == task_id:
                task = t
                break

        if task is None:
            logger.error(f"Cannot register result: Task {task_id[:8]} not found")
            return

        if agent_id not in self.agents:
            logger.error(f"Cannot register result: Agent {agent_id} not found")
            return

        agent_metrics = self.agents[agent_id]

        if success:
            task.mark_completed()
            self.completed_tasks.append(task)
            agent_metrics.tasks_completed += 1
            self.metrics.total_tasks_completed += 1
        else:
            task.mark_failed()
            self.failed_tasks.append(task)
            agent_metrics.tasks_failed += 1
            self.metrics.total_tasks_failed += 1

        if execution_time > 0:
            agent_metrics.total_execution_time += execution_time

        # Remove from pending if still there
        if task.role in self.pending_tasks:
            role_tasks = self.pending_tasks[task.role]
            if task in role_tasks:
                role_tasks.remove(task)

        logger.info(
            f"Task {task_id[:8]} {'completed' if success else 'failed'} "
            f"by agent {agent_id} (duration: {execution_time:.2f}s)"
        )

    async def _run_iteration(self) -> float:
        """
        Run a single iteration of the wiggum loop.

        Returns:
            Duration of iteration in seconds
        """
        start_time = datetime.utcnow()

        async with self._iteration_lock:
            self.metrics.iteration_count += 1

            # Update pending tasks from loaded tasks
            for task in self.tasks:
                if task.status == TaskStatus.PENDING:
                    if task not in self.pending_tasks[task.role]:
                        self.pending_tasks[task.role].append(task)

            # Process and dispatch pending tasks
            await self._process_pending_tasks()

            # Check for timed-out tasks (optional)
            current_time = datetime.utcnow()
            timeout_threshold = 3600  # 1 hour

            for role_tasks in self.pending_tasks.values():
                for task in role_tasks:
                    if task.assigned_at:
                        elapsed = (current_time - task.assigned_at).total_seconds()
                        if elapsed > timeout_threshold:
                            logger.warning(
                                f"Task {task.id[:8]} has been assigned for "
                                f"{elapsed:.0f}s, may need reassignment"
                            )

            iteration_duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.avg_iteration_time = (
                self.metrics.avg_iteration_time * (self.metrics.iteration_count - 1)
                + iteration_duration
            ) / self.metrics.iteration_count

            # Update tasks per second
            elapsed_total = (
                datetime.utcnow() - self.metrics.start_time
            ).total_seconds()
            if elapsed_total > 0:
                self.metrics.tasks_per_second = (
                    self.metrics.total_tasks_dispatched / elapsed_total
                )

            return iteration_duration

    async def run_continuous(self, interval: float = 1.0):
        """
        Run the wiggum loop continuously.

        Args:
            interval: Minimum seconds between iterations
        """
        self._running = True
        logger.info(
            f"Starting EnhancedWiggumLoop (interval={interval}s, "
            f"strategy={self.dispatch_strategy})"
        )

        try:
            while self._running:
                iteration_start = datetime.utcnow()

                try:
                    iteration_time = await self._run_iteration()
                    logger.debug(
                        f"Iteration {self.metrics.iteration_count} completed "
                        f"in {iteration_time:.3f}s "
                        f"(dispatched: {self.metrics.total_tasks_dispatched}, "
                        f"completed: {self.metrics.total_tasks_completed})"
                    )
                except Exception as e:
                    logger.error(f"Error in iteration: {e}", exc_info=True)

                # Sleep for the remainder of the interval
                elapsed = (datetime.utcnow() - iteration_start).total_seconds()
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("EnhancedWiggumLoop cancelled")
            self._running = False
        except Exception as e:
            logger.error(f"Fatal error in EnhancedWiggumLoop: {e}", exc_info=True)
            self._running = False
            raise

    def stop(self):
        """Stop the running loop."""
        self._running = False
        logger.info("EnhancedWiggumLoop stop requested")

    def get_metrics(self) -> Dict:
        """Get current metrics as dictionary."""
        return {
            "iteration_count": self.metrics.iteration_count,
            "total_tasks_dispatched": self.metrics.total_tasks_dispatched,
            "total_tasks_completed": self.metrics.total_tasks_completed,
            "total_tasks_failed": self.metrics.total_tasks_failed,
            "uptime_seconds": (
                datetime.utcnow() - self.metrics.start_time
            ).total_seconds(),
            "avg_iteration_time": self.metrics.avg_iteration_time,
            "tasks_per_second": self.metrics.tasks_per_second,
            "registered_agents": len(self.agents),
            "pending_tasks_by_role": {
                role.value: len(tasks) for role, tasks in self.pending_tasks.items()
            },
        }

    def get_agent_metrics(self) -> List[Dict]:
        """Get metrics for all registered agents."""
        return [
            {
                "agent_id": m.agent_id,
                "role": m.role.value,
                "tasks_dispatched": m.tasks_dispatched,
                "tasks_completed": m.tasks_completed,
                "tasks_failed": m.tasks_failed,
                "success_rate": (m.tasks_completed / (m.tasks_dispatched or 1) * 100),
                "avg_execution_time": (
                    m.total_execution_time / (m.tasks_dispatched or 1)
                ),
                "is_healthy": m.is_healthy,
                "last_heartbeat": m.last_heartbeat.isoformat()
                if m.last_heartbeat
                else None,
            }
            for m in self.agents.values()
        ]

"""
Web Dashboard for monitoring Agentic Team activity.

Provides real-time visibility into agent states, task queues,
message throughput, and system health.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from flask import Flask, jsonify, render_template, Response, request
import threading

from src.config import config
from src.state.state_manager import StateManager

# Initialize Flask app
app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)

# Initialize StateManager
state_manager = StateManager(config.SQLITE_PATH)


@app.route("/")
def dashboard():
    """Render main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/agents")
def get_agents():
    """
    Get all agent states with health information.

    Returns:
        List of agent states with current status, last heartbeat, and tasks
    """
    try:
        agent_states = state_manager.get_all_agent_states()
        conn = state_manager._get_connection()
        cursor = conn.cursor()

        # Enrich with task counts
        for agent in agent_states:
            # Get task count by status for this agent
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM tasks
                WHERE assigned_to = ?
                GROUP BY status
                """,
                (agent["agent_id"],),
            )
            task_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

            agent["task_counts"] = task_counts
            agent["total_tasks"] = sum(task_counts.values())

            # Calculate health based on heartbeat
            last_heartbeat = datetime.fromisoformat(agent["last_heartbeat"])
            age_seconds = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
            agent["heartbeat_age_seconds"] = age_seconds
            agent["is_healthy"] = age_seconds < (config.AGENT_HEARTBEAT_INTERVAL * 3)

        conn.close()
        return jsonify(agent_states)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks")
def get_tasks():
    """
    Get task queue organized by role and status.

    Query params:
        role: Filter by agent role (optional)
        status: Filter by task status (optional)

    Returns:
        List of tasks grouped by role/status with counts
    """
    try:
        role = request.args.get("role")
        status = request.args.get("status")

        tasks = []

        if role:
            # Get tasks for specific role
            tasks = state_manager.get_tasks_by_status(status or "pending")
            tasks = [t for t in tasks if t["role"] == role]
        else:
            # Get all tasks
            tasks = (
                state_manager.get_tasks_by_status(status or "pending") if status else []
            )

            # Also get pending tasks for each role
            if not status:
                pending_tasks_security = state_manager.get_pending_tasks("security")
                pending_tasks_dev = state_manager.get_pending_tasks(
                    "software_developer"
                )
                pending_tasks_frontend = state_manager.get_pending_tasks(
                    "frontend_developer"
                )
                tasks.extend(pending_tasks_security)
                tasks.extend(pending_tasks_dev)
                tasks.extend(pending_tasks_frontend)

        # Sort by creation time
        tasks.sort(key=lambda t: t["created_at"], reverse=True)

        return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/messages")
def get_messages():
    """
    Get recent A2A messages.

    Query params:
        limit: Maximum number of messages (default 50)
        sender: Filter by sender role (optional)
        recipient: Filter by recipient role (optional)

    Returns:
        List of messages ordered by timestamp descending
    """
    try:
        limit = int(request.args.get("limit", 50))
        sender = request.args.get("sender")
        recipient = request.args.get("recipient")

        messages = state_manager.get_messages(
            recipient=recipient, sender=sender, limit=limit
        )

        return jsonify(messages)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics")
def get_metrics():
    """
    Get system performance metrics.

    Returns:
        Dictionary with metrics including:
        - total_tasks_completed
        - total_messages_sent
        - active_agents
        - messages_per_second
        - tasks_per_minute
    """
    try:
        with state_manager._get_connection() as conn:
            cursor = conn.cursor()

            # Task metrics
            cursor.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE status = 'completed'"
            )
            total_tasks_completed = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE status IN ('pending', 'assigned')"
            )
            active_tasks = cursor.fetchone()["count"]

            # Message metrics
            cursor.execute("SELECT COUNT(*) as count FROM messages")
            total_messages = cursor.fetchone()["count"]

            # Agent metrics
            cursor.execute("SELECT COUNT(*) as count FROM agent_states")
            total_agents = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM agent_states WHERE health_status = 'healthy'"
            )
            healthy_agents = cursor.fetchone()["count"]

            # Calculate message rate (messages in last minute)
            timestamp_1min_ago = datetime.now(timezone.utc).timestamp() - 60
            cursor.execute(
                "SELECT COUNT(*) as count FROM messages WHERE timestamp > ?",
                (
                    datetime.fromtimestamp(
                        timestamp_1min_ago, tz=timezone.utc
                    ).isoformat(),
                ),
            )
            messages_last_minute = cursor.fetchone()["count"]
            messages_per_second = (
                messages_last_minute / 60.0 if messages_last_minute > 0 else 0
            )

            # Calculate task completion rate
            timestamp_1hour_ago = datetime.now(timezone.utc).timestamp() - 3600
            cursor.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE completed_at > ?",
                (
                    datetime.fromtimestamp(
                        timestamp_1hour_ago, tz=timezone.utc
                    ).isoformat(),
                ),
            )
            tasks_last_hour = cursor.fetchone()["count"]
            tasks_per_minute = tasks_last_hour / 60.0 if tasks_last_hour > 0 else 0

            # Agent heartbeats
            recent_cutoff = (
                datetime.now(timezone.utc).timestamp()
                - config.AGENT_HEARTBEAT_INTERVAL * 2
            )
            cursor.execute(
                "SELECT COUNT(*) as count FROM agent_states WHERE last_heartbeat > ?",
                (datetime.fromtimestamp(recent_cutoff, tz=timezone.utc).isoformat(),),
            )
            active_agents = cursor.fetchone()["count"]

            metrics = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tasks": {
                    "total_completed": total_tasks_completed,
                    "active": active_tasks,
                    "completion_rate_per_minute": round(tasks_per_minute, 2),
                },
                "messages": {
                    "total_sent": total_messages,
                    "rate_per_second": round(messages_per_second, 2),
                    "last_minute": messages_last_minute,
                },
                "agents": {
                    "total": total_agents,
                    "active": active_agents,
                    "healthy": healthy_agents,
                },
            }

            return jsonify(metrics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue/<role>")
def get_queue_for_role(role: str):
    """
    Get pending task queue for a specific agent role.

    Args:
        role: Agent role (security, software_developer, frontend_developer)

    Returns:
        List of pending tasks for the role
    """
    try:
        pending_tasks = state_manager.get_pending_tasks(role)
        return jsonify(pending_tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/shared-knowledge")
def get_shared_knowledge():
    """
    Get all shared knowledge entries.

    Returns:
        List of key-value pairs with metadata
    """
    try:
        knowledge = state_manager.get_all_shared_knowledge()
        return jsonify(knowledge)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_check():
    """Simple health check endpoint."""
    try:
        # Test database connection
        state_manager._get_connection().close()
        return jsonify(
            {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
        )
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


# SSE endpoint for real-time updates
@app.route("/api/events")
def events():
    """
    Server-Sent Events endpoint for real-time dashboard updates.

    Streams system events including:
    - agent_heartbeat
    - new_message
    - task_update
    """

    def generate():
        # Note: This is a simple implementation
        # In production, you'd want to use Redis pub/sub or similar
        while True:
            try:
                # Poll for changes every 2 seconds
                time.sleep(2)

                # Get current metrics
                cursor = state_manager._get_connection().cursor()
                cursor.execute("SELECT COUNT(*) as count FROM messages")
                msg_count = cursor.fetchone()["count"]

                cursor.execute(
                    "SELECT COUNT(*) as count FROM agent_states WHERE health_status = 'healthy'"
                )
                healthy_agents = cursor.fetchone()["count"]

                event_data = {
                    "messages_total": msg_count,
                    "healthy_agents": healthy_agents,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                yield f"data: {json.dumps(event_data)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"
                break

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print(f"Starting dashboard on {config.FLASK_HOST}:{config.FLASK_PORT}")
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        threaded=True,
    )

"""
Database migration script for agentic-team.

Initializes the SQLite database with all required tables.
Run with: python -m src.state.migrate
"""

import sqlite3
import sys
from pathlib import Path

from .schema import CREATE_TABLES_SQL, CREATE_INDEXES_SQL


def get_db_path() -> Path:
    """Get the database file path."""
    # Database stored in project root
    project_root = Path(__file__).parent.parent.parent
    return project_root / "agentic_team.db"


def initialize_database() -> None:
    """Create all tables if they don't exist."""
    db_path = get_db_path()
    conn = None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute all table creation statements
        cursor.executescript(CREATE_TABLES_SQL)
        cursor.executescript(CREATE_INDEXES_SQL)

        conn.commit()
        print(f"✅ Database initialized at {db_path}")

        # Verify tables were created
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = cursor.fetchall()
        print(f"📊 Created tables: {', '.join([t[0] for t in tables])}")

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()


def verify_schema() -> bool:
    """Verify all expected tables exist."""
    db_path = get_db_path()
    conn = None

    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return False

    expected_tables = {"tasks", "messages", "agent_states", "shared_knowledge"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cursor.fetchall()}

        missing = expected_tables - existing
        if missing:
            print(f"❌ Missing tables: {', '.join(missing)}")
            return False

        print(f"✅ All expected tables exist")
        return True

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Initializing agentic-team database...")
    initialize_database()
    verify_schema()

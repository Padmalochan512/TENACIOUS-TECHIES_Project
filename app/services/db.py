import sqlite3
from pathlib import Path
from typing import Generator
from app.config import settings

def get_db_path() -> Path:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings.database_path

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    # High-efficiency SQLite PRAGMAs
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;")
    cursor.execute("PRAGMA temp_store=MEMORY;")

    # Support Tickets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            customer_id TEXT NOT NULL,
            order_id TEXT,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            summary TEXT NOT NULL,
            requires_human_approval INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets (customer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_idempotency ON tickets (idempotency_key)")

    # Workflow runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            workflow_id TEXT PRIMARY KEY,
            workflow_type TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            order_id TEXT,
            input_text TEXT NOT NULL,
            classification TEXT NOT NULL,
            calculated_priority TEXT NOT NULL,
            ticket_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Conversation sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            last_order_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Conversation messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tool_calls_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON conversation_messages (session_id, id DESC)")

    conn.commit()
    conn.close()

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

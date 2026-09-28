import json
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services.db import get_db_connection
from app.observability.logging import logger

ORDER_ID_PATTERN = re.compile(r"\bORD-\d{4,}\b", re.IGNORECASE)

class SessionMemory:
    def __init__(self, max_messages: Optional[int] = None):
        self.max_messages = max_messages or settings.session_memory_max_messages

    def get_or_create_session(self, session_id: Optional[str], customer_id: str) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()

        if session_id:
            cursor.execute("SELECT session_id, customer_id, last_order_id FROM conversation_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return session_id

        # Generate new session ID
        new_session_id = session_id or f"sess-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO conversation_sessions (session_id, customer_id, last_order_id, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?)
        """, (new_session_id, customer_id, now, now))
        conn.commit()
        conn.close()
        return new_session_id

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None

        cursor.execute("""
            INSERT INTO conversation_messages (session_id, role, content, tool_calls_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, tool_calls_json, now))

        # Check if content references an order ID and update session's last_order_id
        order_match = ORDER_ID_PATTERN.search(content)
        if order_match:
            found_order_id = order_match.group(0).upper()
            cursor.execute("""
                UPDATE conversation_sessions
                SET last_order_id = ?, updated_at = ?
                WHERE session_id = ?
            """, (found_order_id, now, session_id))
        else:
            cursor.execute("""
                UPDATE conversation_sessions
                SET updated_at = ?
                WHERE session_id = ?
            """, (now, session_id))

        conn.commit()
        conn.close()

    def get_recent_messages(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        n = limit or self.max_messages
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content, tool_calls_json, created_at
            FROM conversation_messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (session_id, n))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for r in reversed(rows):
            msg = {
                "role": r["role"],
                "content": r["content"],
            }
            if r["tool_calls_json"]:
                msg["tool_calls"] = json.loads(r["tool_calls_json"])
            messages.append(msg)
        return messages

    def get_last_order_id(self, session_id: str) -> Optional[str]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT last_order_id FROM conversation_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        return row["last_order_id"] if row and row["last_order_id"] else None

    def set_last_order_id(self, session_id: str, order_id: str) -> None:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE conversation_sessions
            SET last_order_id = ?, updated_at = ?
            WHERE session_id = ?
        """, (order_id.upper(), now, session_id))
        conn.commit()
        conn.close()

session_memory = SessionMemory()

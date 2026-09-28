import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.services.db import get_db_connection
from app.observability.logging import logger

def compute_idempotency_key(customer_id: str, order_id: Optional[str], category: str, summary: str) -> str:
    normalized_summary = " ".join((summary or "").strip().lower().split())
    raw_str = f"{customer_id}|{order_id or ''}|{category.lower()}|{normalized_summary}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

def compute_deterministic_priority(
    category: str,
    sentiment: str,
    urgency: str,
    summary: str = "",
    order_status: Optional[str] = None
) -> str:
    """
    App-side deterministic rule system for computing ticket priority.
    """
    cat_lower = category.lower()
    sent_lower = sentiment.lower()
    urg_lower = urgency.lower()
    sum_lower = summary.lower()

    # Rule 1: Payment deducted with failed order or explicit money deducted issue is always HIGH
    if ("payment" in cat_lower or "refund" in cat_lower) and (
        order_status == "payment_failed" or "deducted" in sum_lower or "charged" in sum_lower or "failed" in sum_lower
    ):
        return "High"

    # Rule 2: High urgency or angry sentiment with order/delivery issues -> High
    if (urg_lower == "high" or sent_lower == "angry") and cat_lower in ["payment", "refund", "delivery", "order"]:
        return "High"

    # Rule 3: High urgency alone
    if urg_lower == "high":
        return "High"

    # Rule 4: Angry sentiment alone -> High
    if sent_lower == "angry":
        return "High"

    # Rule 5: Medium urgency or negative sentiment on operational issues -> Medium
    if urg_lower == "medium" or sent_lower == "negative" or cat_lower in ["payment", "refund", "delivery"]:
        return "Medium"

    # Default fallback
    return "Low"

class Ticket(BaseModel):
    ticket_id: str
    idempotency_key: str
    customer_id: str
    order_id: Optional[str] = None
    category: str
    priority: str
    summary: str
    requires_human_approval: bool = False
    status: str = "open"
    created_at: str
    updated_at: str

class TicketService:
    def create_ticket(
        self,
        customer_id: str,
        category: str,
        priority: str,
        summary: str,
        order_id: Optional[str] = None,
        requires_human_approval: bool = False
    ) -> Dict[str, Any]:
        idempotency_key = compute_idempotency_key(customer_id, order_id, category, summary)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if already exists
        cursor.execute("SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,))
        row = cursor.fetchone()
        if row:
            conn.close()
            logger.info(f"Duplicate ticket prevented. Returning existing ticket {row['ticket_id']}")
            return dict(row)

        ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO tickets (ticket_id, idempotency_key, customer_id, order_id, category, priority, summary, requires_human_approval, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket_id,
            idempotency_key,
            customer_id,
            order_id,
            category,
            priority,
            summary,
            1 if requires_human_approval else 0,
            "open",
            now,
            now
        ))
        conn.commit()
        
        cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        created = cursor.fetchone()
        conn.close()
        
        logger.info(f"Created new support ticket {ticket_id} for customer {customer_id} with priority {priority}")
        return dict(created)

    def get_tickets(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        if customer_id:
            cursor.execute("SELECT * FROM tickets WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,))
        else:
            cursor.execute("SELECT * FROM tickets ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

ticket_service = TicketService()

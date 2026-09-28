import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.agent.schemas import (
    ComplaintClassification,
    ComplaintCategory,
    SentimentEnum,
    UrgencyEnum,
    ComplaintWorkflowRequest,
    ComplaintWorkflowResponse
)
from app.services.ticket_service import (
    ticket_service,
    compute_idempotency_key,
    compute_deterministic_priority
)
from app.services.order_service import order_service
from app.services.db import get_db_connection
from app.llm import get_llm_client
from app.llm.base import LLMClient
from app.observability.logging import logger

SAFE_DEFAULT_CLASSIFICATION = ComplaintClassification(
    category=ComplaintCategory.OTHER,
    sentiment=SentimentEnum.NEUTRAL,
    urgency=UrgencyEnum.MEDIUM,
    summary="Unclassified customer inquiry (fallback default)",
    confidence=0.5,
    needs_escalation=True
)

class ComplaintWorkflow:
    def __init__(self, llm_client: Optional[LLMClient] = None, log_file: Optional[Path] = None):
        self._custom_llm_client = llm_client
        self.log_file = log_file or settings.workflow_log_path
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def get_client(self) -> LLMClient:
        return self._custom_llm_client or get_llm_client()

    def classify_complaint_with_fallback(self, complaint_text: str) -> ComplaintClassification:
        client = self.get_client()
        prompt = complaint_text.strip()

        for attempt in range(2):
            try:
                result = client.structured_output(
                    prompt=prompt,
                    response_model=ComplaintClassification,
                    system_instruction=(
                        "You are an expert customer operations classifier. "
                        "Categorize issues accurately and gauge emotional urgency."
                    )
                )
                return result
            except Exception as e:
                logger.warning(f"Complaint classification attempt {attempt+1} failed: {e}")
                if attempt == 1:
                    logger.error("Using safe fallback classification.")
                    return ComplaintClassification(
                        category=ComplaintCategory.OTHER,
                        sentiment=SentimentEnum.NEUTRAL,
                        urgency=UrgencyEnum.MEDIUM,
                        summary=complaint_text[:120].strip() or "Customer complaint",
                        confidence=0.5,
                        needs_escalation=True
                    )

        return SAFE_DEFAULT_CLASSIFICATION

    def simulate_notification(self, ticket_id: str, priority: str, category: str, customer_id: str) -> Dict[str, Any]:
        """
        Simulates sending an urgent dispatch email/webhook to on-call restaurant operations team.
        """
        notification_payload = {
            "channel": "slack_ops_alert" if priority == "High" else "email_support_queue",
            "recipient": "ops-escalations@restaurant.local" if priority == "High" else "support@restaurant.local",
            "subject": f"[{priority.upper()}] Support Ticket Alert {ticket_id} ({category})",
            "customer_id": customer_id,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
            "status": "delivered_to_stub"
        }
        logger.info(f"Simulated notification dispatch: {notification_payload}")
        return notification_payload

    def run(self, request: ComplaintWorkflowRequest) -> ComplaintWorkflowResponse:
        workflow_id = f"wf-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        
        # 1. Check existing order status if order_id provided
        order_status = None
        if request.order_id:
            try:
                order_info = order_service.get_order_raw(request.order_id, customer_id=request.customer_id)
                order_status = order_info.status
            except Exception:
                order_status = None

        # 2. LLM Classification with retry & safe fallback
        classification = self.classify_complaint_with_fallback(request.complaint_text)

        # 3. Deterministic Priority Engine (App-side rule enforcement)
        calculated_priority = compute_deterministic_priority(
            category=classification.category.value,
            sentiment=classification.sentiment.value,
            urgency=classification.urgency.value,
            summary=request.complaint_text,
            order_status=order_status
        )

        # 4. Check Idempotency before ticket creation
        idempotency_key = compute_idempotency_key(
            customer_id=request.customer_id,
            order_id=request.order_id,
            category=classification.category.value,
            summary=classification.summary
        )

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticket_id FROM tickets WHERE idempotency_key = ?", (idempotency_key,))
        existing_row = cursor.fetchone()
        
        is_duplicate = False
        if existing_row:
            ticket_id = existing_row["ticket_id"]
            is_duplicate = True
            logger.info(f"Workflow {workflow_id} detected existing ticket {ticket_id} (Idempotent replay)")
        else:
            ticket = ticket_service.create_ticket(
                customer_id=request.customer_id,
                category=classification.category.value,
                priority=calculated_priority,
                summary=classification.summary,
                order_id=request.order_id,
                requires_human_approval=(calculated_priority == "High" or classification.needs_escalation)
            )
            ticket_id = ticket["ticket_id"]

        # 5. Simulate Notification Dispatch
        notification = self.simulate_notification(
            ticket_id=ticket_id,
            priority=calculated_priority,
            category=classification.category.value,
            customer_id=request.customer_id
        )

        # 6. Persist Workflow Run to SQLite & JSONL
        cursor.execute("""
            INSERT INTO workflow_runs (workflow_id, workflow_type, customer_id, order_id, input_text, classification, calculated_priority, ticket_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow_id,
            "complaint_escalation",
            request.customer_id,
            request.order_id,
            request.complaint_text,
            classification.model_dump_json(),
            calculated_priority,
            ticket_id,
            "completed",
            now
        ))
        conn.commit()
        conn.close()

        # Write to JSONL
        run_record = {
            "workflow_id": workflow_id,
            "customer_id": request.customer_id,
            "order_id": request.order_id,
            "classification": classification.model_dump(),
            "calculated_priority": calculated_priority,
            "ticket_id": ticket_id,
            "is_duplicate": is_duplicate,
            "status": "completed",
            "created_at": now
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(run_record) + "\n")
        except Exception as e:
            logger.error(f"Failed to append workflow run to {self.log_file}: {e}")

        return ComplaintWorkflowResponse(
            workflow_id=workflow_id,
            customer_id=request.customer_id,
            order_id=request.order_id,
            classification=classification,
            computed_priority=calculated_priority,
            ticket_id=ticket_id,
            is_duplicate=is_duplicate,
            status="completed",
            notification_simulated=notification
        )

complaint_workflow = ComplaintWorkflow()

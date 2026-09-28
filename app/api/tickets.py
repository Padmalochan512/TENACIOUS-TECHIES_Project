from fastapi import APIRouter, Depends, Query
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.services.ticket_service import ticket_service, compute_deterministic_priority
from app.services.auth import get_customer_id_from_header

router = APIRouter(prefix="/api/support", tags=["support"])

class CreateTicketRequest(BaseModel):
    category: str
    priority: Optional[str] = None
    summary: str
    order_id: Optional[str] = None
    requires_human_approval: Optional[bool] = False

@router.post("/tickets")
def create_ticket(
    req: CreateTicketRequest,
    customer_id: str = Depends(get_customer_id_from_header)
) -> Dict[str, Any]:
    priority = req.priority or compute_deterministic_priority(
        category=req.category,
        sentiment="neutral",
        urgency="medium",
        summary=req.summary
    )
    return ticket_service.create_ticket(
        customer_id=customer_id,
        category=req.category,
        priority=priority,
        summary=req.summary,
        order_id=req.order_id,
        requires_human_approval=bool(req.requires_human_approval)
    )

@router.get("/tickets")
def list_tickets(
    customer_id: Optional[str] = Query(None, description="Optional customer filter")
) -> List[Dict[str, Any]]:
    return ticket_service.get_tickets(customer_id=customer_id)

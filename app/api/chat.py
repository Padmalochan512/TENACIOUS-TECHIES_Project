from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.agent.schemas import ChatRequest, ChatResponse
from app.agent.orchestrator import agent_orchestrator
from app.services.auth import get_customer_id_from_header

router = APIRouter(prefix="/api/agent", tags=["agent"])

@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(
    req: ChatRequest,
    customer_id: str = Depends(get_customer_id_from_header)
):
    effective_customer_id = req.customer_id if req.customer_id else customer_id
    return agent_orchestrator.process_chat(
        message=req.message,
        customer_id=effective_customer_id,
        session_id=req.session_id
    )

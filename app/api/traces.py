from fastapi import APIRouter, HTTPException
from typing import Any, Dict
from app.observability.tracing import trace_manager

router = APIRouter(prefix="/api/traces", tags=["observability"])

@router.get("/{trace_id}")
def get_trace_details(trace_id: str) -> Dict[str, Any]:
    trace = trace_manager.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")
    return trace.model_dump()

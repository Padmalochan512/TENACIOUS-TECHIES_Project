from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Any, Dict, Optional
from app.services.order_service import order_service, OrderServiceException
from app.services.auth import get_customer_id_from_header

router = APIRouter(prefix="/api/orders", tags=["orders"])

@router.get("/{order_id}")
def get_order_details(
    order_id: str,
    customer_id: str = Depends(get_customer_id_from_header)
) -> Dict[str, Any]:
    try:
        return order_service.get_order_details(order_id=order_id, customer_id=customer_id)
    except OrderServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

@router.get("/{order_id}/status")
def get_order_status(
    order_id: str,
    customer_id: str = Depends(get_customer_id_from_header)
) -> Dict[str, Any]:
    try:
        return order_service.get_order_status(order_id=order_id, customer_id=customer_id)
    except OrderServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

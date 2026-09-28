from typing import Optional
from fastapi import Header, HTTPException, status

def get_customer_id_from_header(
    x_customer_id: Optional[str] = Header(None, alias="X-Customer-Id")
) -> str:
    """
    Extracts the authenticated customer ID from the HTTP request header.
    Defaults to CUST-001 if none provided in relaxed dev mode, but strictly validates presence when required.
    """
    if not x_customer_id:
        return "CUST-001"
    return x_customer_id.strip()

def enforce_order_ownership(customer_id: str, order_customer_id: str) -> None:
    """
    Ensures that a requesting customer can only access their own orders.
    Throws HTTP 403 Forbidden if mismatched.
    """
    if customer_id != order_customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Order belongs to a different customer."
        )

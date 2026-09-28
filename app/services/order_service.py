import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.logging import logger

ORDER_ID_REGEX = re.compile(r"^ORD-\d{4,}$")

class OrderItem(BaseModel):
    name: str
    quantity: int
    price: float

class Order(BaseModel):
    order_id: str
    customer_id: str
    status: str
    items: List[OrderItem]
    total_amount: float
    delivery_address: str
    created_at: str
    delivered_at: Optional[str] = None
    estimated_delivery: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None

class OrderServiceException(Exception):
    def __init__(self, message: str, error_code: str = "ORDER_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code

class OrderService:
    def __init__(self, json_path: Optional[Path] = None):
        self.json_path = json_path or settings.orders_json_path
        self._orders_cache: Dict[str, Order] = {}
        self.reload_orders()

    def reload_orders(self):
        if not self.json_path.exists():
            logger.warning(f"Orders file {self.json_path} does not exist.")
            self._orders_cache = {}
            return
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._orders_cache = {item["order_id"]: Order.model_validate(item) for item in data}
        except Exception as e:
            logger.error(f"Error loading orders from {self.json_path}: {e}")

    def validate_order_id(self, order_id: str) -> None:
        if not order_id or not ORDER_ID_REGEX.match(order_id.strip()):
            raise OrderServiceException(
                f"Invalid order ID format '{order_id}'. Expected format 'ORD-XXXX' (e.g. ORD-1001).",
                error_code="INVALID_ORDER_ID",
                status_code=400
            )

    def get_order_raw(self, order_id: str, customer_id: str) -> Order:
        # Check simulation flags
        if settings.simulate_timeout:
            time.sleep(0.5)
            raise OrderServiceException(
                "Order service connection timed out.",
                error_code="SERVICE_TIMEOUT",
                status_code=504
            )
        if settings.simulate_tool_failure:
            raise OrderServiceException(
                "Order service is currently unavailable. Please try again later.",
                error_code="SERVICE_UNAVAILABLE",
                status_code=503
            )

        self.validate_order_id(order_id)
        order = self._orders_cache.get(order_id)
        if not order:
            raise OrderServiceException(
                f"Order '{order_id}' was not found in our system.",
                error_code="ORDER_NOT_FOUND",
                status_code=404
            )

        if order.customer_id != customer_id:
            raise OrderServiceException(
                f"Unauthorized: You do not have permission to view order '{order_id}'.",
                error_code="UNAUTHORIZED_ACCESS",
                status_code=403
            )

        return order

    def get_order_status(self, order_id: str, customer_id: str) -> Dict[str, Any]:
        order = self.get_order_raw(order_id, customer_id)
        return {
            "order_id": order.order_id,
            "status": order.status,
            "estimated_delivery": order.estimated_delivery,
            "driver_name": order.driver_name,
            "notes": order.notes,
            "created_at": order.created_at
        }

    def get_order_details(self, order_id: str, customer_id: str) -> Dict[str, Any]:
        order = self.get_order_raw(order_id, customer_id)
        return order.model_dump()

order_service = OrderService()

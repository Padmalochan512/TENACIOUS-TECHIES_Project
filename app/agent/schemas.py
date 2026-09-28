from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ComplaintCategory(str, Enum):
    PAYMENT = "Payment"
    ORDER = "Order"
    DELIVERY = "Delivery"
    REFUND = "Refund"
    TECHNICAL = "Technical"
    OTHER = "Other"

class SentimentEnum(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    ANGRY = "angry"

class UrgencyEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ComplaintClassification(BaseModel):
    category: ComplaintCategory = ComplaintCategory.OTHER
    sentiment: SentimentEnum = SentimentEnum.NEUTRAL
    urgency: UrgencyEnum = UrgencyEnum.MEDIUM
    summary: str = Field(description="A concise 1-2 sentence summary of the customer's complaint.")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    needs_escalation: bool = Field(default=False)

# Tool Schemas for Validation
class GetOrderStatusArgs(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{4,}$", description="Unique order ID, formatted like ORD-1001")

class GetOrderDetailsArgs(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{4,}$", description="Unique order ID, formatted like ORD-1001")

class CreateSupportTicketArgs(BaseModel):
    order_id: Optional[str] = Field(default=None, description="Associated order ID if relevant")
    category: str = Field(default="Other", description="Ticket category (Payment, Order, Delivery, Refund, Technical, Other)")
    priority: str = Field(default="Medium", description="Initial priority level (Low, Medium, High)")
    summary: str = Field(description="Brief summary of the issue or complaint")

class SearchKnowledgeBaseArgs(BaseModel):
    query: str = Field(description="Customer question or keywords to search in restaurant policies and FAQs")

# API Schemas
class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    customer_id: Optional[str] = "CUST-001"
    message: str

class ToolCallRecord(BaseModel):
    tool_name: str
    args: Dict[str, Any]
    result: Dict[str, Any]
    error: Optional[str] = None

class SourceRecord(BaseModel):
    source_file: str
    section: str
    last_updated: Optional[str] = None
    score: Optional[float] = None

class ChatResponse(BaseModel):
    session_id: str
    customer_id: str
    reply: str
    sources: List[SourceRecord] = Field(default_factory=list)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    tool_data: Optional[Dict[str, Any]] = None
    trace_id: str

class ComplaintWorkflowRequest(BaseModel):
    customer_id: str = "CUST-001"
    order_id: Optional[str] = None
    complaint_text: str

class ComplaintWorkflowResponse(BaseModel):
    workflow_id: str
    customer_id: str
    order_id: Optional[str] = None
    classification: ComplaintClassification
    computed_priority: str
    ticket_id: str
    is_duplicate: bool
    status: str
    notification_simulated: Dict[str, Any]

import json
from typing import Any, Callable, Dict, List, Optional
from pydantic import ValidationError

from app.agent.schemas import (
    GetOrderStatusArgs,
    GetOrderDetailsArgs,
    CreateSupportTicketArgs,
    SearchKnowledgeBaseArgs
)
from app.services.order_service import order_service, OrderServiceException
from app.services.ticket_service import ticket_service, compute_deterministic_priority
from app.rag.retriever import kb_retriever
from app.observability.logging import logger

AVAILABLE_TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Fetch current status, delivery ETA, driver details, and tracking notes for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID formatted as ORD-XXXX (e.g. ORD-1001)"
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": "Fetch detailed line items, prices, delivery address, and timestamps for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID formatted as ORD-XXXX (e.g. ORD-1001)"
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": "Log a customer support ticket for complaints, issues, cancellations, refunds, or manual human review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Optional order ID related to the issue"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["Payment", "Order", "Delivery", "Refund", "Technical", "Other"],
                        "description": "Issue category"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High"],
                        "description": "Suggested priority level"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise summary of the issue"
                    }
                },
                "required": ["summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Query restaurant policies, refund rules, operating hours, delivery radius, allergens, and FAQs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or question regarding restaurant policy"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

class ToolExecutor:
    def __init__(self):
        pass

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        customer_id: str
    ) -> Dict[str, Any]:
        """
        Executes a validated tool with server-injected customer_id.
        Never allows LLM output to override customer isolation.
        """
        logger.info(f"Executing tool '{tool_name}' for customer '{customer_id}' with args: {arguments}")

        try:
            if tool_name == "get_order_status":
                parsed = GetOrderStatusArgs.model_validate(arguments)
                return order_service.get_order_status(parsed.order_id, customer_id=customer_id)

            elif tool_name == "get_order_details":
                parsed = GetOrderDetailsArgs.model_validate(arguments)
                return order_service.get_order_details(parsed.order_id, customer_id=customer_id)

            elif tool_name == "create_support_ticket":
                parsed = CreateSupportTicketArgs.model_validate(arguments)
                # Compute deterministic priority in application code
                calculated_priority = compute_deterministic_priority(
                    category=parsed.category,
                    sentiment="neutral",
                    urgency="high" if parsed.priority.lower() == "high" else "medium",
                    summary=parsed.summary
                )
                
                # Check if refund or cancellation requires human approval
                requires_human = parsed.category.lower() in ["refund", "cancellation", "payment"]
                
                ticket = ticket_service.create_ticket(
                    customer_id=customer_id,
                    order_id=parsed.order_id,
                    category=parsed.category,
                    priority=calculated_priority,
                    summary=parsed.summary,
                    requires_human_approval=requires_human
                )
                return ticket

            elif tool_name == "search_knowledge_base":
                parsed = SearchKnowledgeBaseArgs.model_validate(arguments)
                results = kb_retriever.search(parsed.query)
                return {
                    "query": parsed.query,
                    "results_count": len(results),
                    "results": results
                }

            else:
                return {
                    "error": f"Unknown tool name '{tool_name}'",
                    "error_code": "UNKNOWN_TOOL"
                }

        except ValidationError as ve:
            logger.warning(f"Tool argument validation failed for {tool_name}: {ve}")
            return {
                "error": f"Invalid arguments for {tool_name}: {ve.errors()[0].get('msg')}",
                "error_code": "INVALID_ARGUMENTS",
                "details": str(ve)
            }

        except OrderServiceException as ose:
            logger.warning(f"OrderServiceException in {tool_name}: {ose.message} ({ose.error_code})")
            return {
                "error": ose.message,
                "error_code": ose.error_code,
                "status_code": ose.status_code
            }

        except Exception as e:
            logger.error(f"Unexpected error executing {tool_name}: {e}", exc_info=True)
            return {
                "error": "The service is temporarily unavailable. Please try again shortly.",
                "error_code": "SERVICE_ERROR"
            }

tool_executor = ToolExecutor()

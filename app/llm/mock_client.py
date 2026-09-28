import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from app.llm.base import LLMClient, LLMResponse
from app.observability.logging import logger

T = TypeVar("T", bound=BaseModel)

class MockLLMClient(LLMClient):
    """
    Deterministic Mock LLM Client used for offline execution and automated test suites.
    Simulates intelligent tool call generation, reasoning over tool responses, and structured output.
    """
    def __init__(self, simulate_bad_json: bool = False):
        self.simulate_bad_json = simulate_bad_json
        self._bad_json_attempt_count = 0

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        last_message = messages[-1] if messages else {"role": "user", "content": ""}
        content = last_message.get("content", "")
        role = last_message.get("role", "user")

        # Case A: Handling the response after tool execution (role == 'tool' or previous messages contained tool outputs)
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        if tool_messages:
            last_tool_msg = tool_messages[-1]
            tool_name = last_tool_msg.get("name", "")
            tool_content = last_tool_msg.get("content", "")

            try:
                tool_data = json.loads(tool_content)
            except Exception:
                tool_data = {"raw": tool_content}

            # If tool returned an error
            if isinstance(tool_data, dict) and "error" in tool_data:
                err_code = tool_data.get("error_code")
                if err_code == "SERVICE_UNAVAILABLE" or err_code == "SERVICE_TIMEOUT":
                    return LLMResponse(
                        text="I apologize for the inconvenience, but our order service is temporarily unavailable at the moment. Please try again in a few minutes.",
                        finish_reason="stop"
                    )
                if err_code == "UNAUTHORIZED_ACCESS":
                    return LLMResponse(
                        text="I cannot access the details for this order because it belongs to a different customer account.",
                        finish_reason="stop"
                    )
                if err_code == "INVALID_ORDER_ID":
                    return LLMResponse(
                        text=f"The provided order ID is invalid. {tool_data.get('error')}",
                        finish_reason="stop"
                    )
                if err_code == "ORDER_NOT_FOUND":
                    return LLMResponse(
                        text=f"We could not find that order in our system. Would you like me to open a support ticket for you?",
                        finish_reason="stop"
                    )
                return LLMResponse(
                    text=f"We encountered an issue: {tool_data.get('error')}",
                    finish_reason="stop"
                )

            # Order Status Tool
            if tool_name == "get_order_status":
                order_id = tool_data.get("order_id", "your order")
                status = tool_data.get("status", "unknown")
                driver = tool_data.get("driver_name")
                est = tool_data.get("estimated_delivery")
                
                details_text = f"Order {order_id} is currently **{status}**."
                if driver:
                    details_text += f" Assigned driver: {driver}."
                if est:
                    details_text += f" Estimated delivery time: {est}."
                return LLMResponse(text=details_text, finish_reason="stop")

            # Order Details Tool
            if tool_name == "get_order_details":
                order_id = tool_data.get("order_id", "your order")
                status = tool_data.get("status", "unknown")
                total = tool_data.get("total_amount", 0.0)
                items = tool_data.get("items", [])
                items_str = ", ".join([f"{i.get('quantity')}x {i.get('name')}" for i in items])
                return LLMResponse(
                    text=f"Order {order_id} details: Status is **{status}**, Total: ${total:.2f}. Items: {items_str}.",
                    finish_reason="stop"
                )

            # Search Knowledge Base Tool
            if tool_name == "search_knowledge_base":
                results = tool_data.get("results", [])
                if not results:
                    return LLMResponse(
                        text="I don't have that information in my knowledge base. Would you like me to create a support ticket for our customer care team to assist you?",
                        finish_reason="stop"
                    )
                # Formulate answer citing sources
                top_chunk = results[0]
                source_file = top_chunk.get("source_file", "")
                section = top_chunk.get("section", "")
                content_snippet = top_chunk.get("content", "")

                # Specific answer for cancellation question
                if "cancellation" in source_file or "Cancellation" in section:
                    return LLMResponse(
                        text=(
                            f"According to our **{section}** ([{source_file}]):\n\n"
                            "Once the restaurant accepts your order (status is 'accepted', 'preparing', or 'out_for_delivery'), "
                            "orders cannot be cancelled through the self-service app because kitchen prep begins immediately. "
                            "If you have an emergency, please contact customer support for a human review."
                        ),
                        finish_reason="stop"
                    )
                
                return LLMResponse(
                    text=f"Based on our policy in **{section}** ({source_file}):\n{content_snippet[:300]}...",
                    finish_reason="stop"
                )

            # Create Support Ticket Tool
            if tool_name == "create_support_ticket":
                ticket_id = tool_data.get("ticket_id")
                priority = tool_data.get("priority")
                summary = tool_data.get("summary")
                return LLMResponse(
                    text=f"I have created a support ticket for you (Ticket ID: **{ticket_id}**, Priority: **{priority}**). Summary: '{summary}'. Our team will review it shortly.",
                    finish_reason="stop"
                )

        # Case B: Initial user prompt - Decide tool calling vs direct response
        user_text = content.lower() if isinstance(content, str) else ""

        # Check for order status inquiry
        order_match = re.search(r"ord-\d{4,}", user_text, re.IGNORECASE)
        if order_match and ("where" in user_text or "status" in user_text or "track" in user_text or "order" in user_text):
            found_order_id = order_match.group(0).upper()
            return LLMResponse(
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_order_status",
                        "arguments": json.dumps({"order_id": found_order_id})
                    }
                }],
                finish_reason="tool_calls"
            )

        # Check for order details inquiry
        if order_match and ("detail" in user_text or "items" in user_text or "receipt" in user_text):
            found_order_id = order_match.group(0).upper()
            return LLMResponse(
                tool_calls=[{
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "get_order_details",
                        "arguments": json.dumps({"order_id": found_order_id})
                    }
                }],
                finish_reason="tool_calls"
            )

        # Check for payment deducted / failure complaint
        if ("payment" in user_text and ("deducted" in user_text or "charged" in user_text)) or "failed" in user_text:
            order_id = order_match.group(0).upper() if order_match else None
            return LLMResponse(
                tool_calls=[{
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "create_support_ticket",
                        "arguments": json.dumps({
                            "order_id": order_id,
                            "category": "Payment",
                            "priority": "High",
                            "summary": content
                        })
                    }
                }],
                finish_reason="tool_calls"
            )

        # Check for general cancellation, delivery, or policy questions -> RAG search
        if any(keyword in user_text for keyword in ["cancel", "refund", "hour", "open", "allergen", "delivery fee", "radius", "policy", "late"]):
            return LLMResponse(
                tool_calls=[{
                    "id": "call_4",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "arguments": json.dumps({"query": content})
                    }
                }],
                finish_reason="tool_calls"
            )

        # Unrelated or unknown query
        if "quantum" in user_text or "alien" in user_text or "unknown topic" in user_text:
            return LLMResponse(
                tool_calls=[{
                    "id": "call_5",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "arguments": json.dumps({"query": content})
                    }
                }],
                finish_reason="tool_calls"
            )

        # Default conversational greeting
        return LLMResponse(
            text="Hello! Welcome to Restaurant Support. How can I help you with your orders or questions today?",
            finish_reason="stop"
        )

    def structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None
    ) -> T:
        prompt_lower = prompt.lower()
        
        # Test hook for bad JSON simulation
        if self.simulate_bad_json and self._bad_json_attempt_count == 0:
            self._bad_json_attempt_count += 1
            raise ValueError("Simulated malformed JSON response from LLM")

        # Classify complaint deterministically based on keywords
        category = "Other"
        sentiment = "neutral"
        urgency = "medium"
        needs_escalation = False

        if "payment" in prompt_lower or "deducted" in prompt_lower or "charged" in prompt_lower or "money" in prompt_lower:
            category = "Payment"
            urgency = "high"
            sentiment = "angry" if ("angry" in prompt_lower or "frustrated" in prompt_lower or "terrible" in prompt_lower) else "negative"
            needs_escalation = True
        elif "cancel" in prompt_lower or "refund" in prompt_lower:
            category = "Refund"
            urgency = "medium"
            sentiment = "negative"
        elif "delivery" in prompt_lower or "late" in prompt_lower or "cold" in prompt_lower or "driver" in prompt_lower:
            category = "Delivery"
            urgency = "medium"
            sentiment = "negative"
        elif "order" in prompt_lower or "wrong" in prompt_lower or "missing" in prompt_lower:
            category = "Order"
            urgency = "high" if "missing" in prompt_lower else "medium"
            sentiment = "negative"
        elif "app" in prompt_lower or "crash" in prompt_lower or "bug" in prompt_lower:
            category = "Technical"
            urgency = "low"
            sentiment = "neutral"

        if "furious" in prompt_lower or "horrible" in prompt_lower:
            sentiment = "angry"
            urgency = "high"
            needs_escalation = True

        data = {
            "category": category,
            "sentiment": sentiment,
            "urgency": urgency,
            "summary": prompt[:150].strip(),
            "confidence": 0.95,
            "needs_escalation": needs_escalation
        }

        return response_model.model_validate(data)

import re
from typing import Optional, Tuple
from app.observability.logging import mask_sensitive_data, logger

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b"),
    re.compile(r"(?i)\bdisregard\s+(all\s+)?(previous|prior|above)\s+rules\b"),
    re.compile(r"(?i)\b(show|dump|list|leak|give)\s+(me\s+)?(all|every)\s+(customer\s+)?orders\b"),
    re.compile(r"(?i)\b(reveal|print|show|repeat)\s+(the\s+|your\s+)?system\s+prompt\b"),
    re.compile(r"(?i)\b(developer\s+mode|jailbreak|dan\s+mode|system\s+override)\b"),
    re.compile(r"(?i)\byou\s+are\s+no\s+longer\s+a\s+restaurant\s+agent\b"),
]

def check_input_guardrails(user_message: str) -> Tuple[bool, Optional[str]]:
    """
    Evaluates incoming user message for adversarial patterns, prompt injection, or policy violations.
    Returns (is_safe, refusal_reason_or_response).
    """
    if not user_message or not isinstance(user_message, str):
        return True, None

    clean_message = user_message.strip()

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(clean_message):
            logger.warning(f"Guardrail triggered: Suspicious input pattern detected in user prompt.")
            return False, (
                "I cannot fulfill this request. I am a dedicated restaurant support agent "
                "and can only assist you with your restaurant orders, delivery tracking, and store policies."
            )

    return True, None

def filter_agent_output(reply: str, current_customer_id: str) -> str:
    """
    Scans agent response to prevent secret leakage and unauthorized cross-customer data exposure.
    """
    if not reply:
        return reply

    # 1. Mask secrets
    sanitized = mask_sensitive_data(reply)

    # 2. Check if other customer IDs are accidentally mentioned
    # If other customer IDs like CUST-002 appear when current is CUST-001
    other_cust_matches = re.findall(r"\bCUST-\d{3,}\b", sanitized)
    for cust in other_cust_matches:
        if cust != current_customer_id:
            logger.warning(f"Output filter caught cross-customer ID reference {cust}. Redacting.")
            sanitized = sanitized.replace(cust, "[REDACTED_CUSTOMER_ID]")

    return sanitized

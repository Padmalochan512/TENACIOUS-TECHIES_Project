import json
import logging
import re
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password|bearer\s+[a-zA-Z0-9_\-\.]+)', re.IGNORECASE),
    re.compile(r'AIzaSy[A-Za-z0-9_-]{33}'),  # Google API key pattern
]

def mask_sensitive_data(text: str) -> str:
    if not isinstance(text, str):
        return text
    masked = text
    for pattern in SENSITIVE_PATTERNS:
        masked = pattern.sub('[REDACTED_SECRET]', masked)
    return masked

def hash_customer_id(customer_id: Optional[str]) -> Optional[str]:
    if not customer_id:
        return None
    return hashlib.sha256(customer_id.encode('utf-8')).hexdigest()[:10]

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_sensitive_data(record.getMessage()),
        }
        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id
        if hasattr(record, "session_id"):
            log_obj["session_id"] = record.session_id
        if hasattr(record, "customer_id"):
            log_obj["customer_id_hashed"] = hash_customer_id(record.customer_id)
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            # Mask any strings in extra_data
            clean_extra = {}
            for k, v in record.extra_data.items():
                if isinstance(v, str):
                    clean_extra[k] = mask_sensitive_data(v)
                else:
                    clean_extra[k] = v
            log_obj["context"] = clean_extra
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

def get_logger(name: str = "restaurant_support") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = get_logger()

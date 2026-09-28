import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.logging import hash_customer_id, logger

class TraceEvent(BaseModel):
    name: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = Field(default_factory=dict)

class ExecutionTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: f"trc-{uuid.uuid4().hex[:12]}")
    session_id: Optional[str] = None
    customer_id_hashed: Optional[str] = None
    start_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    input_message: Optional[str] = None
    reply: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    events: List[TraceEvent] = Field(default_factory=list)
    token_estimate: int = 0
    success: bool = True
    error: Optional[str] = None

class TraceManager:
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or settings.trace_log_path
        self._memory_traces: Dict[str, ExecutionTrace] = {}
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def start_trace(self, session_id: Optional[str] = None, customer_id: Optional[str] = None, input_message: Optional[str] = None) -> ExecutionTrace:
        trace = ExecutionTrace(
            session_id=session_id,
            customer_id_hashed=hash_customer_id(customer_id),
            input_message=input_message
        )
        self._memory_traces[trace.trace_id] = trace
        return trace

    def record_event(self, trace_id: str, name: str, data: Dict[str, Any]):
        if trace_id in self._memory_traces:
            self._memory_traces[trace_id].events.append(TraceEvent(name=name, data=data))

    def finish_trace(self, trace_id: str, reply: Optional[str] = None, tool_calls: Optional[List[Dict[str, Any]]] = None,
                     sources: Optional[List[Dict[str, Any]]] = None, success: bool = True, error: Optional[str] = None,
                     token_estimate: int = 0) -> Optional[ExecutionTrace]:
        trace = self._memory_traces.get(trace_id)
        if not trace:
            return None
        
        trace.end_time = datetime.now(timezone.utc).isoformat()
        start_dt = datetime.fromisoformat(trace.start_time)
        end_dt = datetime.fromisoformat(trace.end_time)
        trace.duration_ms = round((end_dt - start_dt).total_seconds() * 1000, 2)
        trace.reply = reply
        if tool_calls is not None:
            trace.tool_calls = tool_calls
        if sources is not None:
            trace.sources = sources
        trace.success = success
        trace.error = error
        trace.token_estimate = token_estimate

        # Write to JSONL
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(trace.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to persist trace to file: {e}")

        return trace

    def get_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        if trace_id in self._memory_traces:
            return self._memory_traces[trace_id]
        
        # Look in file if not in memory
        if self.log_path and self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get("trace_id") == trace_id:
                                return ExecutionTrace.model_validate(data)
            except Exception as e:
                logger.error(f"Error reading trace log: {e}")
        return None

trace_manager = TraceManager()

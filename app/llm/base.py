from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMResponse(BaseModel):
    text: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = []
    finish_reason: str = "stop"
    token_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        """Execute a conversational completion with optional tool declarations."""
        pass

    @abstractmethod
    def structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None
    ) -> T:
        """Request structured JSON output validated against a Pydantic model."""
        pass

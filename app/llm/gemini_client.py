import json
import time
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from app.config import settings
from app.llm.base import LLMClient, LLMResponse
from app.observability.logging import logger

T = TypeVar("T", bound=BaseModel)

class GeminiClient(LLMClient):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model or settings.gemini_model
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize google-genai client: {e}")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> LLMResponse:
        if not self._client:
            raise RuntimeError("GeminiClient initialized without valid API key or client.")

        # Retry with exponential backoff (max 2 retries)
        last_exception = None
        for attempt in range(3):
            try:
                # Convert messages into contents
                contents = []
                for msg in messages:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": msg["content"]}]})

                config = {
                    "temperature": temperature,
                }
                if system_instruction:
                    config["system_instruction"] = system_instruction

                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )

                text = response.text if hasattr(response, "text") else str(response)
                return LLMResponse(
                    text=text,
                    finish_reason="stop",
                    token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                )
            except Exception as e:
                last_exception = e
                logger.warning(f"Gemini API call attempt {attempt+1} failed: {e}. Retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Gemini API failed after 3 attempts: {last_exception}")

    def structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None
    ) -> T:
        if not self._client:
            raise RuntimeError("GeminiClient initialized without valid API key.")

        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            f"You MUST respond ONLY with a valid JSON object strictly matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Do not include any conversational preamble or markdown code fence."
        )

        for attempt in range(2):
            try:
                response = self.chat(
                    messages=[{"role": "user", "content": full_prompt}],
                    system_instruction=system_instruction,
                    temperature=0.0
                )
                raw_text = (response.text or "").strip()
                # Remove code blocks if present
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()
                
                parsed_json = json.loads(raw_text)
                return response_model.model_validate(parsed_json)
            except Exception as e:
                logger.warning(f"Structured output attempt {attempt+1} failed: {e}")
                if attempt == 1:
                    raise e
        raise RuntimeError("Failed to generate structured output.")

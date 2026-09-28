from typing import Optional
from app.config import settings
from app.llm.base import LLMClient
from app.llm.mock_client import MockLLMClient
from app.llm.gemini_client import GeminiClient
from app.observability.logging import logger

_cached_client: Optional[LLMClient] = None

def get_llm_client(force_mock: bool = False) -> LLMClient:
    global _cached_client
    if force_mock:
        return MockLLMClient()
    
    if _cached_client is not None:
        return _cached_client

    if settings.gemini_api_key and settings.gemini_api_key.strip():
        try:
            logger.info(f"Initializing GeminiClient with model {settings.gemini_model}")
            _cached_client = GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
            return _cached_client
        except Exception as e:
            logger.warning(f"Failed to initialize GeminiClient ({e}), falling back to MockLLMClient")
            _cached_client = MockLLMClient()
            return _cached_client
    else:
        logger.info("No GEMINI_API_KEY detected. Using deterministic MockLLMClient.")
        _cached_client = MockLLMClient()
        return _cached_client

def set_llm_client(client: LLMClient):
    global _cached_client
    _cached_client = client

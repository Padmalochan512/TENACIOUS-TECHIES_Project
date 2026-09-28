from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "restaurant-support-agent"
    debug: bool = True
    port: int = 8000
    host: str = "0.0.0.0"

    # LLM Settings
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"

    # Agent Settings
    max_tool_calls: int = 4
    agent_timeout_seconds: float = 15.0
    session_memory_max_messages: int = 10

    # RAG Settings
    rag_similarity_threshold: float = 0.30
    rag_top_k: int = 3
    kb_dir: Path = BASE_DIR / "app" / "data" / "kb"

    # Persistence
    database_path: Path = BASE_DIR / "app" / "data" / "restaurant_support.db"
    orders_json_path: Path = BASE_DIR / "app" / "data" / "orders.json"
    trace_log_path: Path = BASE_DIR / "app" / "data" / "traces.jsonl"
    workflow_log_path: Path = BASE_DIR / "app" / "data" / "workflow_runs.jsonl"
    log_level: str = "INFO"

    # Simulation / Fault injection
    simulate_tool_failure: bool = False
    simulate_timeout: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.services.db import init_db
from app.rag.retriever import kb_retriever
from app.observability.logging import logger
from app.api.chat import router as chat_router
from app.api.orders import router as orders_router
from app.api.tickets import router as tickets_router
from app.api.workflows import router as workflows_router
from app.api.traces import router as traces_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up restaurant-support-agent...")
    init_db()
    kb_retriever.reload()
    logger.info("Database and RAG index initialized successfully.")
    yield
    # Shutdown actions
    logger.info("Shutting down restaurant-support-agent...")

app = FastAPI(
    title="Restaurant Support & Operations Agent",
    description="Production-minded AI Restaurant Support Agent built with Python, FastAPI, and Google Gemini SDK.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred.", "status_code": 500}
    )

# Register Routers
app.include_router(chat_router)
app.include_router(orders_router)
app.include_router(tickets_router)
app.include_router(workflows_router)
app.include_router(traces_router)

# Mount Static Files
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/health", tags=["system"])
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "env": settings.app_env,
        "gemini_model": settings.gemini_model,
        "mock_llm_active": settings.gemini_api_key is None or len(settings.gemini_api_key.strip()) == 0,
        "indexed_chunks": len(kb_retriever.chunks)
    }

# Minimal single-file HTML Chat UI served at GET /
HTML_FILE_PATH = Path(__file__).parent / "static" / "index.html"

@app.get("/", response_class=HTMLResponse, tags=["ui"])
def serve_chat_ui():
    if HTML_FILE_PATH.exists():
        return HTMLResponse(content=HTML_FILE_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Restaurant Support Agent API is running!</h1><p>Visit /docs for Swagger API documentation.</p>")

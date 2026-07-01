import logging

from fastapi import FastAPI

import app.models.manuscript
import app.models.user
from app.api.endpoints import router as api_router
from app.core.database import engine, Base
from app.core.error_handlers import register_exception_handlers
from app.pages.auth_pages import router as auth_pages_router
from app.pages.user_interface import router as pages_router

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RAG FastAPI Server",
    description="RAG 기능을 포함한 챗봇 서버",
    version="2.0.0",
)

register_exception_handlers(app)

# Register API routes
app.include_router(api_router)
app.include_router(pages_router)
app.include_router(auth_pages_router)

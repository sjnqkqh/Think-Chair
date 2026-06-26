from fastapi import FastAPI
from app.api.endpoints import router as api_router
from app.core.database import engine, Base
import app.models.history

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RAG FastAPI Server",
    description="RAG 기능을 포함한 챗봇 서버",
    version="2.0.0",
)

# Register API routes
app.include_router(api_router)

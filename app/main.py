from fastapi import FastAPI
from app.api.endpoints import router as api_router

app = FastAPI(
    title="RAG FastAPI Server",
    description="카카오테크 부트캠프 4기 규칙 RAG 서비스 API",
    version="2.0.0",
)

# Register API routes
app.include_router(api_router)

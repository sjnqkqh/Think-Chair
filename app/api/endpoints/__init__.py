from fastapi import APIRouter
from app.api.endpoints.query import router as query_router
from app.api.endpoints.document import router as document_router
from app.api.endpoints.evaluation import router as evaluation_router
from app.api.endpoints.history import router as history_router
from app.api.endpoints.auth import router as auth_router

router = APIRouter()

@router.get("/")
async def root():
    return {
        "service": "KTB4 Rules RAG Service API",
        "status": "online",
        "documentation": "/docs",
    }

router.include_router(query_router)
router.include_router(document_router)
router.include_router(evaluation_router)
router.include_router(history_router)
router.include_router(auth_router)

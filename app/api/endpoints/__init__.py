from fastapi import APIRouter
from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.manuscripts import router as manuscripts_router

router = APIRouter()

@router.get("/")
async def root():
    return {
        "service": "Think Chair API",
        "status": "online",
        "documentation": "/docs",
    }

router.include_router(auth_router)
router.include_router(manuscripts_router)

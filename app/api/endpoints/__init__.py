from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.manuscripts import router as manuscripts_router

router = APIRouter()

@router.get("/")
async def root(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse(url="/workspace")
    return RedirectResponse(url="/login")

router.include_router(auth_router)
router.include_router(manuscripts_router)

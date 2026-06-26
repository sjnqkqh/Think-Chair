from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
import os
from app.core.config import settings

router = APIRouter()


@router.get("/chat", response_class=HTMLResponse, summary="RAG 웹 채팅 화면")
async def chat_ui():
    template_path = os.path.join(settings.BASE_DIR, "app", "templates", "chat.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Chat HTML template not found")

    with open(template_path, "r", encoding="utf-8") as template_file:
        html_content = template_file.read()

    return HTMLResponse(content=html_content)

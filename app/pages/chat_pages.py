import uuid

from fastapi import APIRouter, Depends, Form, Request
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.database import get_database_session
from app.models.user import User
from app.services.chat_service import ChatService
from app.services.manuscript_service import get_manuscript
from app.templates.jinja import make_templates

router = APIRouter(prefix="/api/chat", tags=["chat"])

templates = make_templates()


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


@router.post("/{manuscript_id}/message")
async def send_message(
    request: Request,
    manuscript_id: uuid.UUID,
    content: str = Form(...),
    user: User = Depends(require_user),
    svc: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(db, user, manuscript_id)
    state = await svc.run(manuscript, user_message=content)
    pending_version = state.get("pending_version")
    ai_message = next(
        msg for msg in reversed(state["messages"]) if isinstance(msg, AIMessage)
    )
    return templates.TemplateResponse(
        request,
        "workspace/_chat_turn.html",
        {
            "human_message": HumanMessage(content=content),
            "ai_message": ai_message,
            "pending_version": pending_version,
            "manuscript_id": manuscript_id,
        },
    )

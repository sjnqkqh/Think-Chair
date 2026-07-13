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
    chat_service: ChatService = Depends(get_chat_service),
    database_session: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(database_session, user, manuscript_id)
    state = await chat_service.run(manuscript, user_message=content)
    new_paper = state.get("new_paper")
    client_message = state.get("client_message")
    if client_message is None:
        ai_message = next(
            message
            for message in reversed(state["messages"])
            if isinstance(message, AIMessage)
        )
    else:
        ai_message = AIMessage(content=client_message)
    return templates.TemplateResponse(
        request,
            "workspace/_chat_turn.html",
        {
            "human_message": HumanMessage(content=content),
            "ai_message": ai_message,
            "new_paper": new_paper,
            "manuscript_id": manuscript_id,
        },
    )

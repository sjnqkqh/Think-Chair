import json
import uuid

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.auth_deps import require_user
from app.core.database import get_database_session
from app.models.user import User
from app.services.manuscript_service import get_manuscript

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/{manuscript_id}/message")
async def send_message(
    request: Request,
    manuscript_id: uuid.UUID,
    content: str = Form(...),
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(database_session, user, manuscript_id)
    chat_service = request.app.state.chat_service
    action = await chat_service.begin_turn(database_session, manuscript, content)

    async def sse_events():
        try:
            async for event_name, payload in chat_service.stream_response(
                manuscript_id, action
            ):
                yield {
                    "event": event_name,
                    "data": json.dumps(payload, ensure_ascii=False),
                }
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(sse_events(), sep="\n")

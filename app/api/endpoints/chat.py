import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.auth_deps import require_user
from app.core.database import get_database_session
from app.logging import get_logger
from app.models.user import User
from app.services.manuscript_service import get_manuscript
from app.utils.sse import SseEvent

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(__name__)


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
    try:
        turn = await chat_service.begin_turn(
            database_session,
            manuscript,
            content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def sse_events():
        try:
            if turn.research_required:
                yield {
                    "event": SseEvent.RESEARCH_REQUIRED,
                    "data": json.dumps(
                        {
                            "manuscript_id": str(manuscript_id),
                            "message_id": str(turn.message_id),
                            "claim_or_query": turn.claim_or_query,
                        },
                        ensure_ascii=False,
                    ),
                }
            async for event_name, payload in chat_service.stream_response(
                manuscript_id,
                turn.action,
                research_required=turn.research_required,
            ):
                yield {
                    "event": event_name,
                    "data": json.dumps(payload, ensure_ascii=False),
                }
        except ValueError as exc:
            yield {
                "event": SseEvent.ERROR,
                "data": json.dumps({"message": str(exc)}, ensure_ascii=False),
            }
        except Exception:
            logger.exception("chat.stream_failed", manuscript_id=manuscript_id)
            yield {
                "event": SseEvent.ERROR,
                "data": json.dumps(
                    {
                        "message": (
                            "응답 처리 중 오류가 발생했습니다. "
                            "잠시 후 다시 시도해 주세요."
                        )
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(sse_events(), sep="\n")

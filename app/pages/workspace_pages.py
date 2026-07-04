import os
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.config import settings
from app.core.database import get_database_session
from app.models.manuscript import ConceptType
from app.models.user import User
from app.services.manuscript_service import get_manuscript, list_manuscripts

router = APIRouter()

templates = Jinja2Templates(directory=os.path.join(settings.BASE_DIR, "app", "templates"))


@router.get("/workspace", response_class=HTMLResponse)
async def workspace_root(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    return templates.TemplateResponse(
        request,
        "workspace/index.html",
        {
            "manuscripts": manuscripts,
            "concepts": list(ConceptType),
            "active_manuscript": None,
            "messages": [],
        },
    )


@router.get("/workspace/{manuscript_id}", response_class=HTMLResponse)
async def workspace_detail(
    request: Request,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    active = get_manuscript(db, user, manuscript_id)
    return templates.TemplateResponse(
        request,
        "workspace/index.html",
        {
            "manuscripts": manuscripts,
            "concepts": list(ConceptType),
            "active_manuscript": active,
            "messages": await _load_messages(request, active),
        },
    )


async def _load_messages(request: Request, manuscript) -> list:
    # ChatMessage 테이블이 없으므로 그래프 체크포인터가 대화 이력의 유일한 출처다.
    svc = request.app.state.chat_service
    config = {"configurable": {"thread_id": str(manuscript.id)}}
    snapshot = await svc.graph.aget_state(config)
    return snapshot.values.get("messages", []) if snapshot and snapshot.values else []

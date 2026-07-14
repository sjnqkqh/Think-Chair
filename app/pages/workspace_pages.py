import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.database import get_database_session
from app.models.manuscript import ConceptType
from app.models.user import User
from app.services.manuscript_service import (
    get_manuscript,
    group_manuscripts_by_date,
    list_manuscript_versions,
    list_manuscripts,
)
from app.templates.jinja import make_templates

router = APIRouter()

templates = make_templates()


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
            "manuscript_groups": group_manuscripts_by_date(manuscripts),
            "user": user,
            "concepts": list(ConceptType),
            "active_manuscript": None,
            "messages": [],
            "versions": [],
        },
    )


@router.get("/workspace/sidebar", response_class=HTMLResponse)
async def workspace_sidebar(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    return templates.TemplateResponse(
        request,
        "workspace/_sidebar_left.html",
        {
            "manuscript_groups": group_manuscripts_by_date(manuscripts),
            "active_manuscript": None,
        },
    )


@router.get("/workspace/sidebar/{manuscript_id}", response_class=HTMLResponse)
async def workspace_sidebar_active(
    request: Request,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    active = get_manuscript(db, user, manuscript_id)
    return templates.TemplateResponse(
        request,
        "workspace/_sidebar_left.html",
        {
            "manuscript_groups": group_manuscripts_by_date(manuscripts),
            "active_manuscript": active,
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
    messages = await request.app.state.conversation_state.load_messages(active.id)
    return templates.TemplateResponse(
        request,
        "workspace/index.html",
        {
            "manuscript_groups": group_manuscripts_by_date(manuscripts),
            "user": user,
            "concepts": list(ConceptType),
            "active_manuscript": active,
            "messages": messages,
            "versions": list_manuscript_versions(db, user, manuscript_id),
        },
    )

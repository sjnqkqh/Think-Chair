import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.core.auth_deps import require_user
from app.models.user import User
from app.schemas.manuscript import ManuscriptCreateRequest, ManuscriptResponse
from app.services.manuscript_service import (
    create_manuscript,
    get_manuscript,
    list_manuscripts,
)

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.post("", response_model=ManuscriptResponse, status_code=201)
def create(
    payload: ManuscriptCreateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscript = create_manuscript(db, user, payload)
    return ManuscriptResponse(
        id=str(manuscript.id),
        topic=manuscript.topic,
        concept=manuscript.concept,
        status=manuscript.status,
        audience_level=manuscript.audience_level,
    )


@router.get("", response_model=list[ManuscriptResponse])
def list_all(
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    return [
        ManuscriptResponse(
            id=str(m.id),
            topic=m.topic,
            concept=m.concept,
            status=m.status,
            audience_level=m.audience_level,
        )
        for m in manuscripts
    ]


@router.get("/{manuscript_id}", response_model=ManuscriptResponse)
def get(
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(db, user, manuscript_id)
    return ManuscriptResponse(
        id=str(manuscript.id),
        topic=manuscript.topic,
        concept=manuscript.concept,
        status=manuscript.status,
        audience_level=manuscript.audience_level,
    )

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.core.auth_deps import require_user
from app.models.user import User
from app.schemas.manuscript import ManuscriptCreateRequest, ManuscriptResponse
from app.services.manuscript_service import (
    create_manuscript,
    finalize_manuscript,
    get_manuscript,
    get_version_file,
    list_manuscripts,
)

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.post("", response_model=ManuscriptResponse, status_code=201)
def create(
    payload: ManuscriptCreateRequest,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscript = create_manuscript(db, user, payload)
    response.headers["HX-Redirect"] = f"/workspace/{manuscript.id}"
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


@router.get("/{manuscript_id}/versions/{version_id}/download")
def download_version(
    manuscript_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    storage = request.app.state.chat_service.storage
    filename, content = get_version_file(db, user, manuscript_id, version_id, storage)
    encoded_filename = quote(filename)
    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{encoded_filename}\"; "
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.post("/{manuscript_id}/finalize", response_model=ManuscriptResponse)
def finalize(
    manuscript_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscript = finalize_manuscript(db, user, manuscript_id, version_id)
    return ManuscriptResponse(
        id=str(manuscript.id),
        topic=manuscript.topic,
        concept=manuscript.concept,
        status=manuscript.status,
        audience_level=manuscript.audience_level,
    )

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.database import get_database_session
from app.models.user import User
from app.services.manuscript_service import get_manuscript
from app.services.research_job_service import (
    create_or_get_research_job,
    get_owned_research_job,
    mark_job_cancelled,
    research_job_status_payload,
)

router = APIRouter(prefix="/api/research", tags=["research"])


class CreateResearchJobBody(BaseModel):
    manuscript_id: uuid.UUID
    message_id: uuid.UUID
    claim_or_query: str = Field(min_length=1)


@router.post("/jobs", status_code=202)
async def create_research_job(
    request: Request,
    body: CreateResearchJobBody,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(database_session, user, body.manuscript_id)
    chat_service = request.app.state.chat_service
    job, created = create_or_get_research_job(
        database_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=body.message_id,
        claim_or_query=body.claim_or_query,
        background_tasks=chat_service.background_tasks,
        db_factory=chat_service.db_factory,
        concept=manuscript.concept,
    )
    return {
        "id": str(job.id),
        "status": job.status.value,
        "created": created,
        "status_url": f"/api/research/jobs/{job.id}",
    }


@router.get("/jobs/{job_id}")
async def get_research_job(
    job_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    get_manuscript(database_session, user, manuscript_id)
    job = get_owned_research_job(
        database_session,
        job_id=job_id,
        user_id=user.id,
        manuscript_id=manuscript_id,
    )
    if job is None:
        return {"error": "not_found"}
    return research_job_status_payload(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_research_job(
    job_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    database_session: Session = Depends(get_database_session),
):
    get_manuscript(database_session, user, manuscript_id)
    job = get_owned_research_job(
        database_session,
        job_id=job_id,
        user_id=user.id,
        manuscript_id=manuscript_id,
    )
    if job is None:
        return {"error": "not_found"}
    job = mark_job_cancelled(database_session, job)
    return {"id": str(job.id), "status": job.status.value}

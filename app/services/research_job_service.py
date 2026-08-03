"""조사 job 생성·조회. 엔드포인트는 이 서비스만 호출한다."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.research import ResearchJob, ResearchJobStatus
from app.repositories import research_repo
from app.services.background_tasks import BackgroundTaskRegistry


def create_or_get_research_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID,
    claim_or_query: str,
    background_tasks: BackgroundTaskRegistry,
    run_job,
) -> tuple[ResearchJob, bool]:
    """message당 job 1개. 새로 만들면 백그라운드 실행을 예약한다."""
    existing = research_repo.find_research_job_by_message(
        db,
        user_id=user_id,
        manuscript_id=manuscript_id,
        message_id=message_id,
    )
    if existing is not None:
        return existing, False

    try:
        job = research_repo.create_research_job(
            db,
            user_id=user_id,
            manuscript_id=manuscript_id,
            message_id=message_id,
            claim_or_query=claim_or_query,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = research_repo.find_research_job_by_message(
            db,
            user_id=user_id,
            manuscript_id=manuscript_id,
            message_id=message_id,
        )
        if existing is None:
            raise
        return existing, False

    background_tasks.start(run_job(job.id))
    return job, True


def get_owned_research_job(
    db: Session,
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchJob | None:
    return research_repo.find_owned_research_job(
        db, job_id, user_id, manuscript_id
    )


def mark_job_cancelled(
    db: Session,
    job: ResearchJob,
) -> ResearchJob:
    if job.status in {
        ResearchJobStatus.COMPLETED,
        ResearchJobStatus.PARTIAL,
        ResearchJobStatus.FAILED,
        ResearchJobStatus.CANCELLED,
    }:
        return job
    job.status = ResearchJobStatus.CANCELLED
    db.commit()
    return job

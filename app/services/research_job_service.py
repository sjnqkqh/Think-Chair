"""조사 job 생성·조회. 엔드포인트는 이 서비스만 호출한다."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.manuscript import ConceptType
from app.models.research import ResearchJob, ResearchJobStatus
from app.repositories import research_repo
from app.research.research_eligibility import concept_allows_web_research
from app.services.background_tasks import BackgroundTaskRegistry

MAX_RESEARCH_JOBS_PER_MANUSCRIPT = 5


def create_or_get_research_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID,
    claim_or_query: str,
    background_tasks: BackgroundTaskRegistry,
    run_job,
    concept: ConceptType,
) -> tuple[ResearchJob, bool]:
    """message당 job 1개. 새로 만들면 백그라운드 실행을 예약한다.

    원고당 신규 job은 최대 MAX_RESEARCH_JOBS_PER_MANUSCRIPT개까지 허용한다.
    딥다이브·수업 자료 외 컨셉에서는 생성하지 않는다.
    """
    if not concept_allows_web_research(concept):
        raise ConflictError(
            "웹 조사는 딥다이브·수업 자료 원고에서만 사용할 수 있습니다."
        )

    existing = research_repo.find_research_job_by_message(
        db,
        user_id=user_id,
        manuscript_id=manuscript_id,
        message_id=message_id,
    )
    if existing is not None:
        return existing, False

    usage = research_repo.get_or_create_research_usage(
        db, user_id=user_id, manuscript_id=manuscript_id
    )
    if usage.job_count >= MAX_RESEARCH_JOBS_PER_MANUSCRIPT:
        raise ConflictError(
            f"원고당 조사 job은 최대 {MAX_RESEARCH_JOBS_PER_MANUSCRIPT}개까지 "
            "만들 수 있습니다."
        )

    try:
        job = research_repo.create_research_job(
            db,
            user_id=user_id,
            manuscript_id=manuscript_id,
            message_id=message_id,
            claim_or_query=claim_or_query,
        )
        research_repo.increment_research_job_count(
            db, user_id=user_id, manuscript_id=manuscript_id
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

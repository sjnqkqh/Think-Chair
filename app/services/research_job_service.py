"""조사 job 생성·조회·실행 배선. 엔드포인트는 이 서비스만 호출한다."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.storage import get_file_storage
from app.models.manuscript import ConceptType
from app.models.research import ResearchJob, ResearchJobStatus, ResearchSource
from app.repositories import research_repo
from app.research.indexing import (
    create_research_embeddings,
    create_research_evidence_index,
    index_research_sources,
)
from app.research.page_fetcher import fetch_page
from app.research.research_eligibility import concept_allows_web_research
from app.research.research_job_runner import run_research_job
from app.research.web_research import expand_evidence_via_web_search
from app.research.web_search import search_web
from app.services.background_tasks import BackgroundTaskRegistry

MAX_RESEARCH_JOBS_PER_MANUSCRIPT = 5

_EVIDENCE_READY_STATUSES = frozenset(
    {
        ResearchJobStatus.COMPLETED,
        ResearchJobStatus.PARTIAL,
    }
)


def create_or_get_research_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID,
    claim_or_query: str,
    background_tasks: BackgroundTaskRegistry,
    db_factory,
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

    background_tasks.start(execute_research_job(job.id, db_factory=db_factory))
    return job, True


async def execute_research_job(job_id: uuid.UUID, *, db_factory) -> None:
    """조사 job 실행에 필요한 의존성을 조립하고 runner를 호출한다."""
    embeddings = create_research_embeddings()
    evidence_index = create_research_evidence_index()
    storage = get_file_storage()

    async def web_research(*, db, job, query, evidence_index):
        return await expand_evidence_via_web_search(
            db=db,
            job=job,
            query=query,
            evidence_index=evidence_index,
            storage=storage,
            embeddings=embeddings,
            search_web=search_web,
            fetch_page=fetch_page,
            index_research_sources=index_research_sources,
            admit_source=lambda _source: "public",
        )

    await run_research_job(
        job_id=job_id,
        db_factory=db_factory,
        evidence_index=evidence_index,
        embed_query=embeddings.embed_query,
        generate_invoke=_make_deepseek_invoker(),
        judge_invoke=_make_deepseek_invoker(),
        generation_model=settings.DEEPSEEK_MODEL,
        judge_model=settings.DEEPSEEK_MODEL,
        web_research=web_research,
    )


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


def list_sources_for_job(db: Session, job: ResearchJob) -> list[dict]:
    sources = research_repo.list_sources_for_research_job(
        db, research_job_id=job.id
    )
    return [_research_source_payload(source) for source in sources]


def _research_source_payload(source: ResearchSource) -> dict:
    return {
        "id": str(source.id),
        "title": source.title,
        "canonical_url": source.canonical_url,
        "status": source.status.value,
        "scope": source.scope.value,
        "publisher": source.publisher,
        "fetched_at": source.fetched_at.isoformat(),
    }


def research_job_status_payload(db: Session, job: ResearchJob) -> dict:
    return {
        "id": str(job.id),
        "status": job.status.value,
        "terminal_error": job.terminal_error,
        "evidence_ready": job.status in _EVIDENCE_READY_STATUSES,
        "sources": list_sources_for_job(db, job),
    }


def job_ready_for_grounded_reply(job: ResearchJob) -> bool:
    """조사 완료(근거 있음)로 같은 턴 답변을 이어갈 수 있는 상태인지."""
    return job.status in _EVIDENCE_READY_STATUSES


def mark_job_cancelled(
    db: Session,
    job: ResearchJob,
) -> ResearchJob:
    if not job.mark_cancelled():
        return job
    db.commit()
    return job


def _make_deepseek_invoker(model_name: str | None = None):
    """조사 job의 baseline/grounded·비교 판정은 채팅과 같이 DeepSeek를 쓴다."""
    from langchain_openai import ChatOpenAI

    language_model = ChatOpenAI(
        openai_api_key=settings.DEEPSEEK_API_KEY,
        openai_api_base=settings.DEEPSEEK_API_BASE,
        model_name=model_name or settings.DEEPSEEK_MODEL,
        temperature=0,
    )

    def invoke(prompt: str) -> str:
        message = language_model.invoke(prompt)
        content = message.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    return invoke

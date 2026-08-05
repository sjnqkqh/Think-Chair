import datetime
import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript
from app.models.research import (
    ResearchJob,
    ResearchJobSource,
    ResearchJobStatus,
    ResearchSource,
    ResearchSourceScope,
    ResearchSourceUrl,
    ResearchUsage,
    ResearchWebSearch,
    ResponseComparisonRecord,
)

_SOURCE_NAMESPACE = uuid.UUID("e9a6eb1a-54d1-49bd-8bca-2a17d0394630")


def source_identity_key(
    scope: ResearchSourceScope,
    value: str,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> str:
    owner = "" if scope == ResearchSourceScope.PUBLIC else f"{user_id}:{manuscript_id}:"
    return hashlib.sha256(f"{scope.value}:{owner}{value}".encode("utf-8")).hexdigest()


def source_id_from_identity(identity_key: str) -> uuid.UUID:
    return uuid.uuid5(_SOURCE_NAMESPACE, identity_key)


def find_owned_research_job(
    db: Session,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchJob | None:
    return (
        db.query(ResearchJob)
        .join(Manuscript, Manuscript.id == ResearchJob.manuscript_id)
        .filter(
            ResearchJob.id == job_id,
            ResearchJob.user_id == user_id,
            ResearchJob.manuscript_id == manuscript_id,
            Manuscript.user_id == user_id,
            Manuscript.is_deleted.is_(False),
        )
        .first()
    )


def find_source_by_url(
    db: Session,
    scope: ResearchSourceScope,
    url: str,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchSource | None:
    identity_key = source_identity_key(scope, url, user_id, manuscript_id)
    return (
        db.query(ResearchSource)
        .join(ResearchSourceUrl, ResearchSourceUrl.source_id == ResearchSource.id)
        .filter(ResearchSourceUrl.identity_key == identity_key)
        .first()
    )


def add_source_url_alias(
    db: Session,
    source: ResearchSource,
    url: str,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    *,
    is_canonical: bool,
) -> None:
    identity_key = source_identity_key(
        source.scope, url, user_id, manuscript_id
    )
    alias = (
        db.query(ResearchSourceUrl)
        .filter(ResearchSourceUrl.identity_key == identity_key)
        .first()
    )
    if alias is None:
        for pending in db.new:
            if (
                isinstance(pending, ResearchSourceUrl)
                and pending.identity_key == identity_key
            ):
                alias = pending
                break
    if alias is not None:
        alias.is_canonical = alias.is_canonical or is_canonical
        return
    db.add(
        ResearchSourceUrl(
            identity_key=identity_key,
            source_id=source.id,
            url=url,
            scope=source.scope,
            owner_user_id=source.owner_user_id,
            owner_manuscript_id=source.owner_manuscript_id,
            is_canonical=is_canonical,
        )
    )


def list_sources_for_research_job(
    db: Session,
    *,
    research_job_id: uuid.UUID,
) -> list[ResearchSource]:
    return (
        db.query(ResearchSource)
        .join(
            ResearchJobSource,
            ResearchJobSource.source_id == ResearchSource.id,
        )
        .filter(ResearchJobSource.research_job_id == research_job_id)
        .all()
    )


def link_source_to_research_job(
    db: Session,
    job: ResearchJob,
    source: ResearchSource,
) -> None:
    exists = (
        db.query(ResearchJobSource)
        .filter(
            ResearchJobSource.research_job_id == job.id,
            ResearchJobSource.source_id == source.id,
        )
        .first()
    )
    if exists is None:
        db.add(
            ResearchJobSource(
                research_job_id=job.id,
                source_id=source.id,
                user_id=job.user_id,
                manuscript_id=job.manuscript_id,
            )
        )


def record_research_web_search(
    db: Session,
    job: ResearchJob,
    *,
    query: str,
    max_results: int,
    hit_results: list[dict],
    error_code: str | None = None,
    provider: str = "brave",
) -> ResearchWebSearch:
    """Brave 등에 보낸 검색어와 반환 hit 요약을 job에 연결해 저장한다."""
    record = ResearchWebSearch(
        research_job_id=job.id,
        user_id=job.user_id,
        manuscript_id=job.manuscript_id,
        query=query,
        provider=provider,
        max_results=max_results,
        hit_results_json=json.dumps(hit_results, ensure_ascii=False),
        error_code=error_code,
    )
    db.add(record)
    return record


def list_web_searches_for_research_job(
    db: Session, job: ResearchJob
) -> list[ResearchWebSearch]:
    return (
        db.query(ResearchWebSearch)
        .filter(ResearchWebSearch.research_job_id == job.id)
        .order_by(ResearchWebSearch.created_at.asc())
        .all()
    )


def find_research_job_by_message(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID,
) -> ResearchJob | None:
    return (
        db.query(ResearchJob)
        .filter(
            ResearchJob.user_id == user_id,
            ResearchJob.manuscript_id == manuscript_id,
            ResearchJob.message_id == message_id,
        )
        .first()
    )


def create_research_job(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID | None,
    claim_or_query: str | None,
) -> ResearchJob:
    job = ResearchJob(
        user_id=user_id,
        manuscript_id=manuscript_id,
        message_id=message_id,
        claim_or_query=claim_or_query,
        status=ResearchJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    return job


def get_or_create_research_usage(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchUsage:
    usage = (
        db.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript_id)
        .first()
    )
    if usage is not None:
        return usage
    existing_jobs = (
        db.query(ResearchJob)
        .filter(ResearchJob.manuscript_id == manuscript_id)
        .count()
    )
    usage = ResearchUsage(
        user_id=user_id,
        manuscript_id=manuscript_id,
        job_count=existing_jobs,
        search_count=0,
    )
    db.add(usage)
    db.flush()
    return usage


def increment_research_job_count(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchUsage:
    usage = get_or_create_research_usage(
        db, user_id=user_id, manuscript_id=manuscript_id
    )
    usage.job_count += 1
    usage.updated_at = datetime.datetime.utcnow()
    db.flush()
    return usage


def increment_research_search_count(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResearchUsage:
    usage = get_or_create_research_usage(
        db, user_id=user_id, manuscript_id=manuscript_id
    )
    usage.search_count += 1
    usage.updated_at = datetime.datetime.utcnow()
    db.flush()
    return usage


def save_response_comparison_record(
    db: Session,
    record: ResponseComparisonRecord,
) -> ResponseComparisonRecord:
    existing = (
        db.query(ResponseComparisonRecord)
        .filter(
            ResponseComparisonRecord.research_job_id == record.research_job_id
        )
        .first()
    )
    if existing is not None:
        return existing
    db.add(record)
    db.flush()
    return record


def find_comparison_record_for_job(
    db: Session,
    *,
    research_job_id: uuid.UUID,
) -> ResponseComparisonRecord | None:
    return (
        db.query(ResponseComparisonRecord)
        .filter(ResponseComparisonRecord.research_job_id == research_job_id)
        .first()
    )

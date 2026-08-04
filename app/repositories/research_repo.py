import datetime
import hashlib
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
    *,
    research_job_id: uuid.UUID,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    message_id: uuid.UUID | None,
    baseline_body: str,
    grounded_body: str,
    baseline_cited_urls: str = "[]",
    grounded_cited_urls: str = "[]",
    baseline_citation_passed: bool = True,
    grounded_citation_passed: bool = True,
    citation_failure_reasons: str | None = None,
    specificity_winner: str | None = None,
    naturalness_winner: str | None = None,
    accuracy_winner: str | None = None,
    overall_winner: str | None = None,
    judgment_reason: str | None = None,
    order_flipped: bool | None = None,
    generation_model: str | None = None,
    judge_model: str | None = None,
    comparison_error: str | None = None,
    prepared_evidence_json: str | None = None,
) -> ResponseComparisonRecord:
    existing = (
        db.query(ResponseComparisonRecord)
        .filter(ResponseComparisonRecord.research_job_id == research_job_id)
        .first()
    )
    if existing is not None:
        return existing
    record = ResponseComparisonRecord(
        research_job_id=research_job_id,
        user_id=user_id,
        manuscript_id=manuscript_id,
        message_id=message_id,
        baseline_body=baseline_body,
        grounded_body=grounded_body,
        baseline_cited_urls=baseline_cited_urls,
        grounded_cited_urls=grounded_cited_urls,
        baseline_citation_passed=baseline_citation_passed,
        grounded_citation_passed=grounded_citation_passed,
        citation_failure_reasons=citation_failure_reasons,
        specificity_winner=specificity_winner,
        naturalness_winner=naturalness_winner,
        accuracy_winner=accuracy_winner,
        overall_winner=overall_winner,
        judgment_reason=judgment_reason,
        order_flipped=order_flipped,
        generation_model=generation_model,
        judge_model=judge_model,
        comparison_error=comparison_error,
        prepared_evidence_json=prepared_evidence_json,
    )
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


def find_ready_prepared_evidence(
    db: Session,
    *,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> ResponseComparisonRecord | None:
    return (
        db.query(ResponseComparisonRecord)
        .filter(
            ResponseComparisonRecord.user_id == user_id,
            ResponseComparisonRecord.manuscript_id == manuscript_id,
            ResponseComparisonRecord.prepared_evidence_json.isnot(None),
            ResponseComparisonRecord.consumed_at.is_(None),
        )
        .order_by(ResponseComparisonRecord.created_at.desc())
        .first()
    )


def mark_prepared_evidence_consumed(
    db: Session,
    record: ResponseComparisonRecord,
) -> None:
    record.consumed_at = datetime.datetime.utcnow()
    db.flush()

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript
from app.models.research import (
    ResearchJob,
    ResearchJobSource,
    ResearchSource,
    ResearchSourceScope,
    ResearchSourceUrl,
)

_SOURCE_NAMESPACE = uuid.UUID("e9a6eb1a-54d1-49bd-8bca-2a17d0394630")


def scoped_identity(
    scope: ResearchSourceScope,
    value: str,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
) -> str:
    owner = "" if scope == ResearchSourceScope.PUBLIC else f"{user_id}:{manuscript_id}:"
    return hashlib.sha256(f"{scope.value}:{owner}{value}".encode("utf-8")).hexdigest()


def deterministic_source_id(identity_key: str) -> uuid.UUID:
    return uuid.uuid5(_SOURCE_NAMESPACE, identity_key)


def get_owned_job(
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
    identity_key = scoped_identity(scope, url, user_id, manuscript_id)
    return (
        db.query(ResearchSource)
        .join(ResearchSourceUrl, ResearchSourceUrl.source_id == ResearchSource.id)
        .filter(ResearchSourceUrl.identity_key == identity_key)
        .first()
    )


def add_url_alias(
    db: Session,
    source: ResearchSource,
    url: str,
    user_id: uuid.UUID,
    manuscript_id: uuid.UUID,
    *,
    is_canonical: bool,
) -> None:
    identity_key = scoped_identity(source.scope, url, user_id, manuscript_id)
    alias = (
        db.query(ResearchSourceUrl)
        .filter(ResearchSourceUrl.identity_key == identity_key)
        .first()
    )
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


def attach_source_to_job(
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

import uuid

from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript, ManuscriptStatus, ManuscriptVersion
from app.models.user import User


def create(db: Session, user: User, topic: str, concept, audience_level: str | None) -> Manuscript:
    manuscript = Manuscript(
        user_id=user.id,
        topic=topic,
        concept=concept,
        audience_level=audience_level,
    )
    db.add(manuscript)
    db.commit()
    db.refresh(manuscript)
    return manuscript


def list_by_user(db: Session, user: User) -> list[Manuscript]:
    return (
        db.query(Manuscript)
        .filter(Manuscript.user_id == user.id)
        .order_by(Manuscript.last_active_at.desc())
        .all()
    )


def get_owned(db: Session, user: User, manuscript_id: uuid.UUID) -> Manuscript | None:
    return (
        db.query(Manuscript)
        .filter(Manuscript.id == manuscript_id, Manuscript.user_id == user.id)
        .first()
    )


def list_versions_by_manuscript(
    db: Session, user: User, manuscript_id: uuid.UUID
) -> list[ManuscriptVersion]:
    return (
        db.query(ManuscriptVersion)
        .join(Manuscript, Manuscript.id == ManuscriptVersion.manuscript_id)
        .filter(
            ManuscriptVersion.manuscript_id == manuscript_id,
            Manuscript.user_id == user.id,
        )
        .order_by(ManuscriptVersion.created_at.asc())
        .all()
    )


def get_version_owned(
    db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID
) -> ManuscriptVersion | None:
    return (
        db.query(ManuscriptVersion)
        .join(Manuscript, Manuscript.id == ManuscriptVersion.manuscript_id)
        .filter(
            ManuscriptVersion.id == version_id,
            ManuscriptVersion.manuscript_id == manuscript_id,
            Manuscript.user_id == user.id,
        )
        .first()
    )


def finalize(db: Session, manuscript: Manuscript, version: ManuscriptVersion) -> None:
    version.is_finalized = True
    manuscript.status = ManuscriptStatus.FINALIZED
    db.add(version)
    db.add(manuscript)
    db.commit()

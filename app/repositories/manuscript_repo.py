import uuid

from sqlalchemy.orm import Session

from app.models.manuscript import Manuscript
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

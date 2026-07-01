import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories import manuscript_repo
from app.schemas.manuscript import ManuscriptCreateRequest


def create_manuscript(db: Session, user: User, payload: ManuscriptCreateRequest):
    return manuscript_repo.create(
        db, user, payload.topic, payload.concept, payload.audience_level
    )


def list_manuscripts(db: Session, user: User):
    return manuscript_repo.list_by_user(db, user)


def get_manuscript(db: Session, user: User, manuscript_id: uuid.UUID):
    manuscript = manuscript_repo.get_owned(db, user, manuscript_id)
    if not manuscript:
        raise NotFoundError("원고를 찾을 수 없습니다.")
    return manuscript

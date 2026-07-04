import logging
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories import manuscript_repo
from app.schemas.manuscript import ManuscriptCreateRequest

logger = logging.getLogger(__name__)


def create_manuscript(db: Session, user: User, payload: ManuscriptCreateRequest):
    manuscript = manuscript_repo.create(
        db, user, payload.topic, payload.concept, payload.audience_level
    )
    logger.info(
        "manuscript created: manuscript_id=%s user_id=%s concept=%s",
        manuscript.id,
        user.id,
        manuscript.concept,
    )
    return manuscript


def list_manuscripts(db: Session, user: User):
    return manuscript_repo.list_by_user(db, user)


def get_manuscript(db: Session, user: User, manuscript_id: uuid.UUID):
    manuscript = manuscript_repo.get_owned(db, user, manuscript_id)
    if not manuscript:
        logger.warning(
            "manuscript not found or not owned: manuscript_id=%s user_id=%s",
            manuscript_id,
            user.id,
        )
        raise NotFoundError("원고를 찾을 수 없습니다.")
    return manuscript


def finalize_manuscript(
    db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID
):
    manuscript = get_manuscript(db, user, manuscript_id)
    version = manuscript_repo.get_version_owned(db, user, manuscript_id, version_id)
    if not version:
        raise NotFoundError("버전을 찾을 수 없습니다.")
    manuscript_repo.finalize(db, manuscript, version)
    logger.info(
        "manuscript finalized: manuscript_id=%s version_id=%s", manuscript_id, version_id
    )
    return manuscript

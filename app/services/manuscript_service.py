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


def group_manuscripts_by_date(manuscripts):
    """created_at 내림차순으로 정렬된 목록을 날짜(YYYY-MM-DD) 단위로 그룹핑한다."""
    groups = []
    current_date = None
    for manuscript in manuscripts:
        date_str = manuscript.created_at.strftime("%Y-%m-%d")
        if date_str != current_date:
            current_date = date_str
            groups.append({"date": current_date, "manuscripts": []})
        groups[-1]["manuscripts"].append(manuscript)
    return groups


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


def list_manuscript_versions(db: Session, user: User, manuscript_id: uuid.UUID):
    get_manuscript(db, user, manuscript_id)
    return manuscript_repo.list_versions_by_manuscript(db, user, manuscript_id)


def get_version_file(
    db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID, storage
):
    version = manuscript_repo.get_version_owned(db, user, manuscript_id, version_id)
    if not version:
        raise NotFoundError("버전을 찾을 수 없습니다.")
    content = storage.read(version.storage_key)
    filename = f"{version.kind}_v{version.revision}.md"
    return filename, content


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

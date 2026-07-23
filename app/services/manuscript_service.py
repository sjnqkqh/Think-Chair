import re
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.logging import get_logger
from app.models.user import User
from app.repositories import manuscript_repo
from app.schemas.manuscript import ManuscriptCreateRequest

logger = get_logger(__name__)

VERSION_KIND_LABELS = {
    "outline": "개요",
    "document": "문서",
}


def create_manuscript(db: Session, user: User, payload: ManuscriptCreateRequest):
    manuscript = manuscript_repo.create(
        db, user, payload.topic, payload.concept, payload.audience_level
    )
    logger.info(
        "manuscript.created",
        manuscript_id=manuscript.id,
        user_id=user.id,
        concept=manuscript.concept,
    )
    return manuscript


def get_manuscripts_list_by_user(db: Session, user: User):
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
            "manuscript.not_found_or_not_owned",
            manuscript_id=manuscript_id,
            user_id=user.id,
        )
        raise NotFoundError("원고를 찾을 수 없습니다.")
    return manuscript


def list_manuscript_versions(db: Session, user: User, manuscript_id: uuid.UUID):
    get_manuscript(db, user, manuscript_id)
    return manuscript_repo.list_versions_by_manuscript(db, user, manuscript_id)


def list_manuscript_versions_after(
    db: Session, user: User, manuscript_id: uuid.UUID, offset: int
):
    versions = list_manuscript_versions(db, user, manuscript_id)
    return versions[max(offset, 0) :]


def get_version_file(
    db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID, storage
):
    manuscript = get_manuscript(db, user, manuscript_id)
    version = manuscript_repo.get_version_owned(db, user, manuscript_id, version_id)
    if not version:
        raise NotFoundError("버전을 찾을 수 없습니다.")
    content = storage.read(version.storage_key)
    safe_topic = re.sub(r'[\\/:*?"<>|\s]+', "_", manuscript.topic).strip("_") or "원고"
    kind_label = VERSION_KIND_LABELS.get(version.kind, "문서")
    filename = f"{safe_topic}_{kind_label}_{version.revision:02d}.md"
    return filename, content


def delete_manuscript(db: Session, user: User, manuscript_id: uuid.UUID):
    manuscript = get_manuscript(db, user, manuscript_id)
    manuscript_repo.soft_delete(db, manuscript)
    logger.info("manuscript.soft_deleted", manuscript_id=manuscript_id, user_id=user.id)

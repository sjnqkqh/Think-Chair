import uuid

from sqlalchemy.orm import Session

from app.models.research import ResearchSource, ResearchSourceStatus
from app.research.vector_store import ResearchVectorStore
from app.services.storage.base import FileStorage


def tombstone_source(
    source_id: uuid.UUID,
    *,
    db: Session,
    storage: FileStorage,
    vector_store: ResearchVectorStore,
) -> bool:
    source = db.get(ResearchSource, source_id)
    if source is None:
        return False
    vector_store.delete_source(source.scope.value, str(source.id))
    storage.delete(source.storage_key)
    source.status = ResearchSourceStatus.TOMBSTONED
    db.commit()
    return True

import uuid

from sqlalchemy.orm import Session

from app.models.research import ResearchSource, ResearchSourceStatus
from app.research.evidence_index import ResearchEvidenceIndex
from app.services.storage.base import FileStorage


def exclude_source_from_corpus(
    source_id: uuid.UUID,
    *,
    db: Session,
    storage: FileStorage,
    evidence_index: ResearchEvidenceIndex,
) -> bool:
    source = db.get(ResearchSource, source_id)
    if source is None:
        return False
    evidence_index.remove_source_evidence(source.scope.value, str(source.id))
    storage.delete(source.storage_key)
    source.status = ResearchSourceStatus.EXCLUDED
    db.commit()
    return True

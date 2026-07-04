from langchain_core.runnables import RunnableConfig
import uuid

from app.graph.state import DraftsmithState
from app.models.manuscript import ManuscriptVersion


def _next_revision(db, manuscript_id: str, kind: str) -> int:
    last_manuscript = (
        db.query(ManuscriptVersion)
        .filter(
            ManuscriptVersion.manuscript_id == uuid.UUID(manuscript_id),
            ManuscriptVersion.kind == kind,
        )
        .order_by(ManuscriptVersion.revision.desc())
        .first()
    )
    return (last_manuscript.revision + 1) if last_manuscript else 1


def persist_version_node(state: DraftsmithState, config: RunnableConfig) -> dict:
    pending_version = state["pending_version"]
    storage = config["configurable"]["storage"]
    db = config["configurable"]["db_session"]

    key = f"{pending_version['kind']}s/{uuid.uuid4()}.md"
    storage.save(key, pending_version["content"].encode("utf-8"))

    row = ManuscriptVersion(
        manuscript_id=uuid.UUID(state["manuscript_id"]),
        kind=pending_version["kind"],
        revision=_next_revision(db, state["manuscript_id"], pending_version["kind"]),
        storage_key=key,
    )
    db.add(row)
    db.commit()

    return {
        "pending_version": {
            **pending_version,
            "storage_key": key,
            "version_id": str(row.id),
            "revision": row.revision,
        }
    }

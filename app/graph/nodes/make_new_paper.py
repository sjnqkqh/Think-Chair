import datetime
import uuid

from langchain_core.runnables import RunnableConfig

from app.graph.state import GraphState
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


def make_new_paper_node(state: GraphState, config: RunnableConfig) -> dict:
    new_paper = state["new_paper"]
    storage = config["configurable"]["storage"]
    db = config["configurable"]["db_session"]
    created_at = datetime.datetime.utcnow()

    key = f"{new_paper['kind']}s/{uuid.uuid4()}.md"
    storage.save(key, new_paper["content"].encode("utf-8"))

    row = ManuscriptVersion(
        manuscript_id=uuid.UUID(state["manuscript_id"]),
        kind=new_paper["kind"],
        revision=_next_revision(db, state["manuscript_id"], new_paper["kind"]),
        storage_key=key,
        created_at=created_at,
    )
    db.add(row)
    db.commit()

    return {
        "new_paper": {
            **new_paper,
            "storage_key": key,
            "version_id": str(row.id),
            "revision": row.revision,
            "created_at": created_at,
        }
    }

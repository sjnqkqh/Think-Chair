import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage
from app.models.manuscript import Manuscript


def create_message(
    db: Session,
    manuscript: Manuscript,
    role: str,
    content: str,
    phase: str | None,
) -> ChatMessage:
    last_sequence = (
        db.query(func.max(ChatMessage.sequence))
        .filter(ChatMessage.manuscript_id == manuscript.id)
        .scalar()
    )
    message = ChatMessage(
        id=uuid.uuid4(),
        manuscript_id=manuscript.id,
        role=role,
        content=content,
        phase=phase,
        sequence=(last_sequence or 0) + 1,
    )
    db.add(message)
    db.commit()
    return message

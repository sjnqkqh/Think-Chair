import datetime
import enum
import uuid

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConceptType(str, enum.Enum):
    TECH_DEEPDIVE = "딥다이브"
    RETROSPECTIVE = "회고"
    ESSAY = "에세이"
    TIL = "TIL"
    TEACHING = "수업 자료"


class ManuscriptStatus(str, enum.Enum):
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    POLISHING = "polishing"
    FINALIZED = "finalized"


class Manuscript(Base):
    __tablename__ = "manuscripts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255))
    concept: Mapped[ConceptType] = mapped_column(SAEnum(ConceptType))
    status: Mapped[ManuscriptStatus] = mapped_column(
        SAEnum(ManuscriptStatus), default=ManuscriptStatus.DRAFTING
    )
    audience_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_active_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )


class ManuscriptVersion(Base):
    __tablename__ = "manuscript_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manuscripts.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(255))
    is_finalized: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

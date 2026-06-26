import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class UploadHistory(Base):
    __tablename__ = "upload_histories"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    strategies_applied = Column(
        Text, nullable=False
    )  # JSON-serialized list of strategies
    chunks_count = Column(Text, nullable=False)  # JSON-serialized dict of chunks count
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EvalHistory(Base):
    __tablename__ = "eval_histories"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    ground_truth = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    results = relationship(
        "EvalResult", back_populates="eval_history", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id = Column(Integer, primary_key=True, index=True)
    eval_history_id = Column(Integer, ForeignKey("eval_histories.id"), nullable=False)
    strategy = Column(String, nullable=False)
    collection_name = Column(String, nullable=False)
    answer = Column(Text, nullable=False)
    contexts = Column(
        Text, nullable=False
    )  # JSON-serialized list of retrieved contexts

    # RAG Quality Scores
    faithfulness_score = Column(Integer, nullable=False)
    faithfulness_reason = Column(Text, nullable=True)
    relevance_score = Column(Integer, nullable=False)
    relevance_reason = Column(Text, nullable=True)
    precision_score = Column(Integer, nullable=False)
    precision_reason = Column(Text, nullable=True)

    eval_history = relationship("EvalHistory", back_populates="results")

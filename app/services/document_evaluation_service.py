import uuid

from app.models.manuscript import DocumentEvaluation
from app.services.evaluation_response_parser import EvaluationResult


def save_document_evaluation(
    db,
    manuscript_id: str,
    version_id: str,
    raw_output: str,
    checklist_id: str,
    evaluation: EvaluationResult,
) -> None:
    """평가 결과를 저장하고 트랜잭션을 확정한다."""
    db.add(
        DocumentEvaluation(
            manuscript_id=uuid.UUID(manuscript_id),
            version_id=uuid.UUID(version_id),
            score=evaluation["score"],
            verdict=evaluation["verdict"],
            reason=evaluation["reason"],
            improvements=evaluation["improvements"],
            checklist_id=checklist_id,
            raw_output=raw_output,
        )
    )
    db.commit()

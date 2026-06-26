from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import json

from app.core.database import get_database_session
from app.models.history import UploadHistory, EvalHistory

router = APIRouter()


@router.get("/history/uploads", summary="업로드 이력 조회")
async def get_upload_history(database_session: Session = Depends(get_database_session)):
    upload_histories = database_session.query(UploadHistory).order_by(UploadHistory.id.desc()).all()
    return [
        {
            "id": history_item.id,
            "filename": history_item.filename,
            "status": history_item.status,
            "error_message": history_item.error_message,
            "strategies_applied": json.loads(history_item.strategies_applied) if history_item.strategies_applied else [],
            "chunks_count": json.loads(history_item.chunks_count) if history_item.chunks_count else {},
            "created_at": history_item.created_at.isoformat(),
        }
        for history_item in upload_histories
    ]


@router.get("/history/evaluations", summary="RAG 성능 평가 이력 조회")
async def get_evaluation_history(database_session: Session = Depends(get_database_session)):
    evaluation_histories = database_session.query(EvalHistory).order_by(EvalHistory.id.desc()).all()
    results = []
    for history_item in evaluation_histories:
        evaluation_results = []
        for result_item in history_item.results:
            evaluation_results.append(
                {
                    "strategy": result_item.strategy,
                    "collection_name": result_item.collection_name,
                    "answer": result_item.answer,
                    "contexts": json.loads(result_item.contexts),
                    "scores": {
                        "faithfulness": {
                            "score": result_item.faithfulness_score,
                            "reason": result_item.faithfulness_reason,
                        },
                        "relevance": {
                            "score": result_item.relevance_score,
                            "reason": result_item.relevance_reason,
                        },
                        "precision": {
                            "score": result_item.precision_score,
                            "reason": result_item.precision_reason,
                        },
                    },
                }
            )
        results.append(
            {
                "id": history_item.id,
                "question": history_item.question,
                "ground_truth": history_item.ground_truth,
                "created_at": history_item.created_at.isoformat(),
                "results": evaluation_results,
            }
        )
    return results

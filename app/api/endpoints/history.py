import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.schemas.rag import UploadStatusResponse
from app.services.document import DocumentService
from app.services.evaluator import EvaluatorService

router = APIRouter()


@router.get(
    "/history/uploads",
    response_model=List[UploadStatusResponse],
    summary="업로드 이력 조회",
)
async def get_upload_history(database_session: Session = Depends(get_database_session)):
    upload_histories = DocumentService.get_all_upload_histories(database_session)
    return [
        UploadStatusResponse(
            id=history_item.id,
            filename=history_item.filename,
            status=history_item.status,
            error_message=history_item.error_message,
            strategies_applied=json.loads(history_item.strategies_applied) if history_item.strategies_applied else [],
            chunks_count=json.loads(history_item.chunks_count) if history_item.chunks_count else {},
            created_at=history_item.created_at,
        )
        for history_item in upload_histories
    ]


@router.get("/history/evaluations", summary="RAG 성능 평가 이력 조회")
async def get_evaluation_history(database_session: Session = Depends(get_database_session)):
    evaluation_histories = EvaluatorService.get_all_evaluation_histories(database_session)
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
                        "recall": {
                            "score": result_item.recall_score,
                            "reason": result_item.recall_reason,
                        },
                        "completeness": {
                            "score": result_item.completeness_score,
                            "reason": result_item.completeness_reason,
                        },
                        "noise_ratio": result_item.noise_ratio,
                        "coverage_rate": result_item.coverage_rate,
                        "hallucination_count": result_item.hallucination_count,
                        "gt_match_rate": result_item.gt_match_rate,
                        "avg_chunk_length": result_item.avg_chunk_length,
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


@router.delete("/history/uploads/{history_id}", summary="업로드 문서 및 임베딩 삭제")
async def delete_upload_history(
    history_id: int,
    database_session: Session = Depends(get_database_session)
):
    try:
        filename = DocumentService.delete_document_and_embeddings(database_session, history_id)
        return {
            "status": "success",
            "message": f"Successfully deleted document '{filename}' from database and vector store."
        }
    except HTTPException as exception:
        raise exception
    except Exception as exception:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(exception)}"
        )

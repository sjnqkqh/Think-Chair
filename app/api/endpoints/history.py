from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json

from app.core.database import get_database_session
from app.models.history import UploadHistory, EvalHistory
from app.core.vectorstore import VectorStoreManager

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
    upload_history_record = database_session.query(UploadHistory).filter(UploadHistory.id == history_id).first()
    if not upload_history_record:
        raise HTTPException(status_code=404, detail="Upload history not found")

    filename = upload_history_record.filename

    try:
        # 1. Chroma DB에서 관련된 모든 임베딩 삭제
        if upload_history_record.chunks_count:
            chunks_count_dict = json.loads(upload_history_record.chunks_count)
            vector_manager = VectorStoreManager()
            for collection_name, count in chunks_count_dict.items():
                document_ids = [f"{filename}_{collection_name}_{i}" for i in range(count)]
                vector_manager.delete_existing_documents(document_ids, collection_name=collection_name)

        # 2. SQLite DB에서 업로드 이력 삭제
        database_session.delete(upload_history_record)
        database_session.commit()

        # 3. BM25 리트리버 업데이트
        from app.services.rag import RagService
        try:
            RagService().init_bm25_retriever()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to reload BM25 retriever: {e}")

        return {
            "status": "success",
            "message": f"Successfully deleted document '{filename}' from database and vector store."
        }
    except Exception as exception:

        database_session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(exception)}"
        )

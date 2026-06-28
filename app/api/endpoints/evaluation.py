import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.rag import (
    EvaluationRequest,
    EvaluationResponse,
    EvaluationJSONRequest,
    EvaluationJSONResponse,
)
from app.services.evaluator import EvaluatorService
from app.core.database import get_database_session

logger = logging.getLogger(__name__)

router = APIRouter()
_evaluator_service_instance = None


def get_evaluator_service() -> EvaluatorService:
    global _evaluator_service_instance
    if _evaluator_service_instance is None:
        try:
            _evaluator_service_instance = EvaluatorService()
        except Exception as exception:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize Evaluator Service: {str(exception)}",
            )
    return _evaluator_service_instance


@router.post(
    "/evaluation/run", response_model=EvaluationResponse, summary="RAG 다중 청킹 성능 평가"
)
async def run_evaluation(
    request: EvaluationRequest,
    evaluator_service: EvaluatorService = Depends(get_evaluator_service),
    database_session: Session = Depends(get_database_session),
):
    try:
        results = await evaluator_service.run_batch_evaluation(
            database_session=database_session,
            question=request.question,
            ground_truth=request.ground_truth,
            strategies=request.strategies,
            top_k=request.top_k,
            use_ragas=request.use_ragas,
        )

        return EvaluationResponse(
            question=request.question,
            ground_truth=request.ground_truth,
            results=results
        )
    except Exception as exception:
        logger.error("Exception occurred in run_evaluation endpoint", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(exception)}")


@router.post(
    "/evaluation/run-json", response_model=EvaluationJSONResponse, summary="RAG 다중 QA 페어 성능 평가"
)
async def run_json_evaluation(
    request: EvaluationJSONRequest,
    evaluator_service: EvaluatorService = Depends(get_evaluator_service),
    database_session: Session = Depends(get_database_session),
):
    try:
        summaries, evaluations = await evaluator_service.run_json_dataset_evaluation(
            database_session=database_session,
            qa_pairs=request.qa_pairs,
            strategies=request.strategies,
            top_k=request.top_k,
            use_ragas=request.use_ragas,
        )

        return EvaluationJSONResponse(summaries=summaries, evaluations=evaluations)

    except Exception as exception:
        logger.error("Exception occurred in run_json_evaluation endpoint", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(exception)}")

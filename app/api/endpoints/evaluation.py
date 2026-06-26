from fastapi import APIRouter, HTTPException, Depends
import json
from sqlalchemy.orm import Session

from app.schemas.rag import EvaluationRequest, EvaluationResponse, StrategyEvaluationResult
from app.services.evaluator import EvaluatorService
from app.services.chunking import ChunkingService
from app.core.database import get_database_session
from app.models.history import EvalHistory, EvalResult

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
        # 1. Record basic evaluation request info
        evaluation_history_record = EvalHistory(question=request.question, ground_truth=request.ground_truth)
        database_session.add(evaluation_history_record)
        database_session.commit()
        database_session.refresh(evaluation_history_record)

        results = []
        for strategy in request.strategies:
            collection_name = ChunkingService.get_collection_name_for_strategy(strategy)

            evaluation_result = evaluator_service.run_evaluation_for_strategy(
                question=request.question,
                ground_truth=request.ground_truth,
                collection_name=collection_name,
                top_k=request.top_k,
                use_ragas=request.use_ragas,
            )

            strategy_description = f"{strategy.get('name')}"
            if strategy.get("name") in ["recursive", "character"]:
                strategy_description += f" (s={strategy.get('chunk_size')}, o={strategy.get('chunk_overlap')})"

            scores = evaluation_result["scores"]

            # 2. Record detailed evaluation result to database
            evaluation_result_record = EvalResult(
                eval_history_id=evaluation_history_record.id,
                strategy=strategy_description,
                collection_name=collection_name,
                answer=evaluation_result["answer"],
                contexts=json.dumps(evaluation_result["contexts"]),
                faithfulness_score=scores.get("faithfulness", {}).get("score", 0),
                faithfulness_reason=scores.get("faithfulness", {}).get("reason", ""),
                relevance_score=scores.get("relevance", {}).get("score", 0),
                relevance_reason=scores.get("relevance", {}).get("reason", ""),
                precision_score=scores.get("precision", {}).get("score", 0),
                precision_reason=scores.get("precision", {}).get("reason", ""),
            )
            database_session.add(evaluation_result_record)

            results.append(
                StrategyEvaluationResult(
                    strategy=strategy_description,
                    collection_name=collection_name,
                    answer=evaluation_result["answer"],
                    contexts=evaluation_result["contexts"],
                    scores=scores,
                )
            )

        database_session.commit()

        return EvaluationResponse(
            question=request.question, ground_truth=request.ground_truth, results=results
        )
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(exception)}")

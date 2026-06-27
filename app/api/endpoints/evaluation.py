from fastapi import APIRouter, HTTPException, Depends
import asyncio
import json
from sqlalchemy.orm import Session

from app.schemas.rag import (
    EvaluationRequest,
    EvaluationResponse,
    StrategyEvaluationResult,
    EvaluationJSONRequest,
    EvaluationJSONResponse,
    StrategySummary,
    QAPairEvaluationResult,
)
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
        evaluation_history_record = EvalHistory(question=request.question, ground_truth=request.ground_truth)
        database_session.add(evaluation_history_record)
        database_session.commit()
        database_session.refresh(evaluation_history_record)

        results = []
        for strategy in request.strategies:
            collection_name = ChunkingService.get_collection_name_for_strategy(strategy)

            evaluation_result = await evaluator_service.run_evaluation_for_strategy(
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
                recall_score=scores.get("recall", {}).get("score", 0),
                recall_reason=scores.get("recall", {}).get("reason", ""),
                completeness_score=scores.get("completeness", {}).get("score", 0),
                completeness_reason=scores.get("completeness", {}).get("reason", ""),
                noise_ratio=scores.get("noise_ratio", 0.0),
                coverage_rate=scores.get("coverage_rate", 0.0),
                hallucination_count=scores.get("hallucination_count", 0),
                gt_match_rate=scores.get("gt_match_rate", 0.0),
                avg_chunk_length=scores.get("avg_chunk_length", 0),
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


@router.post(
    "/evaluation/run-json", response_model=EvaluationJSONResponse, summary="RAG 다중 QA 페어 성능 평가"
)
async def run_json_evaluation(
    request: EvaluationJSONRequest,
    evaluator_service: EvaluatorService = Depends(get_evaluator_service),
    database_session: Session = Depends(get_database_session),
):
    try:
        async def evaluate_single_task(qa_item, strategy_item):
            col_name = ChunkingService.get_collection_name_for_strategy(strategy_item)
            eval_res = await evaluator_service.run_evaluation_for_strategy(
                question=qa_item.question,
                ground_truth=qa_item.answer,
                collection_name=col_name,
                top_k=request.top_k,
                use_ragas=request.use_ragas,
            )
            return qa_item, strategy_item, col_name, eval_res

        tasks = []
        for qa in request.qa_pairs:
            for strategy in request.strategies:
                tasks.append(evaluate_single_task(qa, strategy))

        completed = await asyncio.gather(*tasks)

        qa_groups = {}
        for qa_item, strategy_item, col_name, eval_res in completed:
            key = qa_item.question
            if key not in qa_groups:
                qa_groups[key] = {
                    "qa": qa_item,
                    "results": []
                }
            qa_groups[key]["results"].append((strategy_item, col_name, eval_res))

        strategy_stats = {}
        evaluations = []

        for key, group in qa_groups.items():
            qa = group["qa"]
            evaluation_history_record = EvalHistory(question=qa.question, ground_truth=qa.answer)
            database_session.add(evaluation_history_record)
            database_session.commit()
            database_session.refresh(evaluation_history_record)

            strategy_results = []
            for strategy_item, col_name, eval_res in group["results"]:
                strategy_description = f"{strategy_item.get('name')}"
                if strategy_item.get("name") in ["recursive", "character"]:
                    strategy_description += f" (s={strategy_item.get('chunk_size')}, o={strategy_item.get('chunk_overlap')})"

                scores = eval_res["scores"]

                evaluation_result_record = EvalResult(
                    eval_history_id=evaluation_history_record.id,
                    strategy=strategy_description,
                    collection_name=col_name,
                    answer=eval_res["answer"],
                    contexts=json.dumps(eval_res["contexts"]),
                    faithfulness_score=scores.get("faithfulness", {}).get("score", 0),
                    faithfulness_reason=scores.get("faithfulness", {}).get("reason", ""),
                    relevance_score=scores.get("relevance", {}).get("score", 0),
                    relevance_reason=scores.get("relevance", {}).get("reason", ""),
                    precision_score=scores.get("precision", {}).get("score", 0),
                    precision_reason=scores.get("precision", {}).get("reason", ""),
                    recall_score=scores.get("recall", {}).get("score", 0),
                    recall_reason=scores.get("recall", {}).get("reason", ""),
                    completeness_score=scores.get("completeness", {}).get("score", 0),
                    completeness_reason=scores.get("completeness", {}).get("reason", ""),
                    noise_ratio=scores.get("noise_ratio", 0.0),
                    coverage_rate=scores.get("coverage_rate", 0.0),
                    hallucination_count=scores.get("hallucination_count", 0),
                    gt_match_rate=scores.get("gt_match_rate", 0.0),
                    avg_chunk_length=scores.get("avg_chunk_length", 0),
                )
                database_session.add(evaluation_result_record)

                if strategy_description not in strategy_stats:
                    strategy_stats[strategy_description] = {
                        "faithfulness": [],
                        "relevance": [],
                        "precision": [],
                        "recall": [],
                        "completeness": [],
                        "noise_ratio": [],
                        "coverage_rate": [],
                        "gt_match_rate": [],
                        "avg_chunk_length": [],
                    }
                
                stats = strategy_stats[strategy_description]
                stats["faithfulness"].append(scores.get("faithfulness", {}).get("score", 0))
                stats["relevance"].append(scores.get("relevance", {}).get("score", 0))
                stats["precision"].append(scores.get("precision", {}).get("score", 0))
                stats["recall"].append(scores.get("recall", {}).get("score", 0))
                stats["completeness"].append(scores.get("completeness", {}).get("score", 0))
                stats["noise_ratio"].append(scores.get("noise_ratio", 0.0))
                stats["coverage_rate"].append(scores.get("coverage_rate", 0.0))
                stats["gt_match_rate"].append(scores.get("gt_match_rate", 0.0))
                stats["avg_chunk_length"].append(scores.get("avg_chunk_length", 0))

                strategy_results.append(
                    StrategyEvaluationResult(
                        strategy=strategy_description,
                        collection_name=col_name,
                        answer=eval_res["answer"],
                        contexts=eval_res["contexts"],
                        scores=scores,
                    )
                )

            evaluations.append(
                QAPairEvaluationResult(
                    id=qa.id,
                    question=qa.question,
                    ground_truth=qa.answer,
                    results=strategy_results,
                )
            )

        database_session.commit()

        summaries = []
        for strategy_desc, stats in strategy_stats.items():
            def get_avg(lst):
                return round(sum(lst) / len(lst), 2) if lst else 0.0

            summaries.append(
                StrategySummary(
                    strategy=strategy_desc,
                    faithfulness_avg=get_avg(stats["faithfulness"]),
                    relevance_avg=get_avg(stats["relevance"]),
                    precision_avg=get_avg(stats["precision"]),
                    recall_avg=get_avg(stats["recall"]),
                    completeness_avg=get_avg(stats["completeness"]),
                    noise_ratio_avg=get_avg(stats["noise_ratio"]),
                    coverage_rate_avg=get_avg(stats["coverage_rate"]),
                    gt_match_rate_avg=get_avg(stats["gt_match_rate"]),
                    avg_chunk_length_avg=get_avg(stats["avg_chunk_length"]),
                )
            )

        return EvaluationJSONResponse(summaries=summaries, evaluations=evaluations)

    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(exception)}")


"""
evaluate_with_ragas 단위 테스트

외부 API 호출 없이 ragas metric 의 single_turn_ascore 를 mock 처리하여
점수 변환 로직, 오류 처리, 반환 스키마를 검증한다.
"""
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evaluator import EvaluatorService, compute_coverage_rate, compute_gt_match_rate

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

QUESTION = "지각 3번 하면 어떻게 되나요?"
GROUND_TRUTH = "지각 3회 누적 시 1일 결석 처리됩니다."
CONTEXT = ["지각·조퇴·외출 3회 누적 시 1일 결석 처리", "결석은 연속 3일 초과 시 퇴소 사유"]
ANSWER = "지각을 3번 하면 1일 결석으로 처리됩니다."

REQUIRED_KEYS = {
    "faithfulness", "relevance", "precision", "recall",
    "completeness", "noise_ratio", "coverage_rate",
    "hallucination_count", "gt_match_rate", "avg_chunk_length",
}

_METRIC_PATHS = [
    "ragas.metrics._faithfulness.Faithfulness.single_turn_ascore",
    "ragas.metrics._answer_relevance.AnswerRelevancy.single_turn_ascore",
    "ragas.metrics._context_precision.ContextPrecision.single_turn_ascore",
    "ragas.metrics._context_recall.ContextRecall.single_turn_ascore",
]

_RAGAS_INFRA_PATCHES = {
    "ragas.llms.LangchainLLMWrapper": MagicMock(),
    "ragas.embeddings.LangchainEmbeddingsWrapper": MagicMock(),
    "langchain_google_genai.GoogleGenerativeAIEmbeddings": MagicMock(),
}


def _apply_patches(stack: ExitStack, metric_scores):
    """공통 mock 셋을 ExitStack 에 등록."""
    for target, return_val in _RAGAS_INFRA_PATCHES.items():
        stack.enter_context(patch(target, return_value=return_val))
    for path, score in zip(_METRIC_PATHS, metric_scores):
        stack.enter_context(patch(path, new=AsyncMock(return_value=score)))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def evaluator():
    """외부 의존성(LLM, VectorStore)을 mock 처리한 EvaluatorService"""
    with patch("app.services.evaluator.VectorStoreManager"), \
         patch("app.services.evaluator.LLMManager"), \
         patch("app.services.evaluator.ChatOpenAI"):
        svc = EvaluatorService.__new__(EvaluatorService)
        svc.judge_llm = MagicMock()
        svc.vector_store_manager = MagicMock()
        svc.llm_manager = MagicMock()
        svc.judge_prompt = MagicMock()
        return svc


# ---------------------------------------------------------------------------
# 순수 함수 테스트
# ---------------------------------------------------------------------------

def test_compute_coverage_rate_full_match():
    rate = compute_coverage_rate("지각 결석", ["지각 결석 처리"])
    assert 0.0 <= rate <= 1.0


def test_compute_coverage_rate_empty_gt():
    assert compute_coverage_rate("", ["some context"]) == 0.0


def test_compute_gt_match_rate_empty_inputs():
    assert compute_gt_match_rate("", "answer") == 0.0
    assert compute_gt_match_rate("ground truth", "") == 0.0


# ---------------------------------------------------------------------------
# evaluate_with_ragas 핵심 경로
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_with_ragas_returns_all_keys(evaluator):
    """정상 동작 시 반환 딕셔너리에 필수 키가 모두 존재해야 한다."""
    with ExitStack() as stack:
        _apply_patches(stack, [0.8, 0.6, 0.4, 1.0])
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, CONTEXT, ANSWER)

    assert REQUIRED_KEYS.issubset(result.keys()), f"Missing keys: {REQUIRED_KEYS - result.keys()}"


@pytest.mark.asyncio
async def test_evaluate_with_ragas_score_conversion(evaluator):
    """0~1 ragas 점수가 1~5 정수로 올바르게 변환되어야 한다."""
    # 1.0→5, 0.0→1, 0.6→3, 0.8→4
    with ExitStack() as stack:
        _apply_patches(stack, [1.0, 0.0, 0.6, 0.8])
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, CONTEXT, ANSWER)

    assert result["faithfulness"]["score"] == 5
    assert result["relevance"]["score"] == 1
    assert result["precision"]["score"] == 3
    assert result["recall"]["score"] == 4


@pytest.mark.asyncio
async def test_evaluate_with_ragas_score_clamped_to_1_5(evaluator):
    """변환 점수는 반드시 1~5 범위를 벗어나지 않아야 한다."""
    with ExitStack() as stack:
        _apply_patches(stack, [0.8, 0.6, 0.4, 1.0])
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, CONTEXT, ANSWER)

    for key in ("faithfulness", "relevance", "precision", "recall"):
        score = result[key]["score"]
        assert 1 <= score <= 5, f"{key} score {score} is out of [1, 5]"


@pytest.mark.asyncio
async def test_evaluate_with_ragas_metric_failure_falls_back_to_1(evaluator):
    """메트릭이 예외를 던지면 해당 지표 score 는 1로 fallback 되어야 한다."""
    with ExitStack() as stack:
        for target, return_val in _RAGAS_INFRA_PATCHES.items():
            stack.enter_context(patch(target, return_value=return_val))
        for path in _METRIC_PATHS:
            stack.enter_context(
                patch(path, new=AsyncMock(side_effect=RuntimeError("LLM error")))
            )
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, CONTEXT, ANSWER)

    for key in ("faithfulness", "relevance", "precision", "recall"):
        assert result[key]["score"] == 1, f"Expected fallback score 1 for {key}"
        assert "Ragas error" in result[key]["reason"]


@pytest.mark.asyncio
async def test_evaluate_with_ragas_deterministic_fields(evaluator):
    """LLM 없이 계산되는 필드는 항상 올바른 타입과 값 범위를 가져야 한다."""
    with ExitStack() as stack:
        _apply_patches(stack, [0.8, 0.6, 0.4, 1.0])
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, CONTEXT, ANSWER)

    assert 0.0 <= result["coverage_rate"] <= 1.0
    assert 0.0 <= result["gt_match_rate"] <= 1.0
    assert isinstance(result["avg_chunk_length"], int)
    assert result["avg_chunk_length"] > 0
    assert result["noise_ratio"] == 0.0
    assert result["hallucination_count"] == 0
    assert result["completeness"]["score"] == 0


@pytest.mark.asyncio
async def test_evaluate_with_ragas_empty_context(evaluator):
    """빈 context 리스트 입력 시 avg_chunk_length 가 0이고 오류 없이 반환되어야 한다."""
    with ExitStack() as stack:
        _apply_patches(stack, [0.5, 0.5, 0.5, 0.5])
        result = await evaluator.evaluate_with_ragas(QUESTION, GROUND_TRUTH, [], ANSWER)

    assert result["avg_chunk_length"] == 0

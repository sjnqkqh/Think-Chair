import json
from typing import TypedDict


class EvaluationResult(TypedDict):
    score: int | None
    verdict: str | None
    reason: str | None
    improvements: str | None
    has_unnecessary_header: bool | None
    has_unnecessary_footer: bool | None


def parse_evaluation_response(raw_output: str) -> EvaluationResult:
    """LLM JSON 출력을 평가 결과로 정규화한다."""
    try:
        data = json.loads(_strip_code_fence(raw_output))
    except (json.JSONDecodeError, TypeError):
        return _empty_evaluation()

    if not isinstance(data, dict):
        return _empty_evaluation()

    improvements = data.get("improvements")
    score = data.get("score")
    verdict = data.get("verdict")
    reason = data.get("reason")
    has_unnecessary_header = data.get("has_unnecessary_header")
    has_unnecessary_footer = data.get("has_unnecessary_footer")
    return {
        "score": score if isinstance(score, int) and not isinstance(score, bool) else None,
        "verdict": verdict if isinstance(verdict, str) else None,
        "reason": reason if isinstance(reason, str) else None,
        "improvements": (
            json.dumps(improvements, ensure_ascii=False)
            if improvements is not None
            else None
        ),
        "has_unnecessary_header": (
            has_unnecessary_header
            if isinstance(has_unnecessary_header, bool)
            else None
        ),
        "has_unnecessary_footer": (
            has_unnecessary_footer
            if isinstance(has_unnecessary_footer, bool)
            else None
        ),
    }


def _empty_evaluation() -> EvaluationResult:
    return {
        "score": None,
        "verdict": None,
        "reason": None,
        "improvements": None,
        "has_unnecessary_header": None,
        "has_unnecessary_footer": None,
    }


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()

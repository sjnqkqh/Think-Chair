import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    reason: str


def parse_sufficiency_response(raw_output: str) -> SufficiencyDecision | None:
    """게이트 LLM 출력이 계약한 JSON 형식일 때만 판정 결과를 반환한다."""
    try:
        data = json.loads(_strip_code_fence(raw_output))
    except (json.JSONDecodeError, TypeError):
        return None

    if not _has_valid_schema(data):
        return None

    return SufficiencyDecision(
        sufficient=data["sufficient"],
        reason=data.get("reason", "").strip(),
    )


def _has_valid_schema(data: object) -> bool:
    if not isinstance(data, dict) or set(data) - {"sufficient", "reason"}:
        return False
    if not isinstance(data.get("sufficient"), bool):
        return False
    return data.get("reason") is None or isinstance(data["reason"], str)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()

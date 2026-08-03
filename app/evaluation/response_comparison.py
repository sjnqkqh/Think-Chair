import json
from typing import Callable

from app.evaluation.response_comparison_contracts import (
    ComparisonWinner,
    GeneratedResponse,
    PairwiseJudgment,
)
from app.evaluation.text_parsing import strip_code_fence

_LABEL_WINNERS = {"A", "B", "tie"}
PromptInvoker = Callable[[str], str]


def build_comparison_prompt(
    *,
    ai_question: str,
    human_response: str,
    answer_a: GeneratedResponse,
    answer_b: GeneratedResponse,
) -> str:
    return f"""당신은 AI 대화 응답 비교 평가자입니다.
같은 상황에서 나온 Answer A와 Answer B를 비교하십시오.

평가 기준:
- specificity: 막연한 말 대신 수치·사례·근거로 얼마나 구체화했는지
- naturalness: 대화 흐름이 자연스러운지, 어색한 조사 보고문이 되지 않았는지
- accuracy: 틀린 사실·과장·근거 없는 단정을 덜 했는지
- overall: 위 기준을 종합한 전체 선호

답변 형태가 설명형이든 질문형이든 같은 기준으로 비교하십시오.
출처 ID의 존재 여부는 검사하지 마십시오.

[AI 질문]
{ai_question}

[사용자 답변]
{human_response}

[Answer A]
{answer_a.body}

[Answer B]
{answer_b.body}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"specificity_winner":"A|B|tie","naturalness_winner":"A|B|tie","accuracy_winner":"A|B|tie","overall_winner":"A|B|tie","reason":"짧은 판정 이유"}}"""


def parse_comparison_judgment(raw_output: str) -> dict[str, str]:
    data = json.loads(strip_code_fence(raw_output))
    if not isinstance(data, dict):
        raise ValueError("comparison judgment must be a JSON object")

    parsed: dict[str, str] = {}
    for key in (
        "specificity_winner",
        "naturalness_winner",
        "accuracy_winner",
        "overall_winner",
    ):
        value = data.get(key)
        if value not in _LABEL_WINNERS:
            raise ValueError(f"invalid {key}: {value!r}")
        parsed[key] = value

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    parsed["reason"] = reason.strip()
    return parsed


def combine_order_swapped_judgments(
    first_pass: dict[str, str],
    second_pass: dict[str, str],
) -> PairwiseJudgment:
    """first: A=baseline/B=grounded, second: A=grounded/B=baseline."""
    first_mapped = _map_pass(first_pass, a_role="baseline")
    second_mapped = _map_pass(second_pass, a_role="grounded")

    return PairwiseJudgment(
        specificity_winner=_stable_winner(
            first_mapped["specificity_winner"],
            second_mapped["specificity_winner"],
        ),
        naturalness_winner=_stable_winner(
            first_mapped["naturalness_winner"],
            second_mapped["naturalness_winner"],
        ),
        accuracy_winner=_stable_winner(
            first_mapped["accuracy_winner"],
            second_mapped["accuracy_winner"],
        ),
        overall_winner=_stable_winner(
            first_mapped["overall_winner"],
            second_mapped["overall_winner"],
        ),
        reason=first_pass["reason"],
        order_flipped=first_mapped["overall_winner"] != second_mapped["overall_winner"],
    )


def compare_response_pair(
    *,
    ai_question: str,
    human_response: str,
    baseline: GeneratedResponse,
    grounded: GeneratedResponse,
    invoke: PromptInvoker,
) -> PairwiseJudgment:
    first_prompt = build_comparison_prompt(
        ai_question=ai_question,
        human_response=human_response,
        answer_a=baseline,
        answer_b=grounded,
    )
    second_prompt = build_comparison_prompt(
        ai_question=ai_question,
        human_response=human_response,
        answer_a=grounded,
        answer_b=baseline,
    )
    first = parse_comparison_judgment(invoke(first_prompt))
    second = parse_comparison_judgment(invoke(second_prompt))
    return combine_order_swapped_judgments(first, second)


def _map_pass(
    payload: dict[str, str], *, a_role: ComparisonWinner
) -> dict[str, ComparisonWinner]:
    b_role: ComparisonWinner = "grounded" if a_role == "baseline" else "baseline"
    return {
        key: _map_label(payload[key], a_role=a_role, b_role=b_role)
        for key in (
            "specificity_winner",
            "naturalness_winner",
            "accuracy_winner",
            "overall_winner",
        )
    }


def _map_label(
    label: str, *, a_role: ComparisonWinner, b_role: ComparisonWinner
) -> ComparisonWinner:
    if label == "tie":
        return "tie"
    if label == "A":
        return a_role
    if label == "B":
        return b_role
    raise ValueError(f"invalid winner label: {label!r}")


def _stable_winner(
    first: ComparisonWinner, second: ComparisonWinner
) -> ComparisonWinner:
    if first == second:
        return first
    return "tie"

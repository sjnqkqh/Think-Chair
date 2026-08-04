import json
from typing import Callable

from app.evaluation.response_comparison_contracts import (
    AnswerScores,
    ComparisonWinner,
    GeneratedResponse,
    PairwiseJudgment,
)
from app.evaluation.text_parsing import strip_code_fence

_CRITERIA = ("specificity", "naturalness", "accuracy", "overall")
PromptInvoker = Callable[[str], str]


def build_comparison_prompt(
    *,
    ai_question: str,
    human_response: str,
    answer_a: GeneratedResponse,
    answer_b: GeneratedResponse,
) -> str:
    return f"""당신은 AI 대화 응답 비교 평가자입니다.
같은 상황에서 나온 Answer A와 Answer B를 비교하고, 각 기준마다 100점 만점 점수를 매기십시오.

평가 기준:
- specificity: 막연한 말 대신 수치·사례·근거로 얼마나 구체화했는지
- naturalness: 대화 흐름이 자연스러운지, 어색한 조사 보고문이 되지 않았는지
- accuracy: 틀린 사실·과장·근거 없는 단정을 덜 했는지
- overall: 위 기준을 종합한 전체 품질

점수는 정수 0~100입니다. A와 B를 같은 기준으로 상대 비교한 뒤 절대 점수로 남기십시오.
답변 형태가 설명형이든 질문형이든 같은 기준으로 평가하십시오.
출처 ID의 존재 여부는 검사하지 마십시오.
reason에는 왜 그런 점수인지 짧은 정성 평가를 쓰십시오.

[AI 질문]
{ai_question}

[사용자 답변]
{human_response}

[Answer A]
{answer_a.body}

[Answer B]
{answer_b.body}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"specificity":{{"A":0,"B":0}},"naturalness":{{"A":0,"B":0}},"accuracy":{{"A":0,"B":0}},"overall":{{"A":0,"B":0}},"reason":"짧은 정성 평가"}}"""


def parse_comparison_judgment(raw_output: str) -> dict:
    data = json.loads(strip_code_fence(raw_output))
    if not isinstance(data, dict):
        raise ValueError("comparison judgment must be a JSON object")

    parsed: dict = {}
    for key in _CRITERIA:
        value = data.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object with A/B scores")
        parsed[key] = {
            "A": _parse_score(value.get("A"), key=f"{key}.A"),
            "B": _parse_score(value.get("B"), key=f"{key}.B"),
        }

    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    parsed["reason"] = reason.strip()
    return parsed


def combine_order_swapped_judgments(
    first_pass: dict,
    second_pass: dict,
) -> PairwiseJudgment:
    """first: A=baseline/B=grounded, second: A=grounded/B=baseline."""
    first_scores = _map_pass_scores(first_pass, a_role="baseline")
    second_scores = _map_pass_scores(second_pass, a_role="grounded")
    baseline = _average_scores(first_scores["baseline"], second_scores["baseline"])
    grounded = _average_scores(first_scores["grounded"], second_scores["grounded"])

    first_overall = _winner_from_scores(
        first_scores["baseline"].overall,
        first_scores["grounded"].overall,
    )
    second_overall = _winner_from_scores(
        second_scores["baseline"].overall,
        second_scores["grounded"].overall,
    )
    order_flipped = first_overall != second_overall

    return PairwiseJudgment(
        baseline_scores=baseline,
        grounded_scores=grounded,
        specificity_winner=_winner_from_scores(
            baseline.specificity, grounded.specificity
        ),
        naturalness_winner=_winner_from_scores(
            baseline.naturalness, grounded.naturalness
        ),
        accuracy_winner=_winner_from_scores(baseline.accuracy, grounded.accuracy),
        overall_winner=(
            "tie"
            if order_flipped
            else _winner_from_scores(baseline.overall, grounded.overall)
        ),
        reason=first_pass["reason"],
        order_flipped=order_flipped,
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


def _parse_score(value, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {key}: {value!r}")
    score = int(value)
    if score != value:
        raise ValueError(f"invalid {key}: {value!r}")
    if not 0 <= score <= 100:
        raise ValueError(f"{key} must be 0..100, got {score}")
    return score


def _map_pass_scores(
    payload: dict, *, a_role: ComparisonWinner
) -> dict[str, AnswerScores]:
    b_role: ComparisonWinner = "grounded" if a_role == "baseline" else "baseline"
    by_role = {
        a_role: {key: payload[key]["A"] for key in _CRITERIA},
        b_role: {key: payload[key]["B"] for key in _CRITERIA},
    }
    return {
        "baseline": AnswerScores(**by_role["baseline"]),
        "grounded": AnswerScores(**by_role["grounded"]),
    }


def _average_scores(first: AnswerScores, second: AnswerScores) -> AnswerScores:
    return AnswerScores(
        specificity=round((first.specificity + second.specificity) / 2),
        naturalness=round((first.naturalness + second.naturalness) / 2),
        accuracy=round((first.accuracy + second.accuracy) / 2),
        overall=round((first.overall + second.overall) / 2),
    )


def _winner_from_scores(baseline: int, grounded: int) -> ComparisonWinner:
    if baseline > grounded:
        return "baseline"
    if grounded > baseline:
        return "grounded"
    return "tie"

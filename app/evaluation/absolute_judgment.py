import json
from typing import Callable

from app.evaluation.response_comparison_contracts import AnswerScores
from app.evaluation.service_growth_contracts import AbsoluteJudgment
from app.evaluation.text_parsing import strip_code_fence

PromptInvoker = Callable[[str], str]

_CRITERIA = ("specificity", "naturalness", "accuracy", "overall")


def build_absolute_judgment_prompt(
    *,
    claim: str,
    topic: str,
    phase: str,
    response_body: str,
    evidence_text: str,
) -> str:
    evidence_block = evidence_text.strip() if evidence_text.strip() else "(주입된 근거 없음)"
    return f"""당신은 Think Chair 대화 응답을 채점하는 **엄격한(깐깐한)** 평가자입니다.
호의적이거나 관대한 채점을 하지 마십시오. 평범한 무난한 답은 대략 40~60점대에 두십시오.
80점 이상은 수치·사례·한계·검증 가능한 구체성이 분명할 때만 주십시오.

평가 기준 (각 0~100 정수):
- specificity: 막연한 일반론 대신 수치·사례·조건·한계로 얼마나 구체화했는지
- naturalness: 글쓰기 대화로서 자연스러운지. 조사 보고문처럼 어색하면 감점
- accuracy: 틀린 사실·과장·근거 없는 단정이 없는지. 근거가 있는데도 무시·오용이면 크게 감점
- overall: 위 기준을 종합한 전체 품질

감점 예:
- 상투적 동의, 일반론 되풀이, “그렇다/도움이 된다”만 있는 답
- 확인 질문만 하고 주장에 실질적 보강이 없음
- 주입된 근거가 있는데 반영하지 않음
- 근거에 없는 수치를 단정함

reason에는 점수 근거와 **감점 사유**를 짧게 적으십시오.

[원고 주제]
{topic}

[대화 위상]
{phase}

[사용자 일반론/주장]
{claim}

[주입된 근거]
{evidence_block}

[AI 응답]
{response_body}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"specificity":0,"naturalness":0,"accuracy":0,"overall":0,"reason":"감점 사유 포함 짧은 평가"}}"""


def parse_absolute_judgment(raw_output: str) -> AbsoluteJudgment:
    data = json.loads(strip_code_fence(raw_output))
    if not isinstance(data, dict):
        raise ValueError("absolute judgment must be a JSON object")
    scores: dict[str, int] = {}
    for key in _CRITERIA:
        scores[key] = _parse_score(data.get(key), key=key)
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    return AbsoluteJudgment(
        scores=AnswerScores(**scores),
        reason=reason.strip(),
    )


def judge_response_absolutely(
    *,
    claim: str,
    topic: str,
    phase: str,
    response_body: str,
    evidence_text: str,
    invoke: PromptInvoker,
) -> AbsoluteJudgment:
    prompt = build_absolute_judgment_prompt(
        claim=claim,
        topic=topic,
        phase=phase,
        response_body=response_body,
        evidence_text=evidence_text,
    )
    return parse_absolute_judgment(invoke(prompt))


def _parse_score(value: object, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer 0~100")
    if value < 0 or value > 100:
        raise ValueError(f"{key} must be an integer 0~100")
    return value

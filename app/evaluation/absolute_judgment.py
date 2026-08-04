import json
from typing import Callable

from app.evaluation.service_growth_contracts import AbsoluteAnswerScores, AbsoluteJudgment
from app.evaluation.text_parsing import strip_code_fence

PromptInvoker = Callable[[str], str]

_CRITERIA = (
    "reference_suggestion",
    "claim_sharpening",
    "knowledge_depth",
    "dialogue_fit",
    "next_step_clarity",
    "overall",
)


def build_absolute_judgment_prompt(
    *,
    claim: str,
    topic: str,
    phase: str,
    response_body: str,
) -> str:
    return f"""당신은 Think Chair 글쓰기 코칭 응답을 채점하는 엄격한 평가자입니다.

제품 목적:
- AI가 사용자에게 **정답을 대신 말해 주는 것**이 목표가 아닙니다.
- 사용자가 자신의 주장에 대해 **더 깊은 지식을 쌓고, 더 명확한 근거를 갖도록** 돕는 것이 목표입니다.
- 따라서 고득점의 핵심은 “맞다/틀리다를 잘 판정했는가”가 아니라,
  **문맥에 맞는 참고자료·검증 경로를 제안해 사용자가 스스로 근거를 확보하게 했는가**입니다.

채점하지 말 것:
- RAG/검색을 시스템 내부에서 썼는지 여부
- 모델이 스스로 완벽한 사실 단정을 얼마나 많이 했는지 (단정만 많고 자료 제안이 없으면 감점)

호의적이거나 관대한 채점을 하지 마십시오.
같은 claim+응답 텍스트에는 **같은 점수대**를 유지하십시오. 임의로 흔들지 마십시오.

점수 밴드 (각 기준 공통):
- 0~20: 공허·상투적 동의, 자료/검증 경로 전무, 사용자 지식 심화와 무관
- 21~40: 약함. 질문만 하거나 일반론 되풀이. 참고 방향이 막연함
- 41~60: 무난. 대화는 되지만 근거를 쌓게 하는 구체 자료·검증 힌트가 부족 (평범한 답의 기본 구간)
- 61~80: 좋음. 문맥에 맞는 자료 유형·찾아볼 곳·검증할 포인트가 분명함
- 81~100: 뛰어남. 사용자가 바로 열어볼 수 있을 만큼 구체적인 참고(문서·스펙·논문·공식 가이드·URL 등)와 그 자료로 무엇을 확인할지까지 연결됨

평가 기준 (각 0~100 정수):
- reference_suggestion: 원고 주제·사용자 주장 문맥에 맞는 참고자료·출처 유형·찾아볼 곳을 제안했는지.
  URL·문서명·공식 문서 종류·검색어·섹션 힌트 등이 구체적일수록 가점.
  “알아서 찾아보세요” 수준이면 낮음.
- claim_sharpening: 사용자 일반론을 검증 가능한 주장으로 좁히거나, 전제·범위를 드러내게 도왔는지
- knowledge_depth: 표면 동의 이상으로, 왜/언제/한계까지 생각하게 만들어 지식을 깊게 했는지
- dialogue_fit: 글쓰기 코칭 대화로서 톤이 자연스러운지 (조사 보고문·정답 강의 독백만이면 감점)
- next_step_clarity: 사용자가 다음에 읽을 것·확인할 것·원고에 적을 것이 분명한지
- overall: 위 기준 종합. 특히 reference_suggestion이 약하면 overall도 크게 낮출 것

감점 예:
- “맞아요, 보통 그렇습니다”만 있는 상투적 동의
- 확인 질문만 반복하고 참고·검증 경로가 없음
- 모델이 수치를 단정만 하고, 사용자가 확인할 자료는 안내하지 않음
- 주제와 무관한 링크·자료 남발

reason에는 점수 밴드 근거와 **감점 사유**를 짧게 적으십시오.
“정답을 잘 말했다”를 고득점 이유로 쓰지 말고, **근거를 쌓게 했는지**를 중심으로 쓰십시오.

[원고 주제]
{topic}

[대화 위상]
{phase}

[사용자 일반론/주장]
{claim}

[AI 응답]
{response_body}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"reference_suggestion":0,"claim_sharpening":0,"knowledge_depth":0,"dialogue_fit":0,"next_step_clarity":0,"overall":0,"reason":"감점 사유 포함 짧은 평가"}}"""


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
        scores=AbsoluteAnswerScores(**scores),
        reason=reason.strip(),
    )


def judge_response_absolutely(
    *,
    claim: str,
    topic: str,
    phase: str,
    response_body: str,
    invoke: PromptInvoker,
) -> AbsoluteJudgment:
    prompt = build_absolute_judgment_prompt(
        claim=claim,
        topic=topic,
        phase=phase,
        response_body=response_body,
    )
    return parse_absolute_judgment(invoke(prompt))


def _parse_score(value: object, *, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer 0~100")
    if value < 0 or value > 100:
        raise ValueError(f"{key} must be an integer 0~100")
    return value

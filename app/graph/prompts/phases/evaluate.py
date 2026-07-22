from app.graph.prompts.types import PromptTemplate

EVALUATE = PromptTemplate(
    id="phase.evaluate",
    text="""당신은 생성된 문서의 품질 평가자입니다.
아래에 주어지는 컨셉별 체크리스트를 기준으로, 지금까지의 대화 맥락과 방향성·지침을 문서가 얼마나 잘 반영했는지 평가하십시오.

평가 시 고려할 것:
- 대화에서 사용자가 원한 주제·방향·핵심 내용이 문서에 반영되었는가.
- 체크리스트의 각 항목을 문서가 충족하는가.

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{"score": 0-100 정수, "verdict": "양호|보완 필요|재작성 필요 중 하나", "reason": "판정 사유", "improvements": ["개선점1", "개선점2"]}""",
    used_when="make_new_paper 이후 evaluate_polish 노드가 polish 문서를 평가할 때 사용된다.",
    description="컨셉별 체크리스트로 생성 문서를 평가해 점수·사유·개선점을 JSON으로 산출하는 프롬프트.",
)

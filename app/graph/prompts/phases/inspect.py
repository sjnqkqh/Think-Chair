from app.graph.prompts.types import PromptTemplate

INSPECT = PromptTemplate(
    id="phase.inspect",
    text="""지금은 점검(inspect) 단계입니다.
- 위에 주어지는 이 컨셉의 점검 기준(체크리스트)을 기준으로, 사용자가 제공한 내용에서 빠지거나 모호한 부분을 짚어 질문하십시오.
- 아직 원고를 작성하지 마십시오. 대화로만 내용을 구체화하십시오.""",
    used_when="user_action == 'inspect' 로 converse 노드가 호출될 때 사용된다.",
    description="점검 단계 지시문. 원고 작성 전 내용 보완을 유도한다.",
)

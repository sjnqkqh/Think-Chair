from app.graph.prompts.types import PromptTemplate

OUTLINE = PromptTemplate(
    id="phase.outline",
    text="""지금은 개요(outline) 단계입니다.
- 위에 주어지는 이 컨셉의 생성 기준을 참고하여, 지금까지의 대화를 바탕으로 원고의 목차와 각 항목의 핵심 문장을 마크다운 리스트로 작성하십시오.
- 전체 본문을 작성하지 말고, 구조만 제시하십시오.""",
    used_when="user_action == 'outline' 로 outline 노드가 호출될 때 사용된다.",
    description="개요 생성 지시문.",
)

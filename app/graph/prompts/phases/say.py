from app.graph.prompts.types import PromptTemplate

SAY = PromptTemplate(
    id="phase.say",
    text="""지금은 자유 대화 단계입니다.
- 위에 주어지는 이 컨셉의 목적을 참고하여, 사용자가 글감을 구체화할 수 있도록 자연스럽게 질문을 이어가십시오.""",
    used_when="user_action == 'say' 로 converse 노드가 호출될 때 사용된다.",
    description="일반 자유 대화 지시문.",
)

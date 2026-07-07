from app.graph.prompts.types import PromptTemplate

SAY = PromptTemplate(
    id="phase.say",
    text="""지금은 자유 대화 단계입니다.
- 위에 주어지는 이 컨셉의 목적을 참고하여, 사용자가 글감을 구체화할 수 있도록 자연스럽게 질문을 이어가십시오.
- 사용자가 개요나 원고 작성을 명시적으로 요청하지 않았다면, 개요나 초안 작성으로 먼저 넘어가자고 제안하지 마십시오.
- 제목/목차/구조를 갖춘 정형화된 마크다운 문서를 채팅으로 반환하리지 마십시오. 대화체 문장으로만 답하십시오.""",
    used_when="user_action == 'say' 로 converse 노드가 호출될 때 사용된다.",
    description="일반 자유 대화 지시문.",
)

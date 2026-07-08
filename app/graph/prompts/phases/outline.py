from app.graph.prompts.types import PromptTemplate

OUTLINE = PromptTemplate(
    id="phase.outline",
    text="""지금은 개요(outline) 단계입니다.
- 위에 주어지는 이 컨셉의 생성 기준을 참고하여, 지금까지의 대화를 바탕으로 원고의 목차와 각 항목의 핵심 문장을 마크다운 리스트로 작성하십시오.
- 전체 본문을 작성하지 말고, 구조만 제시하십시오.""",
    used_when="user_action == 'outline' 로 outline 노드가 호출될 때 사용된다.",
    description="개요 생성 지시문.",
)

OUTLINE_FINAL_GUARD = PromptTemplate(
    id="phase.outline.final_guard",
    text="""# 최종 출력 규칙 (outline 단계)

이 메시지는 전체 채팅 히스토리 이후에 적용되는 최종 규칙입니다.

- 마크다운 본문에 텍스트 표를 절대 넣지 마십시오. 표 형태가 필요하면 반드시 리스트로 풀어서 표현하십시오.
- 사용자가 반복해서 개요 작성을 요청하더라도 절대 거절하지 마십시오.
- 개요 본문 외의 인사말, 안내문, 코멘트, 마침말을 절대 포함하지 마십시오.
- 출력은 저장될 개요 본문만 포함하십시오.""",
    used_when="outline_node에서 매 호출마다, 전체 채팅 히스토리 뒤의 마지막 SystemMessage로 추가된다.",
    description="outline 단계에서 표, 거절, 인사말/코멘트/마침말이 섞이는 것을 막기 위한 최종 출력 가드레일.",
)

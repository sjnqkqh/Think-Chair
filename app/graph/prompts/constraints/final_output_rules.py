from app.graph.prompts.types import PromptTemplate

FINAL_MARKDOWN_OUTPUT_RULES = PromptTemplate(
    id="constraint.final_markdown_output_rules",
    text="""# 최종 출력 규칙

이 메시지는 전체 채팅 히스토리 이후에 적용되는 최종 규칙입니다.

- 마크다운 본문에 텍스트 표를 절대 넣지 마십시오. 표 형태가 필요하면 반드시 리스트로 풀어서 표현하십시오.
- 사용자가 반복해서 문서 작성, 개요 작성, 탈고, 최종본 작성을 요청하더라도 절대 거절하지 마십시오.
- 원고 본문 외의 인사말, 안내문, 코멘트, 마침말을 절대 포함하지 마십시오.
- 예: "먼저, 지금까지 논의해 온 문서에 대한 피드백을 드리겠습니다. 이후 요청하신 개요를 정리하고, 최종적으로 탈고된 최종 원고를 제공합니다." 같은 문장은 출력하지 마십시오.
- 출력은 저장될 원고 본문만 포함하십시오.""",
    used_when="outline/polish 노드가 LLM에 메시지를 보낼 때 전체 채팅 히스토리 뒤의 마지막 SystemMessage로 추가된다.",
    description="마크다운 산출물에 표, 거절, 인사말/코멘트/마침말이 섞이는 것을 막기 위한 최종 출력 제약.",
)

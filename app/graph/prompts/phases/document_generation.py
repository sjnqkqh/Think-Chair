from app.graph.prompts.types import PromptTemplate

DOCUMENT_GENERATION = PromptTemplate(
    id="phase.document_generation",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 초고와 대화를 바탕으로 최종 문서를 작성하십시오.

- 지금까지 대화를 통해 정해진 컨셉, 주제, 독자 수준, 범위, 근거를 모두 반영하십시오.
- 문서 본문만 작성하고, 대화체 응답이나 작성 과정 설명은 포함하지 마십시오.
- 완성된 문서로 바로 사용할 수 있도록 충분히 구체적이고 체계적으로 작성하십시오.""",
    used_when="user_action == 'generate_document'로 generate_document_from_conversation 노드가 호출될 때 사용된다. 결과는 save_new_paper 노드가 ManuscriptVersion(kind='document')로 저장한다.",
    description="충분한 대화 내용을 종합해 최종 문서를 생성하는 단계 프롬프트.",
)

DOCUMENT_FINAL_GUARD = PromptTemplate(
    id="phase.document_generation.final_guard",
    text="""# 최종 출력 규칙 (문서 생성 단계)

- 오직 완성된 문서 본문만 출력하십시오.
- Markdown 표와 비교표를 넣지 마십시오. 텍스트 표를 절대 넣지 마십시오. 비교나 정리는 제목·소제목·문단·목록으로 풀어쓰십시오.
- 인사말, 안내문, 코멘트, 마침말을 넣지 마십시오. 작성 과정 설명이나 '도움이 되었길 바랍니다' 같은 문구도 포함하지 마십시오.
- 본문 없이 요약만 제시하지 마십시오.""",
    used_when="generate_document_from_conversation_node에서 매 호출마다, 전체 채팅 히스토리 뒤의 마지막 SystemMessage로 추가된다.",
    description="문서 생성 단계에서 표, 인사말/코멘트/마침말, 본문 없는 요약 출력이 섞이는 것을 막기 위한 최종 출력 가드레일.",
)

DOCUMENT_STEP_BACK = PromptTemplate(
    id="phase.document_generation.step_back",
    text="""# 재생성 지시

방금 생성한 결과는 너무 짧습니다. 이전 대화에서 정한 내용과 근거를 빠뜨리지 말고, 완결된 문서 본문으로 더 충실하게 다시 작성하십시오.""",
    used_when="generate_document_from_conversation_node 재시도(document_generation_attempts >= 1) 시 마지막 SystemMessage 뒤에 추가된다.",
    description="짧은 문서 생성 결과를 재시도할 때 본문을 충실하게 확장하도록 지시한다.",
)

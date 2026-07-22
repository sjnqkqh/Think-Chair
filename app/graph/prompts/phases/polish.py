from app.graph.prompts.types import PromptTemplate

POLISH = PromptTemplate(
    id="phase.polish",
    text="""위에 주어지는 이 컨셉의 생성 기준을 반드시 따라, 지금까지의 초고와 대화를 바탕으로 탈고(polish)된 최종본을 작성하십시오.
- 문장을 다듬고, 중복되거나 불필요한 부분을 제거하십시오.
- 원고 전체의 구조와 흐름은 유지하십시오.
- 마크다운 형식.
- 기존에 초고 작성/탈고 요청이 완료된 적이 있어도 이와 상관없이 지난 대화내역을 바탕으로 완결성을 갖춘 원고를 생성한다.
- 출력은 원고 본문만 담는다. "다음은 최종본입니다", "검토해보시고 지적해주십시오" 같은 전후 인사말/코멘트를 절대 포함하지 않는다. 이 출력은 그대로 원고 파일로 저장된다.""",
    used_when="user_action == 'polish' 로 polish 노드가 호출될 때 사용된다. 결과는 make_new_paper 노드가 ManuscriptVersion(kind='polish')로 저장한다.",
    description="탈고 지시문. 구체적 구조/분량 기준은 concept의 generate.md가 담당한다.",
)

POLISH_FINAL_GUARD = PromptTemplate(
    id="phase.polish.final_guard",
    text="""# 최종 출력 규칙 (polish 단계)

이 메시지는 전체 채팅 히스토리 이후에 적용되는 최종 규칙입니다.
- 마크다운 본문에 텍스트 표를 절대 넣지 마십시오. 표 형태가 필요하면 반드시 리스트로 풀어서 표현하십시오.
- 지금까지의 대화 내용만을 바탕으로 완결된 원고 본문을 작성하십시오.
- 원고 본문 외의 '초안을 작성해볼까요?','지금까지 이야기한 내용을 바탕으로 정리하겠습니다.' "검토해보시고 지적해주십시오" 등 인사말, 안내문, 코멘트, 마침말을 절대 포함하지 마십시오.
- '작성되었습니다', '전체 N개 섹션으로 구성' 같은 작성 결과 요약/설명만 출력하는 것은 금지입니다. 반드시 원고 본문 자체를 출력하십시오.
- 출력은 저장될 원고 본문만 포함하십시오.""",
    used_when="polish_node에서 매 호출마다, 전체 채팅 히스토리 뒤의 마지막 SystemMessage로 추가된다.",
    description="polish 단계에서 표, 인사말/코멘트/마침말, 본문 없는 요약 출력이 섞이는 것을 막기 위한 최종 출력 가드레일.",
)

POLISH_STEP_BACK = PromptTemplate(
    id="phase.polish.step_back",
    text="""# 재작성 지시 (step-back)

직전 시도의 출력은 원고 본문이 비어 있거나, 본문 없이 작성 결과 요약/코멘트("작성되었습니다", "전체 N개 섹션으로 구성" 등)만 담고 있었습니다.
이는 잘못된 출력입니다. 이번에는 반드시 완결된 원고 본문 전체를 처음부터 끝까지 실제로 작성하십시오.
요약이나 설명이 아니라, 저장 가능한 원고 본문 그 자체를 출력해야 합니다.""",
    used_when="polish_node 재시도(polish_attempts >= 1) 시 마지막 SystemMessage 뒤에 추가된다.",
    description="본문 누락(요약만 출력) 버그로 재생성이 트리거됐을 때 완전한 본문 작성을 강제하는 교정 지시문.",
)

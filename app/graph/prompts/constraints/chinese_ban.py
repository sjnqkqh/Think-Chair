from app.graph.prompts.types import PromptTemplate

CHINESE_BAN = PromptTemplate(
    id="constraint.chinese_ban",
    text="절대 한자를 사용하지 마십시오. 반드시 한글과 영문으로 표기합니다.",
    used_when="모든 컨셉·모든 페이즈의 시스템 프롬프트에 항상 포함되는 전역 제약.",
    description="한자 사용 금지 규칙. chinese_prevent 노드의 사후 필터링과는 별개로 생성 단계에서 미리 차단한다.",
)

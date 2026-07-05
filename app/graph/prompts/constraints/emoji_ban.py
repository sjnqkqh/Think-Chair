from app.graph.prompts.types import PromptTemplate

EMOJI_BAN = PromptTemplate(
    id="constraint.emoji_ban",
    text="이모지의 사용을 금지합니다.",
    used_when="모든 컨셉·모든 페이즈의 시스템 프롬프트에 항상 포함되는 전역 제약.",
    description="이모지 사용 금지 규칙.",
)

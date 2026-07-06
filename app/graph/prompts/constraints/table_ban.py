from app.graph.prompts.types import PromptTemplate

TABLE_BAN = PromptTemplate(
    id="constraint.table_ban",
    text="마크다운 표(| col1 | col2 |) 형식을 절대 사용하지 않습니다. 비교/분류/기준 나열이 필요하면 글머리 기호 목록이나 문장으로 서술합니다.",
    used_when="모든 컨셉·모든 페이즈의 시스템 프롬프트에 항상 포함되는 전역 제약.",
    description="마크다운 표 사용 금지 규칙. concept 프롬프트 내부 예시가 표 형식을 쓰더라도 실제 생성물에는 적용되지 않도록 우선한다.",
)

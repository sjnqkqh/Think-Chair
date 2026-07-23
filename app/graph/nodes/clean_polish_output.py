import re

from app.logging import get_logger
from app.graph.state import GraphState

logger = get_logger(__name__)

_PARAGRAPH_SEPARATOR = re.compile(r"\n[ \t]*\n+")
_PREFACE_STARTS = ("작성되었습니다", "작성됐습니다", "작성 완료")
_PREFACE_DETAILS = ("전체 분량은", "섹션으로 구성되어", "수강생 수준")
_CLOSING_PATTERNS = (
    re.compile(r"검토해 ?보시고.*(?:수정|말씀)"),
    re.compile(r"수정이 필요.*(?:말씀|요청)"),
    re.compile(r"궁금한 점.*(?:말씀|질문)"),
    re.compile(r"도움이 되었"),
    re.compile(r"읽어주셔서"),
)


def _is_preface(paragraph: str) -> bool:
    normalized = paragraph.strip()
    if len(normalized) > 700:
        return False
    return normalized.startswith(_PREFACE_STARTS) or (
        "작성" in normalized
        and any(detail in normalized for detail in _PREFACE_DETAILS)
    )


def _is_closing(paragraph: str) -> bool:
    normalized = paragraph.strip()
    return len(normalized) <= 400 and any(
        pattern.search(normalized) for pattern in _CLOSING_PATTERNS
    )


def clean_polish_content(content: str) -> tuple[str, int, int]:
    """Remove standalone generation commentary around a polish manuscript.

    Only the first and last blank-line-delimited paragraphs are considered, so
    prose inside the manuscript is preserved unless it is an obvious footer.
    """
    if not content:
        return content, 0, 0

    cleaned = content.strip()
    prefix_removed_chars = 0
    suffix_removed_chars = 0

    first_separator = _PARAGRAPH_SEPARATOR.search(cleaned)
    if first_separator and _is_preface(cleaned[: first_separator.start()]):
        removed = cleaned[: first_separator.end()]
        prefix_removed_chars = len(removed)
        cleaned = cleaned[first_separator.end() :].lstrip()

    separators = list(_PARAGRAPH_SEPARATOR.finditer(cleaned))
    if separators:
        last_separator = separators[-1]
        if _is_closing(cleaned[last_separator.end() :]):
            removed = cleaned[last_separator.start() :]
            suffix_removed_chars = len(removed)
            cleaned = cleaned[: last_separator.start()].rstrip()

    return cleaned, prefix_removed_chars, suffix_removed_chars


def clean_polish_output_node(state: GraphState) -> dict:
    new_paper = state.get("new_paper")
    if not new_paper or new_paper.get("kind") != "polish":
        return {}

    content = new_paper.get("content") or ""
    cleaned, prefix_removed_chars, suffix_removed_chars = clean_polish_content(content)
    if not prefix_removed_chars and not suffix_removed_chars:
        return {}

    logger.info(
        "polish_output.meta_removed",
        prefix_removed_chars=prefix_removed_chars,
        suffix_removed_chars=suffix_removed_chars,
        content_bytes_before=len(content.encode("utf-8")),
        content_bytes_after=len(cleaned.encode("utf-8")),
        polish_attempts=state.get("polish_attempts", 0),
    )
    return {"new_paper": {**new_paper, "content": cleaned}}

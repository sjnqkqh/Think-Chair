import re

CHINESE_RE = re.compile(r"[一-鿿]")


def contains_chinese(text: str) -> bool:
    return bool(CHINESE_RE.search(text))


def sanitize_chinese(text: str, replacement: str = "") -> str:
    return CHINESE_RE.sub(replacement, text)

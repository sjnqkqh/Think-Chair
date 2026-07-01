import re

HANJA_RE = re.compile(r"[一-鿿]")


def contains_hanja(text: str) -> bool:
    return bool(HANJA_RE.search(text))


def sanitize_hanja(text: str, replacement: str = "") -> str:
    return HANJA_RE.sub(replacement, text)

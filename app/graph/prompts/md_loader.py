def extract_section(markdown: str, heading: str) -> str:
    lines = markdown.splitlines()
    target = f"## {heading}"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == target:
            start = i + 1
            break
    if start is None:
        return ""

    end = start
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1

    return "\n".join(lines[start:end]).strip()

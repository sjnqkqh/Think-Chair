import re


def strip_code_fence(raw_output: str) -> str:
    text = raw_output.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    return match.group(1) if match else text

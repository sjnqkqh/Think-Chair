from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    text: str
    used_when: str
    description: str

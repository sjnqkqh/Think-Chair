from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

UserAction = Literal[
    "say", "inspect", "feedback", "outline", "draft", "polish", "finalize"
]


class PendingVersion(TypedDict, total=False):
    kind: Literal["outline", "draft", "polish"]
    content: str
    storage_key: str
    version_id: str
    revision: int


class DraftsmithState(TypedDict):
    manuscript_id: str
    concept: str
    topic: str
    audience_level: str | None
    user_action: UserAction | None
    messages: Annotated[list[BaseMessage], add_messages]
    pending_version: PendingVersion | None

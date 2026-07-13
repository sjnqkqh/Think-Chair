from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

UserAction = Literal["opening", "say", "feedback", "outline", "polish", "finalize"]


class NewPaper(TypedDict, total=False):
    kind: Literal["outline", "polish"]
    content: str
    storage_key: str
    version_id: str
    revision: int


class GraphState(TypedDict):
    manuscript_id: str
    concept: str
    topic: str
    user_nickname: str | None
    audience_level: str | None
    user_action: UserAction | None
    current_message_id: str | None
    messages: Annotated[list[BaseMessage], add_messages]
    new_paper: NewPaper | None

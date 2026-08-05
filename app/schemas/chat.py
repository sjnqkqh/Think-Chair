import datetime

from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    phase: str | None = None
    sequence: int
    created_at: datetime.datetime

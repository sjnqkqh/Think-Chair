from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    question: str = Field(..., description="LLM에 질문할 내용")
    top_k: int = Field(5, description="Chroma DB에서 검색할 관련 문서 개수")
    session_id: str = Field(..., description="세션 구분을 위한 UUID 문자열")

class QueryResponse(BaseModel):
    answer: str = Field(..., description="LLM이 생성한 한국어 답변")
    contexts: list[str] = Field(..., description="참조한 원본 문맥 청크 리스트")
    metadatas: list[dict] = Field(..., description="참조한 문맥의 메타데이터")

class IndexResponse(BaseModel):
    status: str
    indexed_count: int

from pydantic import BaseModel, Field
from typing import List, Dict, Any

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

class UploadResponse(BaseModel):
    status: str
    filename: str
    strategies_applied: List[str]
    chunks_count: Dict[str, int]

class EvalRequest(BaseModel):
    question: str = Field(..., description="테스트 질문")
    ground_truth: str = Field(..., description="정답 가이드라인 (Ground Truth)")
    strategies: List[Dict[str, Any]] = Field(..., description="비교 평가할 청킹 전략 리스트")
    top_k: int = Field(5, description="각 전략 검색 시 조회할 청크 수")
    use_ragas: bool = Field(False, description="Ragas 라이브러리를 사용한 정밀 평가 여부")


class StrategyEvalResult(BaseModel):
    strategy: str = Field(..., description="청킹 전략명")
    collection_name: str = Field(..., description="Chroma 컬렉션명")
    answer: str = Field(..., description="생성된 답변")
    contexts: List[str] = Field(..., description="검색된 맥락")
    scores: Dict[str, Any] = Field(..., description="LLM Judge 점수 및 사유 (faithfulness, relevance, precision 등)")

class EvalResponse(BaseModel):
    question: str
    ground_truth: str
    results: List[StrategyEvalResult]


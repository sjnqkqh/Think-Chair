from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class QueryRequest(BaseModel):
    question: str = Field(..., description="LLM에 질문할 내용")
    top_k: int = Field(5, description="Chroma DB에서 검색할 관련 문서 개수")
    session_id: str = Field(..., description="세션 구분을 위한 UUID 문자열")


class QueryResponse(BaseModel):
    answer: str = Field(..., description="LLM이 생성한 한국어 답변")
    contexts: list[str] = Field(..., description="참조한 원본 문맥 청크 리스트")
    metadatas: list[dict] = Field(..., description="참조한 문맥의 메타데이터")


class UploadResponse(BaseModel):
    status: str
    filename: str
    history_id: int
    message: str


class UploadStatusResponse(BaseModel):
    id: int
    filename: str
    status: str
    error_message: Optional[str] = None
    strategies_applied: List[str]
    chunks_count: Dict[str, int]
    created_at: datetime


class EvaluationRequest(BaseModel):
    question: str = Field(..., description="테스트 질문")
    ground_truth: str = Field(..., description="정답 가이드라인 (Ground Truth)")
    strategies: List[Dict[str, Any]] = Field(
        ..., description="비교 평가할 청킹 전략 리스트"
    )
    top_k: int = Field(5, description="각 전략 검색 시 조회할 청크 수")
    use_ragas: bool = Field(
        False, description="Ragas 라이브러리를 사용한 정밀 평가 여부"
    )


class StrategyEvaluationResult(BaseModel):
    strategy: str = Field(..., description="청킹 전략명")
    collection_name: str = Field(..., description="Chroma 컬렉션명")
    answer: str = Field(..., description="생성된 답변")
    contexts: List[str] = Field(..., description="검색된 맥락")
    scores: Dict[str, Any] = Field(
        ...,
        description="LLM Judge 점수 및 사유 (faithfulness, relevance, precision 등)",
    )


class EvaluationResponse(BaseModel):
    question: str
    ground_truth: str
    results: List[StrategyEvaluationResult]


class QAPair(BaseModel):
    id: Optional[int] = Field(None, description="QA 쌍 식별자")
    type: Optional[str] = Field(None, description="분류 (A/B 등)")
    section: Optional[str] = Field(None, description="출처 섹션")
    retrieval_hint: Optional[str] = Field(None, description="검색 힌트")
    question: str = Field(..., description="테스트 질문")
    answer: str = Field(..., description="정답 가이드라인 (Ground Truth)")


class EvaluationJSONRequest(BaseModel):
    qa_pairs: List[QAPair] = Field(..., description="평가할 QA 쌍 목록")
    strategies: List[Dict[str, Any]] = Field(
        ..., description="비교 평가할 청킹 전략 리스트"
    )
    top_k: int = Field(5, description="각 전략 검색 시 조회할 청크 수")
    use_ragas: bool = Field(
        False, description="Ragas 라이브러리를 사용한 정밀 평가 여부"
    )


class StrategySummary(BaseModel):
    strategy: str = Field(..., description="청킹 전략명")
    faithfulness_avg: float = Field(..., description="평균 충실성")
    relevance_avg: float = Field(..., description="평균 답변 연관성")
    precision_avg: float = Field(..., description="평균 컨텍스트 정확성")
    recall_avg: float = Field(..., description="평균 컨텍스트 재현율")
    completeness_avg: float = Field(..., description="평균 답변 완결성")
    noise_ratio_avg: float = Field(..., description="평균 노이즈 비율")
    coverage_rate_avg: float = Field(..., description="평균 커버리지 비율")
    gt_match_rate_avg: float = Field(..., description="평균 GT 매치율")
    avg_chunk_length_avg: float = Field(..., description="평균 청크 길이")


class QAPairEvaluationResult(BaseModel):
    id: Optional[int] = Field(None, description="QA 쌍 ID")
    question: str = Field(..., description="테스트 질문")
    ground_truth: str = Field(..., description="정답 가이드라인 (Ground Truth)")
    results: List[StrategyEvaluationResult] = Field(..., description="각 전략별 평가 결과")


class EvaluationJSONResponse(BaseModel):
    summaries: List[StrategySummary] = Field(..., description="각 전략별 평균 점수 요약")
    evaluations: List[QAPairEvaluationResult] = Field(..., description="각 문항별 평가 결과 목록")


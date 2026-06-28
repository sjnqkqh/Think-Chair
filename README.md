# RAG Integrated AI

PDF/텍스트 문서를 업로드하면 다중 청킹 전략으로 벡터 DB에 색인하고, 하이브리드 검색(BM25 + 벡터)으로 질의에 답변하는 RAG 챗봇 서버입니다. LLM Judge 또는 RAGAS 프레임워크로 청킹 전략별 성능을 정량 비교할 수 있습니다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| 서버 | FastAPI, SQLAlchemy (SQLite) |
| LLM | Google Gemini (생성), DeepSeek (Judge) |
| 벡터 DB | ChromaDB |
| 검색 | BM25 + Vector Ensemble (Kiwi 한국어 형태소 분석) |
| 평가 | RAGAS, Custom LLM Judge |
| 추적 | LangSmith |

## 환경 설정

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
GEMINI_API_KEY=your_gemini_api_key

# 선택 — 미설정 시 Gemini로 대체
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 선택 — LangSmith 추적
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=your_project_name

# 선택 — ChromaDB 원격 모드 (기본: local)
CHROMA_MODE=local
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

## 실행

```bash
# 의존성 설치 (uv 권장)
uv sync

# 서버 실행
uvicorn app.main:app --reload

# 또는 Docker
docker compose up
```

서버 기동 후 `http://localhost:8000` 에서 채팅 UI에 접근할 수 있습니다.  
API 문서: `http://localhost:8000/docs`

## API

### 문서 업로드

```
POST /upload
```

청킹 전략을 JSON 배열로 지정하면 각 전략별로 독립된 ChromaDB 컬렉션에 저장됩니다.

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@document.pdf" \
  -F 'strategies=[
    {"name": "recursive", "chunk_size": 500, "chunk_overlap": 50},
    {"name": "recursive", "chunk_size": 1000, "chunk_overlap": 100},
    {"name": "markdown_header"}
  ]'
```

업로드는 백그라운드로 처리되며, 상태는 아래 엔드포인트로 확인합니다.

```
GET /upload/status/{history_id}
```

### 질의

```
POST /query          # 단일 응답
POST /query/stream   # SSE 스트리밍
```

```json
{
  "question": "질문 내용",
  "session_id": "user-session-id",
  "top_k": 5
}
```

### 평가

```
POST /evaluate
```

단일 질문과 정답(ground truth)을 입력하면 등록된 전략별로 검색·생성·평가를 수행하고 결과를 반환합니다.

```json
{
  "question": "질문",
  "ground_truth": "정답 가이드라인",
  "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
  "top_k": 5,
  "use_ragas": false
}
```

```
POST /evaluate/json-dataset   # JSON 데이터셋 일괄 평가
GET  /evaluate/history        # 평가 이력 조회
```

## 청킹 전략

| 전략 | 파라미터 | 설명 |
|------|----------|------|
| `recursive` | `chunk_size`, `chunk_overlap` | LangChain RecursiveCharacterTextSplitter |
| `character` | `separator`, `chunk_size`, `chunk_overlap` | 구분자 기반 분할 |
| `markdown_header` | — | `#`, `##`, `###` 헤더 단위 분할 |

## 평가 지표

**LLM Judge** (DeepSeek, 1~5점 척도)

| 지표 | 설명 |
|------|------|
| Faithfulness | 생성 답변의 사실성 (환각 검출) |
| Answer Relevance | 질문 대비 답변 연관도 |
| Context Precision | 검색 청크의 노이즈 비율 |
| Context Recall | Ground Truth 대비 검색 완전성 |
| Answer Completeness | Ground Truth 대비 답변 완결성 |

**RAGAS** (`use_ragas: true` 시 활성화)

동일 지표를 RAGAS 프레임워크의 `single_turn_ascore`로 측정합니다 (0~1 → 1~5점 변환).

**통계 지표** (항상 계산)

| 지표 | 설명 |
|------|------|
| `coverage_rate` | Ground Truth 토큰 대비 컨텍스트 포함률 |
| `gt_match_rate` | Ground Truth 토큰 대비 답변 일치율 |
| `avg_chunk_length` | 청크 평균 길이 |

## 테스트

```bash
pytest
```

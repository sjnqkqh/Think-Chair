# Agentic RAG 공용 평가 기준 추가

## PR 개요

- 이후 Agentic RAG 기능을 기존 방식과 같은 입력으로 비교하기 위한 공용 평가 기준 추가
- 스키마 버전이 고정된 JSONL 사례 8개로 한국어·영어·교차 언어·혼합 언어 조건 정의
- detector precision/recall과 source·chunk Recall@k를 계산하는 결정적 평가 runner 추가
- 잘못된 인용, 다른 사용자의 자료 노출, 필요한 답변 보류 누락을 코드로 실패 처리
- baseline과 candidate 결과를 같은 machine-readable JSON 구조로 출력

## 주요 변경 파일

- `tests/evaluation/agentic_rag_cases.jsonl`: detector·retrieval·citation·tenant 격리·자료 충돌 평가 사례 정의
- `tests/evaluation/run_agentic_rag_eval.py`: 평가 데이터와 예측 결과 로드, metric 계산, 안전성 검사, JSON 요약 출력
- `tests/unit/evaluation/test_agentic_rag_eval.py`: 스키마 고정, metric 계산, 안전성 실패, baseline/candidate 출력 계약 검증

## 비고

- `uv run pytest -q`: 180개 통과
- `uv run pytest tests/unit/evaluation/test_agentic_rag_eval.py -q`: 7개 통과
- `uv run ruff check app tests`: 통과
- 외부 평가 서비스, 신규 의존성, 환경 변수, DB migration, runtime 연결 없음
- 기존 환경의 `StarletteDeprecationWarning` 1건 유지

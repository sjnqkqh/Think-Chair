# Agentic RAG 세로 MVP 구현 계획

- 작성일: 2026-08-03
- 근거 설계: `docs/specs/2026-08-03-agentic-rag-vertical-mvp-design.md`
- 목표: 채팅에서 비동기 웹 조사를 쓰고, job 완료 시 baseline/grounded 쌍과 LLM 비교를 DB에 남긴다.

## 완료 기준

설계 §7과 동일. 승률 게이트 없음.

## 작업 순서

### 1. 근거 검색

- `app/research/`에 EvidenceRequest/Item/Context 계약 + `retrieve_evidence`
- Chroma public/private 검색, private tenant filter
- 최소 sufficiency (결과 유무·개수 기반)
- 단위 테스트: 기대 chunk 적중, cross-user 0건

### 2. 인용 응답

- `generate_grounded_response` + citation 검증·1회 재생성·fallback
- baseline 생성은 evaluation 생성 프롬프트/런타임 어댑터 재사용
- 단위 테스트: 유령 citation 거부, URL 본문 포함

### 3. 조사 필요 판단 (최소)

- `detect_evidence_need` — 휴리스틱 또는 짧은 LLM, `UserAction` 미혼입
- 단위 테스트: 수치 주장 vs 가벼운 맞장구

### 4. Research job 실행기

- 검색 → 부족 시 web search/fetch/index → 재검색
- 완료 후 baseline/grounded 생성·규칙 검사·pairwise → DB 저장
- 비교 실패와 job completed 분리
- 단위/통합 테스트: message당 job 1개, 상태 전이

### 5. API

- `POST/GET(/cancel) /api/research/jobs...`
- 채팅 SSE `research_required`
- 얇은 엔드포인트, 로직은 서비스

### 6. 채팅·UI 연결

- 다음 턴 근거 주입
- 폴링 + `근거 준비됨` 표시
- 답 자동 수정·자동 후속 메시지 없음

### 7. 정리

- `uv run ruff check` / 관련 pytest
- 회귀: 비조사 채팅·문서 생성

## 문서 PR 대비

PR 03~06 계약을 최소로 한 줄에 연결. corpus 확장·게이트·detector 고도화는 제외.

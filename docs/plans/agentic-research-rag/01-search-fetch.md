# 작업 1 — `search_web`과 `fetch_page`

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 목적

graph와 vector store 없이 독립 검증 가능한 검색·원문 수집 도구를 만든다.

## 작업 선행 조건

- 없음

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 01 — 웹 검색과 원문 수집](prs/01-search-fetch.md)

## 계약

### `search_web(SearchRequest) -> SearchResponse`

`SearchRequest`

- `query: str`
- `max_results: int`
- `allowed_domains: list[str] | None`

`SearchResponse`

- `results: list[SearchHit]`
  - `url`, `title`, `snippet`
  - `publisher`, `published_at`, `provider_rank`
- `error_code: str | None`
- `retryable: bool`

### `fetch_page(FetchRequest) -> FetchResponse`

`FetchRequest`

- `url: str`

`FetchResponse`

- `source: FetchedSource | None`
  - `requested_url`, `canonical_url`, `title`, `publisher`, `media_type`
  - `text`, `fetched_at`, `published_at`
  - `content_hash`, `source_key`
- `error_code: str | None`
- `retryable: bool`

timeout, 429, 5xx는 제한된 재시도 후 구조화된 실패로 반환한다. 개별 페이지 실패는 전체 research job을 중단하지 않는다.

## 구현 범위

- provider 결과를 공통 검색 결과로 정규화
- caller는 정규화한 검색 결과 URL이 이미 저장됐는지 먼저 확인하고, 처음 보는 URL에만 `fetch_page`를 호출
- HTML 문서만 수집
- canonical URL, 본문, 날짜, content hash 추출
- LangChain tool schema로 노출
- 원문을 instruction이 아닌 untrusted data로 취급

## 예상 파일

- `app/research/web_search.py`
- `app/research/page_fetcher.py`
- `app/research/agent_tools.py`
- `app/core/config.py`
- `tests/unit/research/test_search_web.py`
- `tests/unit/research/test_fetch_page.py`
- `tests/unit/research/test_agent_tools.py`

## 보안 조건

- HTTP(S)만 허용
- 최초 URL과 모든 redirect에서 loopback, private, link-local, metadata IP 차단
- TLS 검증
- timeout, redirect 수, 응답 byte, concurrency, content-type 제한
- script/style 제거
- API key와 원문 전체를 로그에 남기지 않음

## 완료 조건

- fake provider/transport contract test 통과
- timeout, 429/5xx, redirect, oversized body, unsupported media type 검증
- SSRF 차단 테스트 통과
- 동일 입력의 정규화 결과가 결정적임
- graph와 app runtime에는 연결하지 않음

## 제거 조건

두 tool과 관련 설정을 삭제해도 기존 runtime 동작이 변하지 않아야 한다.

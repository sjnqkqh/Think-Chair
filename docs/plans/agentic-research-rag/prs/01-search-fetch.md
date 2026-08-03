# PR 01 — 웹 검색과 원문 수집

[PR 목록](README.md) · [기능 계획](../01-search-fetch.md)

## 목표

검색 결과를 공통 형식으로 정리하고, 그 URL에서 안전하게 HTML 원문과 출처
정보를 가져오는 두 도구를 함께 만든다.

## 선행 조건

- D1에서 검색 API, 비동기 HTTP client, HTML extractor 선택
- D9 source admission과 SSRF 방어 기준 확정

## 포함

- `SearchRequest`, `SearchHit`, `SearchResponse`
- `FetchRequest`, `FetchedSource`, `FetchResponse`
- 검색 provider client와 결과 정규화
- timeout, 429, 5xx의 제한 재시도와 안전한 오류 코드
- requested/canonical URL, 본문, 날짜, content hash, source key 추출
- 최초 URL과 모든 redirect의 SSRF 검증
- 응답 크기·시간·redirect·content-type 제한
- script/style/hidden element와 반복 안내 문구 제거
- 안전검사를 통과하지 못한 자료 거부
- fake provider와 transport를 사용한 contract test

## 제외

- LangGraph 연결
- 원문 저장과 임베딩
- PDF, OCR, JavaScript 렌더링과 브라우저 자동화
- provider registry와 failover routing

## 예상 변경

- `app/research/web_search.py`
- `app/research/page_fetcher.py`
- `app/research/agent_tools.py`
- `app/core/config.py`
- `tests/unit/research/test_search_web.py`
- `tests/unit/research/test_fetch_page.py`
- `tests/unit/research/test_agent_tools.py`

## 완료 조건

- 검색의 정상·빈 결과·timeout·429·5xx contract test 통과
- `max_results`와 `allowed_domains` 강제
- 정상 HTML과 개별 페이지 실패 처리 검증
- loopback, private, link-local, metadata IP와 redirect 우회 차단
- oversized body와 지원하지 않는 media type 차단
- 동일 본문이 동일한 content hash를 생성
- API key와 전체 원문을 로그에 남기지 않음
- 두 도구를 제거해도 기존 runtime에 영향 없음

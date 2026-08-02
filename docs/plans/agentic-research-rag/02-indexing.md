# 작업 2 — 청킹·임베딩·인덱싱

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 목적

공개 웹 원문은 프로젝트 전역에서 재사용하고, 비공개 자료는 tenant에 격리한 corpus로 저장한다.

## 작업 선행 조건

- 작업 1의 `FetchedSource`

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 02 — 자료 저장·청킹·임베딩](prs/02-indexing.md)

## 계약

### `index_sources(IndexRequest) -> IndexResult`

`IndexRequest`

- `research_job_id: UUID`
- `user_id: UUID`
- `manuscript_id: UUID`
- `sources: list[FetchedSource]`

Aux input:

- `source_admission_policy` — 신뢰된 서버 정책이 `public | private | reject`를 결정
- `embedding_model`, `embedding_version`, `embedding_dimension`
- `chunk_schema_version`
- `embedding_client`, `vector_store`, DB·raw storage

corpus scope와 embedding 설정은 caller가 선택하지 않고 composition root가 주입한 정책이 결정한다.

`IndexResult`

- `indexed_source_ids: list[UUID]`
- `chunk_count: int`
- `skipped_source_keys: list[str]`
- `error_codes: list[str]`
- `status: Literal["completed", "partial", "failed"]`

SQL, file storage, vector store를 하나의 transaction으로 가정하지 않는다. source 상태를 `pending → indexed | failed`로 기록하고 idempotent retry와 실패 산출물 정리로 복구한다.

## 내부 단계

1. job ownership과 manuscript soft-delete 재확인
2. requested/canonical URL로 기존 source 중복 확인
3. 새 source의 metadata, URL 별칭과 원문 storage key 저장
4. 문서 구조와 tokenizer limit에 따른 결정적 청킹
5. embedding 생성
6. vector upsert
7. job/manuscript와 source association 저장
8. source 상태 확정 또는 실패 산출물 정리

청킹, embedding, persistence는 하나의 `IndexResult`를 만드는 단일 작업으로 유지한다.

이미 저장된 requested/canonical URL은 이 작업에 전달하지 않는 것이 기본 계약이다. redirect 이후 기존 canonical URL과 같다는 사실을 처음 알게 된 경우에는 URL 별칭만 기존 `ResearchSource`에 연결하고 새 원문·chunk·vector를 만들지 않는다. 동일 URL의 변경 확인과 원문 갱신은 수행하지 않는다.

## 다국어 저장 정책

- 원문을 번역하지 않고 Unicode NFC로 정규화한다.
- 제목·문단·목록·표·코드블록 구조를 먼저 보존하고 tokenizer 기준 최대 크기를 적용한다.
- 한국어·영어가 섞인 문단을 언어 때문에 분리하지 않는다.
- `language: ko | en | mixed | und`를 저장하되 검색 격리 조건으로 사용하지 않는다.
- 하나의 collection에는 같은 embedding model/version/dimension과 chunk schema version만 저장한다.
- embedding 또는 chunk schema가 바뀌면 새 collection에 reindex한다.

검색 인덱스를 다시 만들 때는 저장된 원문을 사용하며 URL을 다시 수집하지 않는다.

## 최소 영속 데이터

- `ResearchJob`: job/manuscript/message/user ID, 상태, timestamps, terminal error
- job 상태: `queued | running | completed | partial | failed | cancelled`
- `ResearchSource`: source ID, `public | private` scope, canonical URL, title, publisher, content hash와 storage key, published/fetched 시각, language, 상태
- 평가 corpus source는 `source_type`, `claim_relevance`, `freshness`, `is_primary_source`, `independence_group`, `expected_treatment`를 보존한다. 이 값은 저장 단계에서 삭제하지 않으며 질문별 출처 선택 평가에 사용한다.
- `ResearchSourceUrl`: 정규화된 requested/canonical URL, source ID, `public | private` scope, private owner ID, canonical 여부
- `ResearchJobSource`: job/manuscript와 source의 tenant-private association
- source 상태: `pending | indexed | failed | tombstoned`
- public vector metadata: chunk/source ID, content hash, language, section/offset, embedding/chunk schema version
- private vector metadata: public metadata + owner user/manuscript ID
- `message_id` unique constraint: 충돌하면 기존 job 반환

## 예상 파일

- `app/models/research.py`
- `app/repositories/research_repo.py`
- `app/research/indexing.py`
- `tests/unit/research/test_indexing.py`

## 완료 조건

- 저장된 requested/canonical URL은 fetch·chunk·embedding 0회
- redirect 이후 기존 canonical URL로 확인되면 URL 별칭만 추가하고 중복 chunk 0건
- public URL은 전역에서 중복되지 않고 private URL은 owner별로만 중복되지 않음
- 모든 chunk의 `source_id`가 canonical URL을 가진 `ResearchSource` 하나로 연결됨
- 중간 실패 후 retry가 중복 없이 완료되거나 실패 산출물을 정리
- public source는 사용자별 vector 복제 없이 재사용
- private source는 다른 user/manuscript retrieval 후보에 들어오지 않음
- embedding version 변경 감지
- `ko`, `en`, `mixed` fixture가 같은 collection에 저장됨
- partial/failed 상태와 safe error code 저장
- seeded HTML fixture 테스트 통과
- 평가 corpus의 source-quality metadata가 chunk와 함께 보존되고 재인덱싱 후에도 변하지 않음

## 제거 조건

research table과 corpus storage/index를 삭제해도 기존 chat/manuscript 데이터가 유지되어야 한다.

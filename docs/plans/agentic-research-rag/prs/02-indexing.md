# PR 02 — 자료 저장·청킹·임베딩

[PR 목록](README.md) · [기능 계획](../02-indexing.md)

## 목표

`FetchedSource`를 일정한 규칙으로 나누고, 이후 조사에서 다시 사용할 수 있는
검색 자료로 저장한다.

## 선행 조건

- PR 00
- PR 01
- D2: embedding model과 vector store
- D3: public/global과 private/tenant corpus 경계, 현재 원문 보존 기간, reindex 정책
- D7: multilingual retrieval subset
- D9: corpus admission과 삭제 전파

## 포함

- research job/source 영속 모델과 repository
- requested/canonical URL 중복 제거와 URL 별칭 저장
- 문서 구조와 tokenizer 제한을 고려한 chunk ordinal/offset, language metadata
- source type·관련성·최신성·원자료성·독립 출처 그룹·기대 처리의 source-quality metadata 보존
- embedding과 vector upsert
- public source 전역 dedupe와 tenant-private job/source association
- 안전검사를 통과한 public source의 공용 검색 노출
- 기존 canonical URL로 확인된 redirect의 URL 별칭 연결
- `pending → indexed | failed` 상태 전이
- 중복 없는 재시도와 실패 산출물 정리

## 제외

- similarity retrieval
- grounded response
- 여러 embedding/vector provider를 위한 별도 추상화

## 예상 변경

- `app/models/research.py`
- `app/repositories/research_repo.py`
- `app/research/indexing.py`
- `tests/unit/research/test_indexing.py`

## 완료 조건

- 같은 source를 다시 처리해도 중복 chunk 0건
- 저장 단계별 실패 후 일관된 retry
- embedding model/version 불일치 감지
- D3에서 정한 public/private 접근 경계 테스트
- public URL은 전역에서, private URL은 owner 범위 안에서만 중복 제거
- 모든 chunk가 canonical URL을 가진 source 하나로 연결
- 이미 저장된 requested/canonical URL에서는 새 원문·chunk·vector 0건
- `ko`, `en`, `mixed` 원문을 번역 없이 같은 multilingual collection에 저장
- source-quality metadata가 인덱싱·재인덱싱 과정에서 보존되고 retrieval 단계에 전달됨

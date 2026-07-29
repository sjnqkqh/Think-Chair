# Chroma·임베딩 구성 설계

## 목적

Agentic RAG가 수집한 웹 자료를 프로젝트 전역에서 다시 사용할 수 있도록
Chroma에 저장한다. 초기 임베딩 모델은 OpenAI `text-embedding-3-small`로
고정하고, 아직 필요하지 않은 다중 공급자 체계는 만들지 않는다.

## 결정 사항

- 임베딩 모델: `text-embedding-3-small`
- 벡터 차원: `1536`
- 벡터 저장소: 로컬 영속 Chroma
- 저장 경로: `settings.DATA_ROOT / "chroma_data"`
- 컬렉션 이름: `research_sources_v1`
- LangChain 경계: `langchain_core.embeddings.Embeddings`
- Chroma 연동: `langchain-chroma`
- OpenAI 연동: 이미 설치된 `langchain-openai`

Docker에서는 기존 named volume이 `/data`를 영속화하므로 Chroma 데이터는
`/data/chroma_data`에 저장된다. 로컬에서는 `DATA_ROOT` 아래에 저장하며,
기존 `.gitignore`의 `**/chroma_data/` 규칙을 그대로 사용한다.

## 구성 경계

애플리케이션 조립 지점에서 `OpenAIEmbeddings`와 Chroma 인스턴스를 각각
한 번 생성한다. 색인·검색 코드는 구체적인 OpenAI 클래스가 아니라
LangChain의 `Embeddings` 계약을 전달받는다.

설정값은 다음으로 제한한다.

- `OPENAI_API_KEY`
- `EMBEDDING_MODEL` — 기본값 `text-embedding-3-small`
- `EMBEDDING_DIMENSION` — 기본값 `1536`

Chroma 경로는 `DATA_ROOT`에서 계산하고 컬렉션 이름은 코드 상수로 둔다.
공급자 레지스트리, 팩토리 계층, 자동 모델 선택은 추가하지 않는다.

## 저장 흐름

아래 흐름은 이후 인덱싱 PR이 이 구성을 사용하는 방식이다. 이번 구성
작업에서는 임베딩과 Chroma 인스턴스를 만드는 경계까지만 구현한다.

1. 저장된 URL인지 먼저 확인한다.
2. 새 원문만 결정적으로 청킹한다.
3. 청크 목록을 문서 입력으로 임베딩한다.
4. 동일한 청크 ID로 Chroma에 upsert한다.
5. 색인 성공 상태를 영속 데이터에 기록한다.

각 벡터에는 최소한 다음 메타데이터를 저장한다.

- `chunk_id`
- `source_id`
- `canonical_url`
- `language`
- `scope`
- `owner_user_id`와 `owner_manuscript_id` — 비공개 자료에만 저장
- `embedding_model`
- `embedding_dimension`
- `chunk_schema_version`

공개 자료는 전역에서 재사용한다. 비공개 자료는 검색 전에 tenant metadata
filter를 반드시 적용하며, 필터가 없는 비공개 검색 경로는 제공하지 않는다.

## 모델 변경과 재색인

서로 다른 임베딩 모델이 만든 벡터는 차원이 같아도 섞지 않는다.
모델이나 차원, 청킹 규칙이 바뀌면 새 컬렉션을 만들고 저장된 원문으로
전체 벡터를 다시 생성한다. 이 과정에서 원본 URL을 다시 수집하지 않는다.

다른 모델을 실험할 때는 별도 임시 컬렉션을 만들고 동일한 평가 질의로
검색 품질을 비교한다. 실제 두 번째 공급자가 필요해질 때 조립 지점의
구현체와 필요한 의존성만 추가한다.

## 실패 처리

- API 키 검증과 Chroma 초기화는 연구 기능이 실제로 호출될 때 수행한다.
- 따라서 기존 채팅 기능은 임베딩 설정이 없어도 시작할 수 있다.
- 임베딩 호출 실패, `partial` 상태와 동일 청크 재시도는 이후 인덱싱 PR이
  기존 `IndexResult` 계약에 따라 처리한다.

## 검증

실제 OpenAI API를 호출하지 않고 결정적인 가짜 `Embeddings` 구현을 사용한다.

- 임시 디렉터리에 Chroma를 만들고 다시 열어도 벡터가 유지되는지 확인한다.
- 컬렉션에 모델명과 차원 정보가 남는지 확인한다.
- 다른 모델 또는 차원으로 기존 컬렉션을 열지 못하게 하는지 확인한다.

청크 재시도, 원본 URL 메타데이터와 tenant filter는 실제 색인·검색 구현이
추가되는 PR에서 검증한다.

## 제외 범위

- 여러 임베딩 공급자를 자동 선택하는 기능
- 모델 변경 시 자동 데이터 이전
- Chroma 서버 분리와 수평 확장
- reranker와 hybrid search
- 실제 OpenAI 호출을 사용하는 자동 테스트

자료량이나 동시 쓰기가 단일 프로세스 Chroma의 한계를 실제로 넘을 때만
외부 벡터 데이터베이스를 검토한다.

## 완료 조건

- 기존 미사용 `chroma_db/`가 제거된다.
- `text-embedding-3-small`, 1536차원으로 새 Chroma 구성이 만들어진다.
- 데이터가 `DATA_ROOT/chroma_data`에 영속되도록 구성된다.
- 이후 색인·검색 코드가 사용할 LangChain `Embeddings` 경계가 제공된다.
- 영속성과 컬렉션 모델 호환성 검증이 통과한다.
- 다중 공급자용 자체 추상화가 추가되지 않는다.

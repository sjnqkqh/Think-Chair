# 운영 신뢰성·의존성 검토

## 결론

- 현재 규모에서는 Redis/Celery 같은 외부 큐보다 **기존 SQLite에 작업 상태를 남기고 실행은 프로세스 내부에서 유지**하는 방식이 적절하다.
- 메시지 유실의 확정된 문제는 실제 삭제보다 **화면과 감사 로그가 서로 다른 저장소를 기준으로 삼는 것**이다. 정확한 개별 장애 원인은 식별자·발생 시각·로그가 없어 아직 확정할 수 없다.
- 이번 브랜치에는 영향이 좁은 SSE 오류 비노출, 미사용 의존성 제거, Ruff 수정만 포함한다. 작업 상태 영속화와 메시지 기준 저장소 변경은 검토 후 별도 PR이 안전하다.

## JWT 시크릿 기준

현재 알고리즘은 HS256이다(`app/core/security.py:8-30`). [RFC 7518 §3.2](https://www.rfc-editor.org/rfc/rfc7518.html#section-3.2)는 HS256에 256비트 이상의 키를 요구한다.

- 최소·권장: 암호학적으로 안전한 난수 **32바이트(256비트)**
- 문자열 표현: hex 64자 또는 base64url 약 43자
- 생성 예: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- 사람이 만든 문장·UUID 한 개는 사용하지 않고 배포 Secret으로만 주입

현재 기본값 `dev-secret-change-me`는 운영에 부적합하다(`app/core/config.py:18`). 다음 보안 PR에서 운영 시작 시 기본값/32바이트 미만을 거부하는 검증이 필요하다.

## 백그라운드 작업 처리

현재 문서 생성은 `asyncio.create_task()`로만 실행되고 상태·재시작 복구가 없다(`app/services/background_tasks.py:10-22`, `app/services/chat_service.py:81-105`). 다만 SQLite와 체크포인트는 `/data` 볼륨에 보존된다(`app/main.py:39-42`, `docker-compose.yml:11-20`).

권장하는 작은 프로젝트용 단계:

1. 요청 승인 전에 기존 `Manuscript.status`를 `generating_document`로 커밋
2. 성공 시 `drafted`, 실패 시 명시적 실패 상태와 짧은 오류 코드 저장
3. 폴링 응답에서 `pending/running/succeeded/failed` 반환
4. 시작 시 남아 있는 `running` 작업을 실패 처리하거나 한 번만 재시도

별도 작업 큐는 다중 인스턴스, 높은 작업량, 엄격한 재시도·우선순위, 웹 프로세스와의 자원 격리가 실제로 필요할 때 도입한다. 현재는 같은 SQLite로 충분하며 “원격 저장소”가 필수는 아니다.

## 메시지 유실 진단

확인된 구조:

- 새로고침은 `ChatMessage`가 아니라 LangGraph 체크포인트만 읽는다(`app/pages/workspace_pages.py:81-100`, `app/graph/conversation_state.py:8-11`).
- `ChatMessage`는 별도로 즉시 커밋되며(`app/repositories/chat_repo.py:17-32`), 저장 실패는 rollback 후 삼켜진다(`app/services/chat_service.py:131-161`).
- assistant 로그 저장은 스트림이 끝난 뒤에만 실행된다(`app/services/chat_service.py:107-129`).

본문을 읽지 않은 로컬 집계 결과:

- `ChatMessage`가 존재하는 원고 41개
- 체크포인트 스레드 52개
- 양쪽 메시지 개수가 다른 원고 9개

따라서 “저장 메시지가 사라짐” 중 일부는 DB 행 삭제가 아니라 체크포인트에 없는 메시지가 화면에서 누락되는 현상으로 확인된다. 스트림 중단, 체크포인트 실패, 삼켜진 DB 오류, 동일 원고 동시 요청도 코드상 가능하지만 특정 장애의 직접 원인으로는 아직 입증되지 않았다.

권장 조사·수정 순서:

1. `manuscript_id`, turn ID, DB 저장 성공, 체크포인트 완료, 스트림 완료/취소를 한 로그 흐름으로 연결
2. DB/체크포인트 메시지 개수 불일치 진단 명령을 운영 점검 항목으로 추가
3. 화면 이력의 기준을 `ChatMessage`로 통일하고 체크포인트는 LLM 실행 상태로 한정
4. 사용자 메시지 저장 실패는 요청 자체를 실패시키고, 동일 원고 턴은 직렬화

3번은 기존 이력 표시와 그래프 재개 의미가 바뀌므로 이번 PR에서 수정하지 않는다.

## 의존성·Ruff

적용한 좁은 변경:

- 미사용 `black`, `langchain-google-vertexai` 제거
- 테스트 전용 `pytest`를 dev 그룹으로 이동
- 잠금 파일 재생성으로 전용 전이 의존성 38개 제거
- Ruff E712 두 건을 `Manuscript.is_deleted.is_(False)`로 수정

Ruff의 일반 제안인 `not Manuscript.is_deleted`는 SQLAlchemy 표현식을 Python `False`로 평가해 항상 결과가 없는 필터가 되므로 사용하면 안 된다. 기존 삭제 통합 테스트가 목록과 단건 조회에서 soft-delete 제외 동작을 검증한다(`tests/integration/test_manuscript.py:71-84`).

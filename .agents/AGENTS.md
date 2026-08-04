# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

- **Communication Language:** Always communicate with the developer (USER) in **Korean** during chat interactions.
**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Name the Intent, Not the Mechanism

**Functions, variables, classes, and files should reveal their domain purpose, not merely the steps or technology they use.**

- Prefer the intended outcome: `find_evidence_for_claim()` over `execute_vector_search()`.
- Prefer the decision being represented: `research_needed` over `similarity_below_threshold`.
- Prefer the responsibility: `research_evidence.py` over `vector_store_utils.py`.
- Avoid vague names such as `process`, `handle`, `manage`, `data`, and `utils` when a domain term is available.
- Include implementation details in a name only when they are part of the public contract or needed to distinguish implementations.

## 5. Thin Endpoints, Logic in Services

**API 엔드포인트 함수(`app/api/endpoints/**`, `app/pages/**`)에 비즈니스 로직을 직접 작성하지 않는다.**

- 엔드포인트 함수는 요청 파싱 → 서비스 호출 → 응답 변환만 담당한다.
- DB 쿼리, 조건 분기, 비밀번호 해싱/토큰 발급 같은 도메인 로직은 `app/services/`에 함수로 분리한다.
- 새 라우터를 추가할 때도 동일하게: 라우터 파일은 얇게, 로직은 서비스 모듈로.

## 6. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 7. No Runtime Schema Migrations

**테이블 구조 변경은 애플리케이션 코드에서 하지 않는다.**

- `ALTER TABLE`, `PRAGMA table_info`로 컬럼 유무를 검사해 보정하는 런타임 마이그레이션 코드를 넣지 않는다.
- 스키마는 SQLAlchemy ORM 모델(`app/models/`)에만 정의하고, 신규·개발 환경은 `Base.metadata.create_all`로 테이블을 만든다.
- 기존 DB에 컬럼·테이블 변경이 필요하면 별도 마이그레이션 절차(수동 SQL, 전용 마이그레이션 도구 등)로 처리하고, 앱 기동 시 자동 적용하지 않는다.

## 8. Shared Vocabulary in Conversation

**대화에서 스스로 만든 이름·축약을 일상 용어인 것처럼 쓰지 않는다.**

- 이번 세션에서 새로 만든 클래스·모듈·패턴 이름을 설명 없이 고유명사처럼 던지지 않는다. (예: “상태 전이는 Context만” — 상대가 모르는 로컬 명칭)
- 설계·리팩터를 말할 때는 **역할·동작을 도메인 말로 먼저** 쓰고, 코드 식별자가 필요하면 그다음에 경로·전체 이름을 붙인다.
- 팀/업계에 이미 공유된 용어(HTTP, ORM, job status 등)와, 이 대화·이 PR에서만 생긴 이름을 구분한다. 후자는 매번 짧게 다시 풀어 쓴다.
- 지나친 축약(`ctx`, `Runner`, `stages`만 단독으로)으로 컴포넌트 이름만 덜렁 제시하지 않는다.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

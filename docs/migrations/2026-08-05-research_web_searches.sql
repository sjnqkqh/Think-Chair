-- research_web_searches: Brave 등 웹 검색 쿼리·hit 요약 (#31)
-- 대상: SQLite (앱 DATABASE_URL과 동일). 기존 DB에 수동 적용.

CREATE TABLE IF NOT EXISTS research_web_searches (
    id CHAR(32) NOT NULL,
    research_job_id CHAR(32) NOT NULL,
    user_id CHAR(32) NOT NULL,
    manuscript_id CHAR(32) NOT NULL,
    "query" TEXT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    max_results INTEGER NOT NULL,
    hit_results_json TEXT NOT NULL,
    error_code VARCHAR(64),
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (research_job_id) REFERENCES research_jobs (id),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (manuscript_id) REFERENCES manuscripts (id)
);

CREATE INDEX IF NOT EXISTS ix_research_web_searches_research_job_id
    ON research_web_searches (research_job_id);

CREATE INDEX IF NOT EXISTS ix_research_web_searches_user_id
    ON research_web_searches (user_id);

CREATE INDEX IF NOT EXISTS ix_research_web_searches_manuscript_id
    ON research_web_searches (manuscript_id);

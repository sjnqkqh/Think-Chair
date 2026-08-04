"""조사 job 실행 구간의 DB 세션·job 행 핸들.

status 변경 API(begin/finish/fail/recover)는 run_research_job 호출부만 쓴다.
필드 값 변경은 ResearchJob 메서드가, commit/refresh는 여기서 한다.
"""

from __future__ import annotations

import uuid

from app.logging import get_logger
from app.models.research import ResearchJob, ResearchJobStatus

logger = get_logger(__name__)


class ResearchJobContext:
    """실행 중인 조사 job의 세션과 ORM 행. 상태 전환은 호출부가 명시적으로 요청한다."""

    def __init__(self, db, job_id: uuid.UUID):
        self.db = db
        self.job_id = job_id
        self._job: ResearchJob | None = None

    @property
    def job(self) -> ResearchJob:
        if self._job is None:
            raise RuntimeError("research job session is not active")
        return self._job

    @property
    def query(self) -> str:
        return (self.job.claim_or_query or "").strip() or "관련 근거"

    def begin(self) -> bool:
        """job을 RUNNING으로 연다. 없거나 이미 취소면 False."""
        job = self.db.get(ResearchJob, self.job_id)
        if job is None or job.cancelled():
            return False
        job.mark_running()
        self.db.commit()
        self._job = job
        return True

    def cancelled(self) -> bool:
        job = self.db.get(ResearchJob, self.job_id)
        if job is not None:
            self.db.refresh(job)
        return job is None or job.cancelled()

    def recover_after_rollback(self) -> bool:
        """롤백 뒤 job 행을 다시 붙이고 RUNNING을 복구한다. 취소면 False."""
        job = self.db.get(ResearchJob, self.job_id)
        if job is None or job.cancelled():
            self._job = None
            return False
        job.mark_running()
        self.db.commit()
        self._job = job
        return True

    def reload_if_active(self) -> bool:
        """저장 직전 최신 행을 다시 읽는다. 취소·삭제면 False."""
        job = self.db.get(ResearchJob, self.job_id)
        if job is not None:
            self.db.refresh(job)
        if job is None or job.cancelled():
            logger.info(
                "research.job_cancelled_before_persist",
                job_id=str(self.job_id),
            )
            self._job = None
            return False
        self._job = job
        return True

    def finish(
        self,
        *,
        status: ResearchJobStatus,
        terminal_error: str | None = None,
    ) -> None:
        self.job.mark_outcome(status, terminal_error=terminal_error)
        self.db.commit()

    def fail_execution(self, terminal_error: str = "job_execution_error") -> None:
        try:
            self.db.rollback()
            job = self.db.get(ResearchJob, self.job_id)
            if job is not None:
                self.db.refresh(job)
            if job is None or job.cancelled():
                return
            job.mark_failed(terminal_error)
            self.db.commit()
            self._job = job
        except Exception:
            self.db.rollback()

    def close(self) -> None:
        self.db.close()

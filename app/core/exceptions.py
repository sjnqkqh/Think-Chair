class AppError(Exception):
    status_code = 500
    detail = "예기치 못한 오류가 발생했습니다."

    def __init__(self, detail: str | None = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "리소스를 찾을 수 없습니다."


class ConflictError(AppError):
    status_code = 409
    detail = "이미 존재하는 리소스입니다."


class UnauthorizedError(AppError):
    status_code = 401
    detail = "인증에 실패했습니다."

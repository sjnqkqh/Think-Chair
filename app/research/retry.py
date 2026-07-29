BASE_BACKOFF_SECONDS = 0.25
MAX_BACKOFF_SECONDS = 2.0


def retry_wait_seconds(attempt: int, retry_after: str | None = None) -> float:
    exponential_delay = BASE_BACKOFF_SECONDS * (2**attempt)
    try:
        server_delay = float(retry_after) if retry_after is not None else 0
    except ValueError:
        server_delay = 0
    return min(max(exponential_delay, server_delay), MAX_BACKOFF_SECONDS)

# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

# Install only locked production dependencies. Keeping this layer separate from
# application code makes dependency installation cacheable between builds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project


FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STORAGE_ROOT=/data/storage

# Copy the resolved virtual environment without shipping uv or build tools.
COPY --from=builder /app/.venv ./.venv
COPY app ./app

# Run the application without root privileges. Mount /data when persistent
# manuscript storage is required.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/storage \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

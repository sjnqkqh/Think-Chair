import datetime
import uuid

from sqlalchemy.orm import Session

from app.models.manuscript import ManuscriptLlmSettings

DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-v4-flash",
    "openai": "gpt-5.6-luna",
}
ALLOWED_MODELS_BY_PROVIDER = {
    "deepseek": frozenset({"deepseek-v4-flash", "deepseek-v4-pro"}),
    "openai": frozenset({"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}),
}
# Chat Completions 기준. OpenAI gpt-5.6-* 는 max를 거부하고 xhigh까지 허용한다.
# (문서에 max가 있어도 Chat Completions에서는 400; DeepSeek만 max를 받는다.)
ALLOWED_EFFORTS_BY_PROVIDER = {
    "deepseek": frozenset({"none", "low", "medium", "high", "xhigh", "max"}),
    "openai": frozenset({"none", "low", "medium", "high", "xhigh"}),
}
ALLOWED_EFFORTS = frozenset().union(*ALLOWED_EFFORTS_BY_PROVIDER.values())
DEFAULT_EFFORT = "high"
_OPENAI_MAX_FALLBACK_EFFORT = "xhigh"


def llm_settings_for_manuscript(
    db: Session, manuscript_id: uuid.UUID
) -> ManuscriptLlmSettings:
    """원고에 저장된 LLM 선택을 반환한다. 없으면 DeepSeek 기본값으로 둔다."""
    settings = db.get(ManuscriptLlmSettings, manuscript_id)
    if settings is not None:
        return settings
    settings = ManuscriptLlmSettings(
        manuscript_id=manuscript_id,
        provider=DEFAULT_PROVIDER,
        model=DEFAULT_MODEL_BY_PROVIDER[DEFAULT_PROVIDER],
        effort=DEFAULT_EFFORT,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def save_llm_settings_for_manuscript(
    db: Session,
    manuscript_id: uuid.UUID,
    *,
    provider: str,
    model: str,
    effort: str,
) -> ManuscriptLlmSettings:
    """원고의 LLM 선택(provider/model/effort)을 저장한다."""
    resolved_provider, resolved_model, resolved_effort = normalize_llm_choice(
        provider=provider, model=model, effort=effort
    )
    settings = llm_settings_for_manuscript(db, manuscript_id)
    settings.provider = resolved_provider
    settings.model = resolved_model
    settings.effort = resolved_effort
    settings.updated_at = datetime.datetime.utcnow()
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def normalize_llm_choice(
    *, provider: str, model: str, effort: str
) -> tuple[str, str, str]:
    """허용된 LLM 선택으로 맞춘다. provider별 허용 밖 model은 기본 모델로 교정한다."""
    resolved_provider = (provider or "").strip().lower()
    if resolved_provider not in ALLOWED_MODELS_BY_PROVIDER:
        raise ValueError(
            f"지원하지 않는 provider: {provider!r}. "
            f"사용 가능: {', '.join(sorted(ALLOWED_MODELS_BY_PROVIDER))}"
        )

    resolved_effort = (effort or "").strip().lower()
    allowed_efforts = ALLOWED_EFFORTS_BY_PROVIDER[resolved_provider]
    if resolved_effort not in allowed_efforts:
        raise ValueError(
            f"지원하지 않는 effort: {effort!r} (provider={resolved_provider}). "
            f"사용 가능: {', '.join(sorted(allowed_efforts))}"
        )

    resolved_model = (model or "").strip()
    allowed_models = ALLOWED_MODELS_BY_PROVIDER[resolved_provider]
    if resolved_model not in allowed_models:
        resolved_model = DEFAULT_MODEL_BY_PROVIDER[resolved_provider]
    return resolved_provider, resolved_model, resolved_effort


def resolve_request_effort(*, provider: str, effort: str) -> str:
    """이미 저장된 설정이 provider에 맞지 않으면 호출 전에 안전한 effort로 내린다."""
    resolved_provider = (provider or "").strip().lower()
    resolved_effort = (effort or "").strip().lower()
    allowed = ALLOWED_EFFORTS_BY_PROVIDER.get(resolved_provider)
    if allowed is None or resolved_effort in allowed:
        return resolved_effort
    if resolved_provider == "openai" and resolved_effort == "max":
        return _OPENAI_MAX_FALLBACK_EFFORT
    return DEFAULT_EFFORT


def llm_settings_fields(settings: ManuscriptLlmSettings) -> dict[str, str]:
    return {
        "provider": settings.provider,
        "model": settings.model,
        "effort": settings.effort,
    }

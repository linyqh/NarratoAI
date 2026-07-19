"""Shared config defaults used by both bootstrap and WebUI fallbacks."""

from __future__ import annotations

DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_OPENAI_COMPATIBLE_PROVIDER = "openai"

DEFAULT_VISION_LLM_PROVIDER = DEFAULT_OPENAI_COMPATIBLE_PROVIDER
DEFAULT_VISION_OPENAI_MODEL_NAME = "Qwen/Qwen3.5-122B-A10B"

DEFAULT_TEXT_LLM_PROVIDER = DEFAULT_OPENAI_COMPATIBLE_PROVIDER
DEFAULT_TEXT_OPENAI_MODEL_NAME = "Pro/zai-org/GLM-5"
DEFAULT_TEXT_OPENAI_FAST_MODEL_NAME = ""

DEFAULT_LLM_GENERATION_CONFIG = {
    "temperature": 1.0,
    "top_p": 0.95,
    "max_tokens": 65536,
    "thinking_level": "auto",
}

DEFAULT_LLM_THINKING_LEVELS = ["auto", "off", "low", "medium", "high"]

DEFAULT_LLM_GENERATION_APP_CONFIG = {
    f"{model_type}_openai_{param_name}": value
    for model_type in ("vision", "text")
    for param_name, value in DEFAULT_LLM_GENERATION_CONFIG.items()
}

DEFAULT_LLM_APP_CONFIG = {
    "vision_llm_provider": DEFAULT_VISION_LLM_PROVIDER,
    "vision_openai_model_name": DEFAULT_VISION_OPENAI_MODEL_NAME,
    "vision_openai_api_key": "",
    "vision_openai_base_url": DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    "text_llm_provider": DEFAULT_TEXT_LLM_PROVIDER,
    "text_openai_model_name": DEFAULT_TEXT_OPENAI_MODEL_NAME,
    "text_openai_fast_model_name": DEFAULT_TEXT_OPENAI_FAST_MODEL_NAME,
    "text_openai_api_key": "",
    "text_openai_base_url": DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    "tavily_api_key": "",
    "tavily_search_depth": "basic",
    "tavily_max_results": 5,
}
DEFAULT_LLM_APP_CONFIG.update(DEFAULT_LLM_GENERATION_APP_CONFIG)


def build_default_app_config(app_config: dict | None = None) -> dict:
    """Force the shared LLM defaults into a fresh app config."""
    merged = dict(app_config or {})
    merged.update(DEFAULT_LLM_APP_CONFIG)
    return merged


def merge_missing_app_defaults(app_config: dict | None = None) -> dict:
    """Backfill missing keys without overriding saved user values."""
    merged = dict(app_config or {})
    for key, value in DEFAULT_LLM_APP_CONFIG.items():
        merged.setdefault(key, value)
    return merged


def normalize_openai_compatible_model_name(
    model_name: str,
    provider: str = DEFAULT_OPENAI_COMPATIBLE_PROVIDER,
) -> str:
    """Strip only the internal OpenAI-compatible provider prefix if present."""
    normalized = (model_name or "").strip()
    provider_prefix = f"{provider}/"
    if normalized.lower().startswith(provider_prefix):
        return normalized[len(provider_prefix):]
    return normalized


def resolve_text_model_name(
    app_config: dict,
    provider: str = DEFAULT_OPENAI_COMPATIBLE_PROVIDER,
    *,
    prefer_fast: bool = False,
) -> str:
    """Resolve the configured reasoning or fast text model with legacy fallback."""
    provider = (provider or DEFAULT_OPENAI_COMPATIBLE_PROVIDER).strip().lower()
    reasoning_model = normalize_openai_compatible_model_name(
        str(app_config.get(f"text_{provider}_model_name") or ""),
        provider=provider,
    )
    if not reasoning_model and provider == DEFAULT_OPENAI_COMPATIBLE_PROVIDER:
        reasoning_model = DEFAULT_TEXT_OPENAI_MODEL_NAME

    if not prefer_fast:
        return reasoning_model

    fast_model = normalize_openai_compatible_model_name(
        str(app_config.get(f"text_{provider}_fast_model_name") or ""),
        provider=provider,
    )
    return fast_model or reasoning_model


def get_openai_compatible_ui_values(
    full_model_name: str,
    default_model: str,
    provider: str = DEFAULT_OPENAI_COMPATIBLE_PROVIDER,
) -> tuple[str, str]:
    """Keep the UI provider fixed while preserving the full model identifier."""
    current_model = normalize_openai_compatible_model_name(
        full_model_name or default_model,
        provider=provider,
    )
    return provider, current_model or default_model

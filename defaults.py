"""Shared config defaults used by both bootstrap and WebUI fallbacks."""

from __future__ import annotations

DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_OPENAI_COMPATIBLE_PROVIDER = "openai"

DEFAULT_VISION_LLM_PROVIDER = DEFAULT_OPENAI_COMPATIBLE_PROVIDER
DEFAULT_VISION_OPENAI_MODEL_NAME = "Qwen/Qwen3.5-122B-A10B"

DEFAULT_TEXT_LLM_PROVIDER = DEFAULT_OPENAI_COMPATIBLE_PROVIDER
DEFAULT_TEXT_OPENAI_MODEL_NAME = "Pro/zai-org/GLM-5"

# 影片分析模式
#   - "frames": 抽取关键帧后逐批送入 OpenAI 兼容视觉模型（默认）
#   - "direct": 直接上传完整视频文件给原生大模型（Gemini / Qwen-VL）一次性分析
DEFAULT_VIDEO_ANALYSIS_MODE = "frames"

# 「直接上传分析」支持的官方原生 provider
DIRECT_VIDEO_PROVIDER_GEMINI = "gemini"
DIRECT_VIDEO_PROVIDER_QWEN = "qwen"
DEFAULT_DIRECT_VIDEO_PROVIDER = DIRECT_VIDEO_PROVIDER_GEMINI

# Gemini 官方默认模型（File API）
DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME = "gemini-2.0-flash-exp"

# Qwen-VL 官方默认模型（DashScope MultiModalConversation）
DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME = "qwen-vl-max-latest"


DEFAULT_LLM_APP_CONFIG = {
    "vision_llm_provider": DEFAULT_VISION_LLM_PROVIDER,
    "vision_openai_model_name": DEFAULT_VISION_OPENAI_MODEL_NAME,
    "vision_openai_api_key": "",
    "vision_openai_base_url": DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    "text_llm_provider": DEFAULT_TEXT_LLM_PROVIDER,
    "text_openai_model_name": DEFAULT_TEXT_OPENAI_MODEL_NAME,
    "text_openai_api_key": "",
    "text_openai_base_url": DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    # 影片分析模式（frames / direct）
    "video_analysis_mode": DEFAULT_VIDEO_ANALYSIS_MODE,
    # 「直接上传分析」当前选用的官方 provider（gemini / qwen）
    "direct_video_provider": DEFAULT_DIRECT_VIDEO_PROVIDER,
    # Gemini 官方原生 API 配置
    "direct_video_gemini_api_key": "",
    "direct_video_gemini_model_name": DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME,
    # Qwen-VL（阿里百炼 / DashScope）配置
    "direct_video_qwen_api_key": "",
    "direct_video_qwen_model_name": DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME,
}





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

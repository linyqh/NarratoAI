"""UI orchestration for the independent film-vision fusion narration mode."""

import asyncio

import streamlit as st

from app.config import config
from app.config.defaults import DEFAULT_VISION_MAX_CONCURRENCY
from app.services.film_vision_fusion import FilmVisionFusion, VisualEvidence


def collect_visual_evidence(
    *,
    video_path: str,
    video_theme: str,
    custom_prompt: str,
    frame_interval_seconds: float,
    vision_batch_size: int,
    progress_callback=None,
) -> VisualEvidence:
    """Analyze one source film and return time-coded evidence for fusion prompts."""
    provider = str(
        st.session_state.get("vision_llm_provider")
        or config.app.get("vision_llm_provider", "openai")
    ).lower()
    api_key = st.session_state.get(f"vision_{provider}_api_key") or config.app.get(
        f"vision_{provider}_api_key", ""
    )
    model_name = st.session_state.get(f"vision_{provider}_model_name") or config.app.get(
        f"vision_{provider}_model_name", ""
    )
    base_url = st.session_state.get(f"vision_{provider}_base_url") or config.app.get(
        f"vision_{provider}_base_url", ""
    )
    if not api_key or not model_name:
        raise ValueError("未配置视觉模型。请先在设置中配置视觉模型并测试连接。")

    return asyncio.run(
        FilmVisionFusion().collect_visual_evidence(
            video_path=video_path,
            video_theme=video_theme,
            custom_prompt=custom_prompt,
            frame_interval_seconds=frame_interval_seconds,
            vision_batch_size=vision_batch_size,
            vision_llm_provider=provider,
            vision_api_key=api_key,
            vision_model_name=model_name,
            vision_base_url=base_url,
            max_concurrency=int(
                config.frames.get("vision_max_concurrency", DEFAULT_VISION_MAX_CONCURRENCY)
            ),
            progress_callback=progress_callback,
        )
    )

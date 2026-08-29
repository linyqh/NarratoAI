"""UI orchestration for the independent film-vision fusion narration mode."""

import asyncio
from pathlib import Path

import streamlit as st

from app.config import config
from app.config.defaults import DEFAULT_VISION_MAX_CONCURRENCY
from app.services.film_vision_fusion import FilmVisionFusion, VisualEvidence
from app.services.documentary.local_analysis_tasks import (
    LocalAnalysisTaskRunner, LocalAnalysisTaskStore, batch_checkpoint_from_result, estimate_full_film_analysis,
    batch_result_from_checkpoint,
)
from app.services.visual_evidence_artifact import build_source_video_identity
from app.utils import utils
from app.utils import video_processor


def collect_visual_evidence(
    *,
    video_path: str,
    video_theme: str,
    custom_prompt: str,
    frame_interval_seconds: float,
    vision_batch_size: int,
    progress_callback=None,
    completed_batches=None,
    checkpoint_callback=None,
    is_cancelled=None,
    vision_settings: dict | None = None,
) -> VisualEvidence:
    """Analyze one source film and return time-coded evidence for fusion prompts."""
    settings = vision_settings or _current_vision_settings()
    provider = settings["provider"]
    api_key = settings["api_key"]
    model_name = settings["model_name"]
    base_url = settings["base_url"]
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
            completed_batches=completed_batches,
            checkpoint_callback=checkpoint_callback,
            is_cancelled=is_cancelled,
        )
    )


def _current_vision_settings() -> dict:
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
    return {"provider": provider, "api_key": api_key, "model_name": model_name, "base_url": base_url}


def start_local_visual_analysis(**request) -> str:
    """Start a resumable local analysis without tying it to the current page request."""
    video_path = str(request["video_path"])
    task_store = LocalAnalysisTaskStore(Path(utils.task_dir("visual_analysis")))
    task = task_store.create(request, build_source_video_identity(video_path))
    vision_settings = _current_vision_settings()

    def work(progress, checkpoint, cancelled):
        evidence = collect_visual_evidence(
            **request,
            progress_callback=progress,
            checkpoint_callback=lambda batch: checkpoint(batch_checkpoint_from_result(batch)),
            is_cancelled=cancelled,
            vision_settings=vision_settings,
        )
        return {"artifact_path": evidence.artifact_path, "visual_evidence": evidence.context}

    LocalAnalysisTaskRunner(task_store).start(task["task_id"], work)
    return task["task_id"]


def estimate_local_visual_analysis(video_path: str, frame_interval_seconds: float, vision_batch_size: int):
    """Estimate full-film work from local metadata without extracting any frames."""
    duration = video_processor.VideoProcessor(video_path).duration
    return estimate_full_film_analysis(
        duration_seconds=duration,
        frame_interval_seconds=frame_interval_seconds,
        vision_batch_size=vision_batch_size,
        max_concurrency=int(config.frames.get("vision_max_concurrency", DEFAULT_VISION_MAX_CONCURRENCY)),
    )


def resume_local_visual_analysis(task_id: str) -> None:
    """Resume only the successfully checkpointed batches for an unchanged local source."""
    task_store = LocalAnalysisTaskStore(Path(utils.task_dir("visual_analysis")))
    task = task_store.read(task_id)
    request = dict(task["request"])
    if build_source_video_identity(str(request["video_path"])) != task["source_video_identity"]:
        raise ValueError("当前视频与可恢复视觉分析任务的来源不一致")
    recovered = [batch_result_from_checkpoint(item) for item in task.get("completed_batches", [])]
    task_store.update(task_id, status="queued", cancel_requested=False, error_message="")
    vision_settings = _current_vision_settings()

    def work(progress, checkpoint, cancelled):
        evidence = collect_visual_evidence(
            **request,
            completed_batches=recovered,
            progress_callback=progress,
            checkpoint_callback=lambda batch: checkpoint(batch_checkpoint_from_result(batch)),
            is_cancelled=cancelled,
            vision_settings=vision_settings,
        )
        return {"artifact_path": evidence.artifact_path, "visual_evidence": evidence.context}

    LocalAnalysisTaskRunner(task_store).start(task_id, work)


def local_visual_analysis_status(task_id: str) -> dict:
    return LocalAnalysisTaskStore(Path(utils.task_dir("visual_analysis"))).read(task_id)


def find_local_visual_analysis(video_path: str) -> dict | None:
    store = LocalAnalysisTaskStore(Path(utils.task_dir("visual_analysis")))
    return store.find_latest_for_source(build_source_video_identity(video_path))


def cancel_local_visual_analysis(task_id: str) -> None:
    LocalAnalysisTaskStore(Path(utils.task_dir("visual_analysis"))).request_cancel(task_id)

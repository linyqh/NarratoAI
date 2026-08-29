"""Timed visual evidence for the independent film-vision fusion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.documentary.frame_analysis_service import DocumentaryFrameAnalysisService
from app.services.visual_evidence_artifact import (
    highlight_candidate_state,
    usable_highlight_candidates,
    validate_visual_evidence_artifact,
)
from app.services.visual_claims import contains_unsupported_audio_claim


def _time_range_start(value: str) -> str:
    return str(value or "").split("-", 1)[0].strip()


def format_visual_evidence(
    artifact: dict[str, Any],
    *,
    max_observations_per_batch: int = 2,
) -> str:
    """Turn successful frame-analysis batches into bounded, time-coded model context.

    The raw artifact keeps every frame observation for auditability. Text LLMs do
    not need every repeated observation, though, so the prompt context keeps the
    batch summary plus a small number of representative observations.
    """
    evidence_blocks: list[tuple[str, str]] = []
    for batch in artifact.get("batches", []):
        if not isinstance(batch, dict) or batch.get("status") == "failed":
            continue

        time_range = str(batch.get("time_range") or "").strip()
        summary = str(
            batch.get("overall_activity_summary")
            or batch.get("fallback_summary")
            or ""
        ).strip()
        if contains_unsupported_audio_claim(summary):
            summary = ""
        observations = batch.get("frame_observations") or []
        try:
            observation_limit = max(0, int(max_observations_per_batch))
        except (TypeError, ValueError):
            observation_limit = 2
        observation_lines = [
            f"- {str(item.get('timestamp') or '').strip()}: {str(item.get('observation') or '').strip()}"
            for item in observations[:observation_limit]
            if isinstance(item, dict)
            and str(item.get("observation") or "").strip()
            and not contains_unsupported_audio_claim(str(item.get("observation") or ""))
        ]
        if not time_range or (not summary and not observation_lines):
            continue

        lines = [f"## {time_range}"]
        if summary:
            lines.append(f"- 画面摘要：{summary}")
        lines.extend(observation_lines)
        evidence_blocks.append((_time_range_start(time_range), "\n".join(lines)))

    if not evidence_blocks:
        raise ValueError("逐帧分析未返回可用视觉证据，请检查视觉模型后重试。")

    evidence_blocks.sort(key=lambda item: item[0])
    return "# 视觉证据（仅可用于确认画面事实）\n\n" + "\n\n".join(
        block for _, block in evidence_blocks
    )


def format_highlight_candidates(artifact: dict[str, Any]) -> str:
    """Create compact, time-coded source-highlight candidates for OST selection.

    Candidates are suggestions grounded in visual evidence, not instructions to
    force every listed range into the script. They intentionally stay separate
    from ordinary visual evidence so the matching model can budget source audio
    across story, performance, action and visual spectacle rather than only dialogue.
    """
    candidates = usable_highlight_candidates(artifact)

    entries: list[tuple[str, str]] = []
    for candidate in candidates:
        time_range = str(candidate.time_range)
        category = candidate.category
        reason = candidate.reason
        score = candidate.score
        entries.append(
            (_time_range_start(time_range), f"- {time_range}｜{category}｜价值 {score}/5：{reason}")
        )

    if not entries:
        return ""
    entries.sort(key=lambda item: item[0])
    return "# 原片高光候选（仅作 OST=1 优先级依据）\n" + "\n".join(
        entry for _, entry in entries
    )


@dataclass(frozen=True)
class VisualEvidence:
    """Visual Evidence plus the artifact retained for the user-facing audit."""

    context: str
    highlight_candidates: str
    artifact_path: str
    artifact: dict[str, Any]
    source_verified: bool = True
    highlight_state: str = "available"


def load_visual_evidence_artifact(
    artifact: dict[str, Any],
    *,
    source_video_path: str,
    artifact_path: str,
    allow_unverified_source: bool = False,
) -> VisualEvidence:
    """Restore compatible persisted evidence without re-running vision analysis."""
    source_verified = validate_visual_evidence_artifact(
        artifact,
        source_video_path=source_video_path,
        allow_unverified_source=allow_unverified_source,
    )
    return VisualEvidence(
        context=format_visual_evidence(artifact, max_observations_per_batch=0),
        highlight_candidates=format_highlight_candidates(artifact),
        artifact_path=artifact_path,
        artifact=artifact,
        source_verified=source_verified,
        highlight_state=highlight_candidate_state(artifact),
    )


class FilmVisionFusion:
    """Collect visual evidence behind one stable interface for fusion narration."""

    def __init__(
        self,
        frame_analysis_factory: Callable[[], DocumentaryFrameAnalysisService] = DocumentaryFrameAnalysisService,
    ) -> None:
        self._frame_analysis_factory = frame_analysis_factory

    async def collect_visual_evidence(
        self,
        *,
        video_path: str,
        video_theme: str,
        custom_prompt: str,
        frame_interval_seconds: float,
        vision_batch_size: int,
        vision_llm_provider: str,
        vision_api_key: str,
        vision_model_name: str,
        vision_base_url: str,
        max_concurrency: int,
        progress_callback=None,
        completed_batches=None,
        checkpoint_callback=None,
        is_cancelled=None,
    ) -> VisualEvidence:
        analysis = await self._frame_analysis_factory().analyze_video(
            video_path=video_path,
            video_theme=video_theme,
            custom_prompt=custom_prompt,
            frame_interval_input=frame_interval_seconds,
            vision_batch_size=vision_batch_size,
            vision_llm_provider=vision_llm_provider,
            vision_api_key=vision_api_key,
            vision_model_name=vision_model_name,
            vision_base_url=vision_base_url,
            max_concurrency=max_concurrency,
            progress_callback=progress_callback,
            completed_batches=completed_batches,
            checkpoint_callback=checkpoint_callback,
            is_cancelled=is_cancelled,
        )
        artifact = analysis["analysis_artifact"]
        # Keep the full per-frame observations in the JSON artifact, but send
        # only one bounded summary per time block to the text LLMs.
        context = format_visual_evidence(artifact, max_observations_per_batch=0)
        return VisualEvidence(
            context=context,
            highlight_candidates=format_highlight_candidates(artifact),
            artifact_path=str(analysis["analysis_json_path"]),
            artifact=artifact,
            highlight_state=highlight_candidate_state(artifact),
        )

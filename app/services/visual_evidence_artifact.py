"""Identity and compatibility checks for persisted visual-evidence artifacts."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.services.visual_claims import contains_unsupported_audio_claim
from app.services.fusion_models import CandidateRejection, HighlightCandidateIntake


ARTIFACT_VERSION = "documentary-frame-analysis-v4"
SUPPORTED_ARTIFACT_VERSIONS = frozenset(
    {
        "documentary-frame-analysis-v2",
        "documentary-frame-analysis-v3",
        ARTIFACT_VERSION,
    }
)
_HASH_CHUNK_SIZE = 1024 * 1024


def build_source_video_identity(video_path: str) -> dict[str, Any]:
    """Return a content identity that survives a source video's relocation."""
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    digest = hashlib.sha256()
    with open(video_path, "rb") as source:
        while chunk := source.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)

    return {
        "algorithm": "sha256",
        "sha256": digest.hexdigest(),
        "size_bytes": os.path.getsize(video_path),
    }


def validate_visual_evidence_artifact(
    artifact: dict[str, Any],
    *,
    source_video_path: str,
    allow_unverified_source: bool = False,
) -> bool:
    """Validate an artifact and return whether its source video was verified.

    Legacy artifacts do not include a content identity. They may only be used
    after an explicit user acknowledgement; this keeps a same-named but
    different film from silently contributing visual facts to a Fusion Script.
    """
    if not isinstance(artifact, dict):
        raise ValueError("视觉证据产物必须是 JSON 对象。")
    version = str(artifact.get("artifact_version") or "")
    if version not in SUPPORTED_ARTIFACT_VERSIONS:
        raise ValueError("不是受支持的视觉证据产物。")
    if not isinstance(artifact.get("batches"), list):
        raise ValueError("视觉证据产物缺少 batches。")

    stored_identity = artifact.get("source_video_identity")
    if not isinstance(stored_identity, dict):
        if allow_unverified_source:
            return False
        raise ValueError(
            "此历史产物没有视频内容校验信息。确认当前视频与分析来源一致后，"
            "请勾选“允许导入未验证来源的历史产物”。"
        )

    stored_hash = str(stored_identity.get("sha256") or "").lower()
    stored_algorithm = str(stored_identity.get("algorithm") or "").lower()
    stored_size = stored_identity.get("size_bytes")
    if stored_algorithm != "sha256" or len(stored_hash) != 64 or not isinstance(stored_size, int):
        raise ValueError("视觉证据产物的视频内容校验信息无效。")

    current_identity = build_source_video_identity(source_video_path)
    if (
        current_identity["size_bytes"] != stored_size
        or not hmac.compare_digest(current_identity["sha256"], stored_hash)
    ):
        raise ValueError("当前视频与视觉证据产物的来源不一致，已拒绝导入。")
    return True


def usable_highlight_candidates(artifact: dict[str, Any]) -> list[HighlightCandidate]:
    """Project the accepted candidates from the canonical artifact intake."""
    return list(read_highlight_candidate_intake(artifact).candidates)


def highlight_candidate_rejections(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Project rejected candidates for legacy UI callers."""
    return [rejection.to_dict() for rejection in read_highlight_candidate_intake(artifact).rejections]


def read_highlight_candidate_intake(artifact: dict[str, Any]) -> HighlightCandidateIntake:
    """Parse every submitted candidate once into one accepted or rejected outcome."""
    raw_candidates = _submitted_highlight_candidates(artifact)
    normalized: list[HighlightCandidate] = []
    rejections: list[CandidateRejection] = []
    source_identity = artifact.get("source_video_identity")
    batch_ranges = _batch_ranges(artifact)
    source_hash = str(source_identity.get("sha256") or "") if isinstance(source_identity, dict) else "legacy"
    for index, candidate in enumerate(raw_candidates):
        payload = candidate if isinstance(candidate, dict) else {}
        candidate_id = _candidate_id(payload, source_hash, fallback=f"artifact-{index}")
        if not isinstance(candidate, dict):
            rejections.append(CandidateRejection(candidate_id, "", "malformed_candidate"))
            continue
        time_range = str(candidate.get("time_range") or "").strip()
        category = str(candidate.get("category") or "").strip()
        reason = str(candidate.get("reason") or "").strip()
        try:
            score = int(candidate.get("score"))
        except (TypeError, ValueError):
            score = 0
        if (
            not _is_valid_time_range(time_range)
            or not category
            or not reason
            or contains_unsupported_audio_claim(reason)
            or not 1 <= score <= 5
        ):
            rejections.append(CandidateRejection(candidate_id, time_range, _highlight_candidate_rejection_reason(payload)))
            continue
        candidate_range = TimeRange.parse(time_range)
        try:
            candidate_batch_index = int(candidate["batch_index"])
        except (KeyError, TypeError, ValueError):
            candidate_batch_index = None
        applicable_ranges = (
            [batch_ranges[candidate_batch_index]]
            if candidate_batch_index in batch_ranges
            else list(batch_ranges.values())
        )
        if not any(
            batch_range.start_seconds <= candidate_range.start_seconds
            and candidate_range.end_seconds <= batch_range.end_seconds
            for batch_range in applicable_ranges
        ):
            rejections.append(CandidateRejection(candidate_id, time_range, "outside_batch_range"))
            continue
        signal_scores: dict[str, int] = {}
        defaulted_signals: list[str] = []
        for signal in ("story_importance", "visual_impact", "performance_value"):
            try:
                signal_scores[signal] = max(1, min(5, int(candidate.get(signal, 3))))
            except (TypeError, ValueError):
                signal_scores[signal] = 3
            if signal not in candidate:
                defaulted_signals.append(signal)
        try:
            video_id = int(candidate["video_id"]) if candidate.get("video_id") is not None else None
        except (TypeError, ValueError):
            video_id = None
        normalized.append(
            HighlightCandidate(
                time_range=TimeRange.parse(time_range),
                category=category,
                reason=reason,
                score=score,
                **signal_scores,
                video_id=video_id,
                video_name=str(candidate.get("video_name") or ""),
                source_video_identity=source_identity if isinstance(source_identity, dict) else None,
                source_identity_status="available" if isinstance(source_identity, dict) else "defaulted_legacy",
                defaulted_signals=tuple(defaulted_signals),
                candidate_id=candidate_id,
            )
        )
    return HighlightCandidateIntake(
        candidates=tuple(normalized),
        rejections=tuple(rejections),
        submitted_count=len(raw_candidates),
    )


def _submitted_highlight_candidates(artifact: dict[str, Any]) -> list[Any]:
    raw_candidates = artifact.get("highlight_candidates")
    if isinstance(raw_candidates, list):
        return list(raw_candidates)
    candidates: list[Any] = []
    for fallback_index, batch in enumerate(artifact.get("batches", [])):
        if not isinstance(batch, dict) or not isinstance(batch.get("highlight_candidates"), list):
            continue
        for item in batch["highlight_candidates"]:
            candidates.append({
                **item,
                "batch_index": batch.get("batch_index", fallback_index),
                "time_range": item.get("time_range") or batch.get("time_range"),
            } if isinstance(item, dict) else item)
    return candidates


def _batch_ranges(artifact: dict[str, Any]) -> dict[int, TimeRange]:
    ranges: dict[int, TimeRange] = {}
    for fallback_index, batch in enumerate(artifact.get("batches", [])):
        if not isinstance(batch, dict):
            continue
        try:
            ranges[int(batch.get("batch_index", fallback_index))] = TimeRange.parse(str(batch.get("time_range") or ""))
        except (TypeError, ValueError):
            continue
    return ranges


def _candidate_id(candidate: dict[str, Any], source_hash: str, *, fallback: str) -> str:
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    if candidate_id:
        return candidate_id
    identity = "|".join(str(candidate.get(field) or "") for field in ("time_range", "category", "reason"))
    return hashlib.sha256(f"{source_hash}|{identity}".encode("utf-8")).hexdigest()[:16] if identity.strip("|") else fallback


def _highlight_candidate_rejection_reason(candidate: dict[str, Any]) -> str:
    if not candidate:
        return "malformed_candidate"
    if not _is_valid_time_range(str(candidate.get("time_range") or "")):
        return "invalid_time_range"
    if not str(candidate.get("category") or "").strip():
        return "missing_category"
    reason = str(candidate.get("reason") or "").strip()
    if not reason:
        return "missing_visual_reason"
    if contains_unsupported_audio_claim(reason):
        return "unsupported_audio_claim"
    try:
        if not 1 <= int(candidate.get("score")) <= 5:
            return "invalid_score"
    except (TypeError, ValueError):
        return "invalid_score"
    return "outside_batch_range"


def highlight_candidate_state(artifact: dict[str, Any]) -> str:
    """Classify whether this artifact actually ran highlighter inference."""
    if usable_highlight_candidates(artifact):
        return "available"
    if isinstance(artifact.get("highlight_candidates"), list):
        return "analyzed_empty"
    if any(
        isinstance(batch, dict) and isinstance(batch.get("highlight_candidates"), list)
        for batch in artifact.get("batches", [])
    ):
        return "analyzed_empty"
    return "unavailable_legacy"


def _is_valid_time_range(value: str) -> bool:
    try:
        TimeRange.parse(value)
        return True
    except (TypeError, ValueError):
        return False

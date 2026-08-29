"""Identity and compatibility checks for persisted visual-evidence artifacts."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.services.visual_claims import contains_unsupported_audio_claim


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
    """Return normalized, valid highlighter output from current and legacy artifacts."""
    raw_candidates = artifact.get("highlight_candidates")
    candidates: list[dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        candidates.extend(item for item in raw_candidates if isinstance(item, dict))
    else:
        for batch_index, batch in enumerate(artifact.get("batches", [])):
            if not isinstance(batch, dict) or not isinstance(batch.get("highlight_candidates"), list):
                continue
            for item in batch["highlight_candidates"]:
                if isinstance(item, dict):
                    candidates.append(
                        {
                            "batch_index": batch.get("batch_index", batch_index),
                            "time_range": item.get("time_range") or batch.get("time_range"),
                            "category": item.get("category"),
                            "reason": item.get("reason"),
                            "score": item.get("score"),
                        }
                    )

    normalized: list[HighlightCandidate] = []
    source_identity = artifact.get("source_video_identity")
    batch_ranges: dict[int, TimeRange] = {}
    for fallback_index, batch in enumerate(artifact.get("batches", [])):
        if not isinstance(batch, dict):
            continue
        try:
            batch_index = int(batch.get("batch_index", fallback_index))
            batch_ranges[batch_index] = TimeRange.parse(str(batch.get("time_range") or ""))
        except (TypeError, ValueError):
            continue
    for candidate in candidates:
        time_range = str(candidate.get("time_range") or "").strip()
        category = str(candidate.get("category") or "").strip()
        reason = str(candidate.get("reason") or "").strip()
        try:
            score = int(candidate.get("score"))
        except (TypeError, ValueError):
            continue
        if (
            not _is_valid_time_range(time_range)
            or not category
            or not reason
            or contains_unsupported_audio_claim(reason)
            or not 1 <= score <= 5
        ):
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
        source_hash = str(source_identity.get("sha256") or "") if isinstance(source_identity, dict) else "legacy"
        candidate_id = str(candidate.get("candidate_id") or "").strip() or hashlib.sha256(
            f"{source_hash}|{time_range}|{category}|{reason}".encode("utf-8")
        ).hexdigest()[:16]
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
    return normalized


def highlight_candidate_rejections(artifact: dict[str, Any]) -> list[dict[str, str]]:
    """Return one auditable rejection for every artifact candidate that cannot normalize."""
    raw_candidates = artifact.get("highlight_candidates")
    candidates = list(raw_candidates) if isinstance(raw_candidates, list) else []
    if not isinstance(raw_candidates, list):
        for batch_index, batch in enumerate(artifact.get("batches", [])):
            if isinstance(batch, dict) and isinstance(batch.get("highlight_candidates"), list):
                candidates.extend(
                    {**item, "batch_index": batch.get("batch_index", batch_index)}
                    if isinstance(item, dict) else item
                    for item in batch["highlight_candidates"]
                )
    rejected = []
    for index, candidate in enumerate(candidates):
        probe = {**artifact, "highlight_candidates": [candidate]}
        if usable_highlight_candidates(probe):
            continue
        payload = candidate if isinstance(candidate, dict) else {}
        rejected.append({
            "candidate_id": str(payload.get("candidate_id") or f"artifact-{index}"),
            "time_range": str(payload.get("time_range") or ""),
            "reason": "invalid_highlight_candidate",
        })
    return rejected


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

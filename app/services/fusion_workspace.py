"""Single projection seam for the Film Vision Fusion creator workspace."""

from __future__ import annotations

from typing import Any

from app.services.documentary.frame_analysis_models import TimeRange
from app.services.fusion_script_pipeline import FusionScriptPipeline


_PHASES = {
    "not_started", "running", "waiting_for_review", "approved", "warning",
    "blocked", "invalidated", "archived",
}


def project_fusion_workspace(
    *,
    task: dict[str, Any] | None = None,
    finalization: dict[str, Any] | None = None,
    narrative_map: dict[str, Any] | None = None,
    quality_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert durable Fusion data into one stable, UI-facing workspace read model."""
    task = task or {}
    finalization = finalization or {}
    preflight = finalization.get("preflight") or {}
    blockers = list(preflight.get("blockers") or [])
    warnings = list(preflight.get("warnings") or [])
    quality = list(quality_findings or finalization.get("narrative_quality_findings") or [])
    decisions = list(finalization.get("review_decisions") or [])
    ignored_quality = {
        (str(item.get("segment_id") or ""), str(item.get("code") or ""))
        for item in decisions
        if isinstance(item, dict) and item.get("action") == "ignored" and item.get("kind") == "quality"
    }
    quality = [
        item for item in quality
        if isinstance(item, dict)
        and (str(item.get("segment_id") or ""), str(item.get("code") or "")) not in ignored_quality
    ]
    task_status = str(task.get("status") or "")
    if blockers or task_status in {"failed", "cancelled", "interrupted"}:
        phase = "blocked"
    elif task_status in {"queued", "running"}:
        phase = "running"
    elif warnings or quality:
        phase = "warning"
    elif finalization.get("renderable"):
        phase = "approved"
    elif finalization:
        phase = "waiting_for_review"
    else:
        phase = "not_started"
    queue = [
        {"priority": 0, "kind": "blocker", **item}
        for item in blockers
        if isinstance(item, dict)
    ] + [
        {"priority": 1, "kind": "warning", **item}
        for item in warnings
        if isinstance(item, dict)
    ] + [
        {"priority": 2, "kind": "quality", **item}
        for item in quality
        if isinstance(item, dict)
    ]
    queue.sort(key=lambda item: (int(item["priority"]), str(item.get("segment_id") or ""), str(item.get("code") or "")))
    stream_snapshot = task.get("stream_snapshot") if isinstance(task.get("stream_snapshot"), dict) else {}
    return {
        "phase": phase if phase in _PHASES else "not_started",
        "active_version_id": str(finalization.get("active_version_id") or ""),
        "review_queue": queue,
        "task_center": {
            "task_id": task.get("task_id"),
            "status": task_status,
            "progress": task.get("progress"),
            "failure_category": stream_snapshot.get("failure_category"),
            "recoverable": task_status in {"failed", "interrupted", "cancelled"},
        },
        "inspector": {
            "narrative_map": narrative_map or finalization.get("narrative_map") or {},
            "preflight": preflight,
            "stream_diagnostics": stream_snapshot.get("failure_diagnostics") or {},
            "review_decisions": decisions,
        },
        "versions": list(finalization.get("version_history") or []),
    }


def project_fusion_task_center_details(task: dict[str, Any] | None) -> dict[str, Any]:
    """Expose bounded matching-task diagnostics without leaking the full request."""
    task = task or {}
    stream_snapshot = task.get("stream_snapshot")
    stream_snapshot = stream_snapshot if isinstance(stream_snapshot, dict) else {}
    return {
        "task_id": str(task.get("task_id") or ""),
        "status": str(task.get("status") or ""),
        "progress": task.get("progress"),
        "error_message": str(task.get("error_message") or ""),
        "failure_category": str(stream_snapshot.get("failure_category") or ""),
        "failure_diagnostics": stream_snapshot.get("failure_diagnostics") or {},
        "segment_matches": [
            {
                "segment_id": str(item.get("segment_id") or ""),
                "status": str(item.get("status") or ""),
                "error_message": str(item.get("error_message") or ""),
            }
            for item in task.get("segment_matches") or []
            if isinstance(item, dict)
        ],
        "can_cancel": str(task.get("status") or "") in {"queued", "running"},
        "can_resume": str(task.get("status") or "") in {"failed", "cancelled", "interrupted"},
    }


def project_fusion_task_center(
    *, visual_analysis_tasks: list[dict[str, Any]] | None, matching_tasks: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Combine durable Fusion task summaries into one action-oriented Task Center list."""
    tasks = []
    for kind, entries in (
        ("visual_analysis", visual_analysis_tasks or []),
        ("fusion_matching", matching_tasks or []),
    ):
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("task_id") or ""):
                continue
            status = str(entry.get("status") or "")
            tasks.append(
                {
                    "kind": kind,
                    "task_id": str(entry.get("task_id") or ""),
                    "status": status,
                    "progress": entry.get("progress"),
                    "message": str(entry.get("message") or ""),
                    "updated_at": str(entry.get("updated_at") or ""),
                    "failure_category": str(entry.get("failure_category") or ""),
                    "can_cancel": status in {"queued", "running"},
                    "can_resume": status in {"failed", "interrupted", "cancelled"},
                }
            )
    return sorted(tasks, key=lambda item: item["updated_at"], reverse=True)


def project_fusion_review_context(
    *, task: dict[str, Any] | None, finalization: dict[str, Any] | None, segment_id: str
) -> dict[str, Any]:
    """Project every evidence-bound artefact related to one reviewable segment."""
    task = task or {}
    finalization = finalization or {}
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    plan = request.get("plan_payload") if isinstance(request.get("plan_payload"), dict) else {}
    segment = next(
        (
            item for item in plan.get("segments") or []
            if isinstance(item, dict) and str(item.get("segment_id") or "") == str(segment_id)
        ),
        {},
    )
    narrative_map = finalization.get("narrative_map") if isinstance(finalization.get("narrative_map"), dict) else {}
    story_beat = next(
        (
            item for item in narrative_map.get("beats") or []
            if isinstance(item, dict) and str(item.get("segment_id") or "") == str(segment_id)
        ),
        {},
    )
    time_range = str(segment.get("core_window") or story_beat.get("evidence_window") or "")
    timeline_items = [
        {
            key: item.get(key)
            for key in ("_id", "timestamp", "picture", "narration", "OST", "_segment_id")
        }
        for item in finalization.get("finalized_script") or []
        if isinstance(item, dict) and str(item.get("_segment_id") or "") == str(segment_id)
    ]
    evidence = {"subtitle_evidence": "", "visual_evidence": "", "highlight_candidates": ""}
    try:
        window = TimeRange.parse(time_range)
        evidence_values = FusionScriptPipeline().select_evidence_window(
            subtitle_evidence=str(request.get("subtitle_content") or ""),
            visual_evidence=str(request.get("visual_evidence") or ""),
            highlight_candidates=str(request.get("highlight_candidates") or ""),
            time_range=window,
        )
        evidence = dict(zip(evidence, evidence_values))
    except ValueError:
        pass
    return {
        "segment_id": str(segment_id),
        "time_range": time_range,
        "story_beat": story_beat,
        "plan_segment": segment,
        "timeline_items": timeline_items,
        **evidence,
    }


def locate_fusion_review_item(
    *, narrative_map: dict[str, Any], segment_id: str
) -> dict[str, str]:
    """Return the evidence-bounded source location used by a selected review item."""
    for beat in narrative_map.get("beats") or []:
        if isinstance(beat, dict) and str(beat.get("segment_id") or "") == str(segment_id):
            return {
                "segment_id": str(segment_id),
                "time_range": str(beat.get("evidence_window") or ""),
                "active_subject": str(beat.get("active_subject") or ""),
            }
    return {"segment_id": str(segment_id), "time_range": "", "active_subject": ""}


def compare_fusion_versions(
    *,
    versions: list[dict[str, Any]],
    baseline_version_id: str,
    candidate_version_id: str,
) -> dict[str, Any]:
    """Compare two saved review-context snapshots using script-line summaries."""
    versions_by_id = {
        str(item.get("version_id") or ""): item
        for item in versions
        if isinstance(item, dict)
    }
    baseline = versions_by_id.get(str(baseline_version_id))
    candidate = versions_by_id.get(str(candidate_version_id))
    if baseline is None or candidate is None:
        raise ValueError("Both selected Fusion versions must exist")
    baseline_summary = _fusion_version_summary(baseline)
    candidate_summary = _fusion_version_summary(candidate)
    changed_fields = [
        field
        for field in (
            "script",
            "renderable",
            "blocker_codes",
            "warning_codes",
            "quality_codes",
            "narrative_map_approval",
            "ost_ratio",
            "evidence_conflicts",
            "timeline_ranges",
        )
        if baseline_summary.get(field) != candidate_summary.get(field)
    ]
    return {
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "changed": bool(changed_fields),
        "changed_fields": changed_fields,
    }


def _fusion_version_summary(version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version.get("snapshot") if isinstance(version.get("snapshot"), dict) else {}
    preflight = snapshot.get("preflight") if isinstance(snapshot.get("preflight"), dict) else {}
    script = snapshot.get("finalized_script") if isinstance(snapshot.get("finalized_script"), list) else []
    quality = snapshot.get("narrative_quality_findings")
    quality = quality if isinstance(quality, list) else []
    narrative_map = snapshot.get("narrative_map") if isinstance(snapshot.get("narrative_map"), dict) else {}
    durations = []
    ost_duration = 0.0
    for item in script:
        if not isinstance(item, dict):
            continue
        try:
            time_range = TimeRange.parse(str(item.get("timestamp") or ""))
            duration = time_range.end_seconds - time_range.start_seconds
        except ValueError:
            continue
        durations.append(max(0.0, duration))
        if int(item.get("OST") or 0) == 1:
            ost_duration += max(0.0, duration)
    total_duration = sum(durations)
    conflicts = snapshot.get("evidence_conflicts")
    conflicts = conflicts if isinstance(conflicts, list) else []
    return {
        "version_id": str(version.get("version_id") or ""),
        "kind": str(version.get("kind") or ""),
        "created_at": version.get("created_at"),
        "script_item_count": len(script),
        "script": [
            (item.get("_id"), item.get("timestamp"), item.get("narration"))
            for item in script
            if isinstance(item, dict)
        ],
        "renderable": bool(snapshot.get("renderable")),
        "blocker_codes": sorted(
            str(item.get("code") or "")
            for item in preflight.get("blockers") or []
            if isinstance(item, dict)
        ),
        "warning_codes": sorted(
            str(item.get("code") or "")
            for item in preflight.get("warnings") or []
            if isinstance(item, dict)
        ),
        "quality_codes": sorted(
            str(item.get("code") or "")
            for item in quality
            if isinstance(item, dict)
        ),
        "narrative_map_approval": str(narrative_map.get("approval_status") or ""),
        "ost_ratio": round(ost_duration / total_duration, 4) if total_duration else 0.0,
        "evidence_conflicts": sorted(
            (
                str(item.get("severity") or ""),
                str(item.get("time_range") or ""),
                str(item.get("status") or ""),
            )
            for item in conflicts
            if isinstance(item, dict)
        ),
        "timeline_ranges": [
            (str(item.get("video_name") or ""), str(item.get("timestamp") or ""))
            for item in script
            if isinstance(item, dict)
        ],
    }

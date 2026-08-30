"""Single projection seam for the Film Vision Fusion creator workspace."""

from __future__ import annotations

from typing import Any


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
    }

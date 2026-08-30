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
        },
    }

"""Deterministic, creator-facing renderability decision for Film Vision Fusion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PreflightFinding:
    code: str
    message: str
    segment_id: str = ""


@dataclass(frozen=True, slots=True)
class RenderPreflight:
    blockers: tuple[PreflightFinding, ...]
    warnings: tuple[PreflightFinding, ...]
    passed: tuple[PreflightFinding, ...]

    def can_render(self, warning_override_reason: str = "") -> bool:
        return not self.blockers and (
            not self.warnings or bool(str(warning_override_reason).strip())
        )

    def to_dict(self, warning_override_reason: str = "") -> dict[str, Any]:
        reason = str(warning_override_reason or "").strip()
        return {
            "blockers": [asdict(item) for item in self.blockers],
            "warnings": [asdict(item) for item in self.warnings],
            "passed": [asdict(item) for item in self.passed],
            "warning_override_reason": reason,
            "renderable": self.can_render(reason),
        }


def build_render_preflight(
    *,
    continuity_report: dict[str, Any] | None,
    evidence_conflicts: list[dict[str, Any]] | None,
    segment_matches: list[dict[str, Any]] | None = None,
) -> RenderPreflight:
    """Classify Fusion safety signals once, before the render action is exposed."""
    blockers: list[PreflightFinding] = []
    warnings: list[PreflightFinding] = []
    passed: list[PreflightFinding] = []
    report = continuity_report or {}
    if not bool(report.get("is_renderable")):
        blockers.append(
            PreflightFinding("continuity_not_renderable", "Segment continuity still requires review.")
        )
    else:
        passed.append(PreflightFinding("continuity_checked", "Segment continuity passed."))

    for conflict in evidence_conflicts or []:
        if not isinstance(conflict, dict) or conflict.get("status") != "unresolved":
            continue
        severity = str(conflict.get("severity") or "medium").lower()
        if severity in {"high", "critical"}:
            blockers.append(
                PreflightFinding(
                    "unresolved_high_severity_conflict",
                    "A high-severity Evidence Conflict must be resolved before rendering.",
                )
            )
        else:
            warnings.append(
                PreflightFinding(
                    "unresolved_evidence_conflict",
                    "An unresolved Evidence Conflict needs a creator override reason.",
                )
            )

    for segment in segment_matches or []:
        if not isinstance(segment, dict):
            continue
        status = str(segment.get("status") or "missing")
        segment_id = str(segment.get("segment_id") or "")
        if status in {"failed", "missing", "malformed", "core_window_invalid"}:
            blockers.append(
                PreflightFinding(
                    "segment_match_failed",
                    f"Segment Match {segment_id or '<unknown>'} is {status}.",
                    segment_id,
                )
            )
    if not blockers and not warnings:
        passed.append(PreflightFinding("evidence_conflicts_checked", "No unresolved render-risk conflicts."))
    return RenderPreflight(tuple(blockers), tuple(warnings), tuple(passed))

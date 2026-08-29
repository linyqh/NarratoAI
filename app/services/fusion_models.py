"""Domain values shared by Film Vision Fusion orchestration and finalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.documentary.frame_analysis_models import TimeRange


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    """A validated disagreement between subtitle and visual evidence."""

    video_name: str
    time_range: TimeRange
    subtitle_claim: str
    visual_observation: str
    severity: str
    source_video_identity: dict[str, Any] | None
    status: str = "unresolved"
    source_identity_status: str = "verified"
    related_script_item_ids: tuple[Any, ...] = ()
    related_candidate_ids: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "EvidenceConflict":
        if not isinstance(payload, dict):
            raise ValueError("evidence conflict must be an object")
        video_name = str(payload.get("video_name") or "").strip()
        subtitle_claim = str(payload.get("subtitle_claim") or "").strip()
        visual_observation = str(payload.get("visual_observation") or "").strip()
        severity = str(payload.get("severity") or "").strip().lower()
        if not video_name:
            raise ValueError("evidence conflict requires video_name")
        if not subtitle_claim:
            raise ValueError("evidence conflict requires subtitle_claim")
        if not visual_observation:
            raise ValueError("evidence conflict requires visual_observation")
        if severity not in {"low", "medium", "high"}:
            raise ValueError("evidence conflict severity must be low, medium, or high")
        source_identity = payload.get("source_video_identity")
        verified_identity = source_identity if isinstance(source_identity, dict) else None
        return cls(
            video_name=video_name,
            time_range=TimeRange.parse(str(payload.get("time_range") or "")),
            subtitle_claim=subtitle_claim,
            visual_observation=visual_observation,
            severity=severity,
            source_video_identity=verified_identity,
            status="unresolved",
            source_identity_status="verified" if verified_identity is not None else "unverified_legacy",
            related_script_item_ids=tuple(payload.get("related_script_item_ids") or ()),
            related_candidate_ids=tuple(
                str(item) for item in (payload.get("related_candidate_ids") or ())
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_name": self.video_name,
            "time_range": str(self.time_range),
            "subtitle_claim": self.subtitle_claim,
            "visual_observation": self.visual_observation,
            "severity": self.severity,
            "status": self.status,
            "source_video_identity": self.source_video_identity,
            "source_identity_status": self.source_identity_status,
            "related_script_item_ids": list(self.related_script_item_ids),
            "related_candidate_ids": list(self.related_candidate_ids),
        }

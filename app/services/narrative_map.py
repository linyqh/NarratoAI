"""Evidence-bounded Narrative Map and deterministic review suggestions for Fusion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from app.services.documentary.frame_analysis_models import TimeRange


@dataclass(frozen=True, slots=True)
class NarrativeMapBeat:
    segment_id: str
    sentence_start: int
    sentence_end: int
    evidence_window: str
    active_subject: str
    entering_state: str
    immediate_pressure: str
    trigger_event: str
    exiting_state: str
    next_risk_or_choice: str
    temporal_or_location_transition: str
    bridge_to_next: bool


@dataclass(frozen=True, slots=True)
class NarrativeQualityFinding:
    code: str
    segment_id: str
    message: str
    severity: str = "suggestion"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def build_narrative_map(
    *,
    approved_narration: str,
    plan_payload: dict[str, Any],
    subtitle_evidence: str,
    visual_evidence: str,
) -> dict[str, Any]:
    """Project an approved Segment Plan into a cached artifact without adding facts."""
    if not str(approved_narration or "").strip():
        raise ValueError("Narrative Map requires approved narration")
    if not str(subtitle_evidence or "").strip() and not str(visual_evidence or "").strip():
        raise ValueError("Narrative Map requires Subtitle Evidence or Visual Evidence")
    segments = plan_payload.get("segments") if isinstance(plan_payload, dict) else None
    if not isinstance(segments, list) or not segments:
        raise ValueError("Narrative Map requires an approved Fusion Segment Plan")
    beats: list[NarrativeMapBeat] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError("Narrative Map segments must be objects")
        evidence_window = str(segment.get("core_window") or segment.get("timestamp") or "")
        TimeRange.parse(evidence_window)
        beats.append(
            NarrativeMapBeat(
                segment_id=str(segment.get("segment_id") or f"segment-{index}"),
                sentence_start=int(segment.get("sentence_start") or 0),
                sentence_end=int(segment.get("sentence_end") or 0),
                evidence_window=evidence_window,
                active_subject=str(segment.get("active_subject") or ""),
                entering_state=str(segment.get("entering_state") or ""),
                immediate_pressure=str(segment.get("intent") or segment.get("entering_state") or ""),
                trigger_event=str(segment.get("trigger_event") or ""),
                exiting_state=str(segment.get("exiting_state") or ""),
                next_risk_or_choice=str(segment.get("transition") or segment.get("exiting_state") or ""),
                temporal_or_location_transition=str(segment.get("narrative_mode") or "linear"),
                bridge_to_next=bool(segment.get("bridge_to_next")),
            )
        )
    signature_input = "\n".join(
        [str(approved_narration), str(subtitle_evidence), str(visual_evidence), repr(plan_payload)]
    )
    return {
        "artifact_type": "Narrative Map",
        "signature": hashlib.sha256(signature_input.encode("utf-8")).hexdigest(),
        "approval_status": "pending",
        "beats": [asdict(beat) for beat in beats],
    }


def evaluate_narrative_quality(
    narrative_map: dict[str, Any], matched_items: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Produce review suggestions only; never change approved narration or clips."""
    findings: list[NarrativeQualityFinding] = []
    beats = narrative_map.get("beats") if isinstance(narrative_map, dict) else []
    previous = None
    for beat in beats or []:
        if not isinstance(beat, dict):
            continue
        segment_id = str(beat.get("segment_id") or "")
        if not str(beat.get("trigger_event") or "").strip() or not str(beat.get("exiting_state") or "").strip():
            findings.append(NarrativeQualityFinding("missing_causal_bridge", segment_id, "Story Beat is missing a trigger or resulting change."))
        if previous and str(previous.get("active_subject") or "").strip() != str(beat.get("active_subject") or "").strip() and not bool(previous.get("bridge_to_next")):
            findings.append(NarrativeQualityFinding("unstable_subject_handoff", segment_id, "Active subject changes without a Narrative Bridge."))
        previous = beat

    normalized_previous = ""
    for item in matched_items or []:
        narration = re.sub(r"\s+", "", str(item.get("narration") or ""))
        if narration and narration == normalized_previous:
            findings.append(NarrativeQualityFinding("repetitive_narration", str(item.get("_segment_id") or ""), "Adjacent narration is repeated."))
        normalized_previous = narration
    return [finding.to_dict() for finding in findings]

"""Evidence-bounded Narrative Map and deterministic review suggestions for Fusion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
import time
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
        if previous:
            previous_window = TimeRange.parse(str(previous.get("evidence_window") or ""))
            current_window = TimeRange.parse(str(beat.get("evidence_window") or ""))
            if current_window.start_seconds - previous_window.end_seconds > 150 and not bool(previous.get("bridge_to_next")):
                findings.append(NarrativeQualityFinding("unexplained_temporal_jump", segment_id, "Story Beat jumps forward in source time without a Narrative Bridge."))
        previous = beat

    normalized_previous = ""
    beats_by_id = {
        str(beat.get("segment_id") or ""): beat
        for beat in beats or []
        if isinstance(beat, dict)
    }
    for item in matched_items or []:
        narration = re.sub(r"\s+", "", str(item.get("narration") or ""))
        segment_id = str(item.get("_segment_id") or "")
        active_subject = str(
            (beats_by_id.get(segment_id) or {}).get("active_subject") or ""
        ).strip()
        if (
            not active_subject
            and re.search(r"(?:他|她|他们|她们|这人|此人|对方)", narration)
        ):
            findings.append(
                NarrativeQualityFinding(
                    "ambiguous_character_reference",
                    segment_id,
                    "Narration uses a character reference without an active subject in its Story Beat.",
                )
            )
        if narration and narration == normalized_previous:
            findings.append(NarrativeQualityFinding("repetitive_narration", segment_id, "Adjacent narration is repeated."))
        normalized_previous = narration
        try:
            window = TimeRange.parse(str(item.get("timestamp") or ""))
            characters_per_second = len(narration) / max(0.1, window.end_seconds - window.start_seconds)
            if narration and characters_per_second > 14:
                findings.append(NarrativeQualityFinding("narration_density_high", segment_id, "Narration density may be too high for comfortable viewing."))
        except ValueError:
            continue
        if int(item.get("OST") or 0) == 1 and not segment_id:
            findings.append(NarrativeQualityFinding("highlight_story_relevance_unknown", "", "Original-sound highlight is not linked to a Story Beat."))
    return [finding.to_dict() for finding in findings]


def review_narrative_map(
    artifact: dict[str, Any], *, action: str, edited_beats: list[dict[str, Any]] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a creator review decision without allowing evidence windows to drift."""
    if action not in {"approved", "skipped", "applied_draft"}:
        raise ValueError("Narrative Map review action must be approved, skipped, or applied_draft")
    updated = dict(artifact or {})
    original_beats = list(updated.get("beats") or [])
    proposed_beats = list(edited_beats) if edited_beats is not None else original_beats
    original_by_id = {str(beat.get("segment_id") or ""): beat for beat in original_beats if isinstance(beat, dict)}
    if len(proposed_beats) != len(original_by_id):
        raise ValueError("Narrative Map edits cannot add or remove Story Beats")
    for beat in proposed_beats:
        if not isinstance(beat, dict) or str(beat.get("segment_id") or "") not in original_by_id:
            raise ValueError("Narrative Map edit refers to an unknown Story Beat")
        original = original_by_id[str(beat["segment_id"])]
        if str(beat.get("evidence_window") or "") != str(original.get("evidence_window") or ""):
            raise ValueError("Narrative Map edits cannot expand an Evidence Window")
    invalidation = preview_narrative_map_invalidation(original_beats, proposed_beats)
    updated["beats"] = proposed_beats
    updated["approval_status"] = action
    updated["reviewed_at"] = time.time()
    return updated, invalidation


def preview_narrative_map_invalidation(
    original_beats: list[dict[str, Any]], proposed_beats: list[dict[str, Any]]
) -> dict[str, Any]:
    """Report only changed Story Beats and their existing match dependencies."""
    original_by_id = {str(beat.get("segment_id") or ""): beat for beat in original_beats if isinstance(beat, dict)}
    changed = [
        str(beat.get("segment_id") or "")
        for beat in proposed_beats
        if isinstance(beat, dict) and beat != original_by_id.get(str(beat.get("segment_id") or ""))
    ]
    return {
        "changed_story_beats": changed,
        "invalidates_segment_matches": changed,
        "retains_visual_evidence": True,
        "requires_creator_confirmation": bool(changed),
    }

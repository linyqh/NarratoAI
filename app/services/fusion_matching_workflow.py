"""High-level orchestration seam for one approved Fusion Matching Task."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.documentary.frame_analysis_models import TimeRange
from app.services.fusion_script_pipeline import (
    ContinuityFinding,
    ContinuityReport,
    FusionScriptPipeline,
    SegmentMatchRequest,
)


@dataclass(frozen=True, slots=True)
class FusionMatchingInput:
    narration_copy: str
    plan_payload: dict[str, Any]
    subtitle_evidence: str
    visual_evidence: str
    highlight_candidates: str


class FusionTextAdapter(Protocol):
    def match_segment(self, request: SegmentMatchRequest) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ContinuityRepairRequest:
    affected_segment_id: str
    previous_segment_id: str
    next_segment_id: str
    core_window: TimeRange
    narration: str
    subtitle_evidence: str
    visual_evidence: str
    highlight_candidates: str


@dataclass(frozen=True, slots=True)
class FusionMatchingSnapshot:
    plan_payload: dict[str, Any]
    completed_segment_results: dict[str, dict[str, Any]]
    attempts_by_segment: dict[str, int]
    repair_attempts_by_segment: dict[str, int]


@dataclass(frozen=True, slots=True)
class FusionMatchingResult:
    items: list[dict[str, Any]]
    evidence_conflicts: list[dict[str, Any]]
    continuity_report: ContinuityReport
    snapshot: FusionMatchingSnapshot
    repaired_segment_ids: tuple[str, ...] = ()
    attempts_by_segment: dict[str, int] = field(default_factory=dict)
    repair_attempts_by_segment: dict[str, int] = field(default_factory=dict)

    @property
    def renderable(self) -> bool:
        return self.continuity_report.is_renderable


class FusionMatchingWorkflow:
    """Own matching and post-merge Continuity Gate evaluation behind one interface."""

    def execute(
        self,
        request: FusionMatchingInput,
        text_adapter: FusionTextAdapter,
        *,
        resume_from: FusionMatchingSnapshot | None = None,
        retry_count: int = 1,
        max_concurrency: int = 2,
        on_segment_started=None,
        on_segment_complete=None,
        on_segment_failed=None,
        on_segment_attempt=None,
        on_repair_attempt=None,
        is_cancelled=None,
    ) -> FusionMatchingResult:
        pipeline = FusionScriptPipeline()
        invalidated = self._invalidated_segment_ids(
            resume_from.plan_payload if resume_from else None,
            request.plan_payload,
        )
        completed_responses = {
            segment_id: deepcopy(response)
            for segment_id, response in (
                resume_from.completed_segment_results.items() if resume_from else []
            )
            if segment_id not in invalidated
        }
        attempts_by_segment = dict(resume_from.attempts_by_segment) if resume_from else {}
        repair_attempts_by_segment = (
            dict(resume_from.repair_attempts_by_segment) if resume_from else {}
        )
        plan_report = pipeline.validate_continuity(
            request.narration_copy, request.plan_payload
        )
        if not plan_report.is_renderable:
            return FusionMatchingResult(
                items=[],
                evidence_conflicts=[],
                continuity_report=plan_report,
                snapshot=FusionMatchingSnapshot(
                    plan_payload=deepcopy(request.plan_payload),
                    completed_segment_results=deepcopy(completed_responses),
                    attempts_by_segment=attempts_by_segment,
                    repair_attempts_by_segment=repair_attempts_by_segment,
                ),
            )

        def match_segment(segment_request: SegmentMatchRequest) -> dict[str, Any]:
            attempts_by_segment[segment_request.segment_id] = (
                attempts_by_segment.get(segment_request.segment_id, 0) + 1
            )
            if on_segment_attempt:
                on_segment_attempt(
                    segment_request, attempts_by_segment[segment_request.segment_id]
                )
            response = self._with_segment_id(
                text_adapter.match_segment(segment_request), segment_request.segment_id
            )
            completed_responses[segment_request.segment_id] = response
            return response

        matched = pipeline.match_approved_plan(
            narration_copy=request.narration_copy,
            plan_payload=request.plan_payload,
            subtitle_evidence=request.subtitle_evidence,
            visual_evidence=request.visual_evidence,
            highlight_candidates=request.highlight_candidates,
            matcher=match_segment,
            completed_segment_results=completed_responses,
            retry_count=retry_count,
            max_concurrency=max_concurrency,
            on_segment_started=on_segment_started,
            on_segment_complete=on_segment_complete,
            on_segment_failed=on_segment_failed,
            is_cancelled=is_cancelled,
        )
        report = self._evaluate_merged_continuity(matched)
        repaired_segment_ids: tuple[str, ...] = ()
        gap = next(iter(self._unbridged_large_gaps(matched.items)), None)
        repair_transition = getattr(text_adapter, "repair_transition", None)
        if gap and callable(repair_transition):
            previous, current, _jump = gap
            affected_segment_id = str(previous.get("_segment_id") or "")
            affected_request = next(
                item for item in matched.requests
                if item.segment_id == affected_segment_id
            )
            affected_window = TimeRange.parse(affected_request.core_window)
            subtitles, visuals, candidates = pipeline.select_evidence_window(
                subtitle_evidence=request.subtitle_evidence,
                visual_evidence=request.visual_evidence,
                highlight_candidates=request.highlight_candidates,
                time_range=affected_window,
            )
            repair_request = ContinuityRepairRequest(
                affected_segment_id=affected_segment_id,
                previous_segment_id=affected_segment_id,
                next_segment_id=str(current.get("_segment_id") or ""),
                core_window=affected_window,
                narration=affected_request.narration,
                subtitle_evidence=subtitles,
                visual_evidence=visuals,
                highlight_candidates=candidates,
            )
            repair_attempts_by_segment[affected_segment_id] = 1
            if on_repair_attempt:
                on_repair_attempt(repair_request, 1)
            try:
                completed_responses[affected_segment_id] = self._with_segment_id(
                    repair_transition(repair_request), affected_segment_id
                )
                matched = pipeline.match_approved_plan(
                    narration_copy=request.narration_copy,
                    plan_payload=request.plan_payload,
                    subtitle_evidence=request.subtitle_evidence,
                    visual_evidence=request.visual_evidence,
                    highlight_candidates=request.highlight_candidates,
                    matcher=match_segment,
                    completed_segment_results=completed_responses,
                    retry_count=retry_count,
                    max_concurrency=max_concurrency,
                    on_segment_started=on_segment_started,
                    on_segment_complete=on_segment_complete,
                    on_segment_failed=on_segment_failed,
                    is_cancelled=is_cancelled,
                )
                report = self._evaluate_merged_continuity(matched)
                repaired_segment_ids = (affected_segment_id,)
            except Exception as exc:
                report = ContinuityReport(
                    report.findings
                    + (
                        ContinuityFinding(
                            "continuity_repair_failed",
                            affected_segment_id,
                            f"targeted continuity repair failed: {exc}",
                            str(current.get("_segment_id") or ""),
                        ),
                    )
                )

        return FusionMatchingResult(
            items=matched.items,
            evidence_conflicts=matched.evidence_conflicts,
            continuity_report=report,
            snapshot=FusionMatchingSnapshot(
                plan_payload=deepcopy(request.plan_payload),
                completed_segment_results=deepcopy(completed_responses),
                attempts_by_segment=dict(attempts_by_segment),
                repair_attempts_by_segment=dict(repair_attempts_by_segment),
            ),
            repaired_segment_ids=repaired_segment_ids,
            attempts_by_segment=attempts_by_segment,
            repair_attempts_by_segment=repair_attempts_by_segment,
        )

    @staticmethod
    def _invalidated_segment_ids(
        previous_plan: dict[str, Any] | None,
        current_plan: dict[str, Any],
    ) -> set[str]:
        if not previous_plan:
            return set()
        previous_segments = [
            segment
            for segment in previous_plan.get("segments", [])
            if isinstance(segment, dict)
        ]
        current_segments = [
            segment
            for segment in current_plan.get("segments", [])
            if isinstance(segment, dict)
        ]
        previous_by_id = {
            str(segment.get("segment_id") or ""): (index, segment)
            for index, segment in enumerate(previous_segments)
        }
        changed_indexes = set()
        for index, segment in enumerate(current_segments):
            segment_id = str(segment.get("segment_id") or "")
            previous = previous_by_id.get(segment_id)
            if previous is None or previous[0] != index or previous[1] != segment:
                changed_indexes.add(index)
        affected_indexes = {
            neighbor
            for index in changed_indexes
            for neighbor in (index - 1, index, index + 1)
            if 0 <= neighbor < len(current_segments)
        }
        return {
            str(current_segments[index].get("segment_id") or "")
            for index in affected_indexes
        }

    @staticmethod
    def _with_segment_id(response: dict[str, Any], segment_id: str) -> dict[str, Any]:
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            return response
        return {
            **response,
            "items": [
                {**item, "_segment_id": segment_id} if isinstance(item, dict) else item
                for item in response["items"]
            ],
        }

    def _evaluate_merged_continuity(self, matched) -> ContinuityReport:
        findings = list(matched.continuity_report.findings)
        for previous, current, jump in self._unbridged_large_gaps(matched.items):
            findings.append(
                ContinuityFinding(
                    code="unbridged_merged_source_jump",
                    segment_id=str(current.get("_segment_id") or ""),
                    previous_segment_id=str(previous.get("_segment_id") or ""),
                    message=(
                        f"merged Segment Matches jump {round(jump, 3)} seconds "
                        "without a Narrative Bridge"
                    ),
                )
            )
        return ContinuityReport(tuple(findings))

    def _unbridged_large_gaps(self, items):
        for previous, current in zip(items, items[1:]):
            previous_window = TimeRange.parse(str(previous.get("timestamp") or ""))
            current_window = TimeRange.parse(str(current.get("timestamp") or ""))
            if (
                current_window.start_seconds - previous_window.end_seconds
                > FusionScriptPipeline.MAX_UNMARKED_FORWARD_JUMP_SECONDS
                and not self._is_narrative_bridge(previous)
                and not self._is_narrative_bridge(current)
            ):
                yield previous, current, current_window.start_seconds - previous_window.end_seconds

    @staticmethod
    def _is_narrative_bridge(item: dict[str, Any]) -> bool:
        return (
            str(item.get("narrative_role") or "").strip().lower() == "bridge"
            and int(item.get("OST") or 0) == 0
            and bool(str(item.get("narration") or "").strip())
        )

"""Two-stage orchestration for bounded Film Vision Fusion matching."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import re
import time
from typing import Any, Callable

from app.services.documentary.frame_analysis_models import TimeRange


_TIME_RANGE = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*(?:-->|-)\s*(\d{2}:\d{2}:\d{2},\d{3})")
_VISUAL_BLOCK = re.compile(r"(?ms)^##\s+(?P<range>\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3})\s*\n(?P<body>.*?)(?=^##\s+|\Z)")


def is_retryable_fusion_request_error(error: Exception) -> bool:
    """Return whether the one permitted Fusion retry can plausibly recover."""
    message = str(error).lower()
    if any(
        marker in message
        for marker in (
            "authentication", "api key", "configuration", "invalid parameter",
            "请求错误", "content filter",
        )
    ):
        return False
    return any(
        marker in message
        for marker in (
            "timeout", "timed out", "connection", "temporary", "unavailable",
            "rate limit", "429", "500", "502", "503", "504",
        )
    )


def call_fusion_request_with_retry(call, *, retry_count: int = 1, on_retry=None):
    """Run a Fusion request with bounded retries for recoverable provider failures."""
    attempts = max(0, int(retry_count)) + 1
    last_error = None
    for attempt_index in range(attempts):
        try:
            return call()
        except Exception as error:
            last_error = error
            if attempt_index >= attempts - 1 or not is_retryable_fusion_request_error(error):
                raise
            if on_retry:
                on_retry(error)
            time.sleep(1.0)
    raise RuntimeError("Fusion request exhausted retries") from last_error


@dataclass(frozen=True, slots=True)
class FusionPlanSegment:
    segment_id: str
    sentence_start: int
    sentence_end: int
    core_window: TimeRange
    story_role: str = ""
    intent: str = ""
    transition: str = ""
    active_subject: str = ""
    entering_state: str = ""
    trigger_event: str = ""
    exiting_state: str = ""
    bridge_to_next: bool = False
    bridge_reason: str = ""
    narrative_mode: str = "linear"
    narration_cue: str = ""
    handoff_from_previous: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SegmentMatchRequest:
    segment_id: str
    narration: str
    core_window: str
    context_window: str
    story_role: str
    intent: str
    transition: str
    subtitle_evidence: str
    visual_evidence: str
    highlight_candidates: str


@dataclass(frozen=True, slots=True)
class FusionScriptPipelineResult:
    items: list[dict[str, Any]]
    evidence_conflicts: list[dict[str, Any]]
    requests: list[SegmentMatchRequest]
    continuity_report: ContinuityReport


@dataclass(frozen=True, slots=True)
class ContinuityFinding:
    code: str
    segment_id: str
    message: str
    previous_segment_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "segment_id": self.segment_id,
            "previous_segment_id": self.previous_segment_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ContinuityReport:
    findings: tuple[ContinuityFinding, ...]

    @property
    def is_renderable(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_renderable": self.is_renderable,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class FusionScriptPipeline:
    """Match an approved plan through local evidence windows, not full-film prompts."""

    MAX_UNMARKED_FORWARD_JUMP_SECONDS = 150.0
    NONLINEAR_MODES = frozenset({"flashback", "flashforward", "montage", "recap"})

    def match_approved_plan(
        self,
        *,
        narration_copy: str,
        plan_payload: dict[str, Any],
        subtitle_evidence: str,
        visual_evidence: str,
        highlight_candidates: str,
        matcher: Callable[[SegmentMatchRequest], dict[str, Any]],
        context_margin_seconds: float = 15.0,
        retry_count: int = 1,
        max_concurrency: int = 2,
        completed_segment_results: dict[str, dict[str, Any]] | None = None,
        on_segment_started: Callable[[SegmentMatchRequest], None] | None = None,
        on_segment_complete: Callable[[SegmentMatchRequest, dict[str, Any]], None] | None = None,
        on_segment_failed: Callable[[SegmentMatchRequest, Exception], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> FusionScriptPipelineResult:
        sentences = self._sentences(narration_copy)
        plan = self._parse_plan(plan_payload, len(sentences))
        continuity_report = self.validate_continuity(narration_copy, plan_payload)
        if not continuity_report.is_renderable:
            codes = ", ".join(finding.code for finding in continuity_report.findings)
            raise ValueError(f"Fusion Segment Plan requires Narrative Bridges: {codes}")
        requests = [
            self._request_for_segment(
                segment,
                sentences,
                subtitle_evidence,
                visual_evidence,
                highlight_candidates,
                context_margin_seconds,
            )
            for segment in plan
        ]

        responses = dict(completed_segment_results or {})
        pending_requests = [request for request in requests if request.segment_id not in responses]
        self._match_pending_requests(
            pending_requests,
            responses,
            matcher,
            retry_count,
            max_concurrency,
            on_segment_started,
            on_segment_complete,
            on_segment_failed,
            is_cancelled,
        )

        merged_items: list[dict[str, Any]] = []
        merged_conflicts: list[dict[str, Any]] = []
        for request in requests:
            response = responses[request.segment_id]
            items = response.get("items") if isinstance(response, dict) else None
            if not isinstance(items, list) or not items:
                raise ValueError(f"segment {request.segment_id} returned no script items")
            self._validate_items_within_core_window(items, request)
            self._validate_highlight_quota(items, request)
            merged_items.extend(item for item in items if isinstance(item, dict))
            conflicts = response.get("evidence_conflicts", []) if isinstance(response, dict) else []
            merged_conflicts.extend(item for item in conflicts if isinstance(item, dict))

        normalized_items = [
            {**item, "_id": index}
            for index, item in enumerate(merged_items, start=1)
        ]
        return FusionScriptPipelineResult(
            normalized_items,
            merged_conflicts,
            requests,
            continuity_report,
        )

    def validate_plan(self, narration_copy: str, plan_payload: dict[str, Any]) -> list[FusionPlanSegment]:
        """Validate a creator-edited plan before it can be approved."""
        return self._parse_plan(plan_payload, len(self._sentences(narration_copy)))

    def select_evidence_window(
        self,
        *,
        subtitle_evidence: str,
        visual_evidence: str,
        highlight_candidates: str,
        time_range: TimeRange,
    ) -> tuple[str, str, str]:
        """Select only evidence overlapping one affected source-time range."""
        return (
            self._filter_subtitles(
                subtitle_evidence, time_range.start_seconds, time_range.end_seconds
            ),
            self._filter_visual_evidence(
                visual_evidence, time_range.start_seconds, time_range.end_seconds
            ),
            self._filter_candidates(
                highlight_candidates, time_range.start_seconds, time_range.end_seconds
            ),
        )

    def validate_continuity(self, narration_copy: str, plan_payload: dict[str, Any]) -> ContinuityReport:
        """Return deterministic continuity findings for a creator-approved plan."""
        plan = self._parse_plan(plan_payload, len(self._sentences(narration_copy)))
        findings: list[ContinuityFinding] = []
        for segment in plan:
            missing_fields = [
                field_name
                for field_name, value in (
                    ("active_subject", segment.active_subject),
                    ("entering_state", segment.entering_state),
                    ("trigger_event", segment.trigger_event),
                    ("exiting_state", segment.exiting_state),
                )
                if not value.strip()
            ]
            if missing_fields:
                findings.append(
                    ContinuityFinding(
                        "incomplete_story_beat",
                        segment.segment_id,
                        "Story Beat is missing: " + ", ".join(missing_fields),
                    )
                )
        for previous, current in zip(plan, plan[1:]):
            required_handoff_dimensions = {"actor", "place", "goal", "cause", "state"}
            supplied_handoff_dimensions = {
                dimension for dimension, _status in current.handoff_from_previous
            }
            disconnected_dimensions = [
                dimension
                for dimension, status in current.handoff_from_previous
                if status in {"changed", "disconnected", "missing", "unknown"}
            ]
            disconnected_dimensions.extend(
                sorted(required_handoff_dimensions - supplied_handoff_dimensions)
            )
            if disconnected_dimensions and not self._has_narrative_bridge(previous):
                findings.append(
                    ContinuityFinding(
                        "unbridged_semantic_handoff",
                        current.segment_id,
                        "Story Beat handoff is disconnected for: "
                        + ", ".join(disconnected_dimensions),
                        previous.segment_id,
                    )
                )
            if (
                previous.active_subject.strip() != current.active_subject.strip()
                and not self._has_narrative_bridge(previous)
            ):
                findings.append(
                    ContinuityFinding(
                        "unbridged_active_subject_change",
                        current.segment_id,
                        "active subject changes without a Narrative Bridge",
                        previous.segment_id,
                    )
                )
            if current.core_window.start_seconds < previous.core_window.end_seconds:
                if not self._is_marked_nonlinear(current):
                    findings.append(
                        ContinuityFinding(
                            "unmarked_nonlinear_transition",
                            current.segment_id,
                            "source time moves backward without a nonlinear narrative cue",
                            previous.segment_id,
                        )
                    )
                continue
            jump = current.core_window.start_seconds - previous.core_window.end_seconds
            if jump > self.MAX_UNMARKED_FORWARD_JUMP_SECONDS and not self._has_narrative_bridge(previous):
                findings.append(
                    ContinuityFinding(
                        "unmarked_large_forward_jump",
                        current.segment_id,
                        f"source-time jump is {round(jump, 3)} seconds without a Narrative Bridge",
                        previous.segment_id,
                    )
                )
        return ContinuityReport(tuple(findings))

    def _parse_plan(self, payload: dict[str, Any], sentence_count: int) -> list[FusionPlanSegment]:
        segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(segments, list) or not segments:
            raise ValueError("Fusion Segment Plan requires segments")
        parsed: list[FusionPlanSegment] = []
        segment_ids: set[str] = set()
        expected_sentence_start = 1
        for index, item in enumerate(segments, start=1):
            if not isinstance(item, dict):
                raise ValueError("Fusion Segment Plan segments must be objects")
            sentence_start = int(item.get("sentence_start", 0))
            sentence_end = int(item.get("sentence_end", 0))
            if sentence_start != expected_sentence_start or sentence_end < sentence_start:
                raise ValueError("Fusion Segment Plan must cover narration sentences in order")
            sentence_span = sentence_end - sentence_start + 1
            if not 3 <= sentence_span <= 8 and not str(item.get("exception_reason") or "").strip():
                raise ValueError(
                    "Fusion Segment Plan segments outside 3-8 sentences require an exception_reason"
                )
            core_window = TimeRange.parse(str(item.get("core_window") or item.get("timestamp") or ""))
            if any(
                self._overlaps(
                    core_window.start_seconds,
                    core_window.end_seconds,
                    existing.core_window.start_seconds,
                    existing.core_window.end_seconds,
                )
                for existing in parsed
            ):
                raise ValueError("Fusion Segment Plan core windows must not overlap")
            segment_id = str(item.get("segment_id") or f"segment-{index}")
            if segment_id in segment_ids:
                raise ValueError("Fusion Segment Plan segment IDs must be unique")
            segment_ids.add(segment_id)
            parsed.append(
                FusionPlanSegment(
                    segment_id=segment_id,
                    sentence_start=sentence_start,
                    sentence_end=sentence_end,
                    core_window=core_window,
                    story_role=str(item.get("story_role") or ""),
                    intent=str(item.get("intent") or ""),
                    transition=str(item.get("transition") or ""),
                    active_subject=str(item.get("active_subject") or ""),
                    entering_state=str(item.get("entering_state") or ""),
                    trigger_event=str(item.get("trigger_event") or ""),
                    exiting_state=str(item.get("exiting_state") or ""),
                    bridge_to_next=bool(item.get("bridge_to_next", False)),
                    bridge_reason=str(item.get("bridge_reason") or ""),
                    narrative_mode=str(item.get("narrative_mode") or "linear").lower(),
                    narration_cue=str(item.get("narration_cue") or ""),
                    handoff_from_previous=tuple(
                        sorted(
                            (
                                str(key),
                                (
                                    str(value).strip().lower()
                                    if str(value).strip().lower() in {"continuous", "changed"}
                                    else "unknown"
                                ),
                            )
                            for key, value in (
                                item.get("handoff_from_previous", {}).items()
                                if isinstance(item.get("handoff_from_previous"), dict)
                                else ()
                            )
                        )
                    ),
                )
            )
            expected_sentence_start = sentence_end + 1
        if expected_sentence_start != sentence_count + 1:
            raise ValueError("Fusion Segment Plan must cover every narration sentence")
        return parsed

    def _is_marked_nonlinear(self, segment: FusionPlanSegment) -> bool:
        return (
            segment.narrative_mode in self.NONLINEAR_MODES
            and bool(segment.narration_cue.strip())
        )

    @staticmethod
    def _has_narrative_bridge(segment: FusionPlanSegment) -> bool:
        return segment.bridge_to_next and bool(segment.bridge_reason.strip())

    def _request_for_segment(
        self,
        segment: FusionPlanSegment,
        sentences: list[str],
        subtitles: str,
        visual_evidence: str,
        candidates: str,
        context_margin_seconds: float,
    ) -> SegmentMatchRequest:
        context_start = max(0.0, segment.core_window.start_seconds - max(0.0, context_margin_seconds))
        context_end = segment.core_window.end_seconds + max(0.0, context_margin_seconds)
        return SegmentMatchRequest(
            segment_id=segment.segment_id,
            narration="".join(sentences[segment.sentence_start - 1 : segment.sentence_end]),
            core_window=str(segment.core_window),
            context_window=self._format_range(context_start, context_end),
            story_role=segment.story_role,
            intent=segment.intent,
            transition=segment.transition,
            subtitle_evidence=self._filter_subtitles(subtitles, context_start, context_end),
            visual_evidence=self._filter_visual_evidence(visual_evidence, context_start, context_end),
            highlight_candidates=self._filter_candidates(candidates, context_start, context_end),
        )

    @staticmethod
    def _sentences(narration_copy: str) -> list[str]:
        sentences = [sentence.strip() for sentence in re.findall(r"[^。！？!?…]+[。！？!?…]*", str(narration_copy or ""))]
        sentences = [sentence for sentence in sentences if sentence]
        if not sentences:
            raise ValueError("approved narration copy must contain sentences")
        return sentences

    def _call_with_retry(self, request, matcher, retry_count):
        try:
            return call_fusion_request_with_retry(
                lambda: matcher(request), retry_count=retry_count
            )
        except Exception as error:
            raise RuntimeError(
                f"segment {request.segment_id} failed after retry: {error}"
            ) from error

    def _match_pending_requests(
        self,
        requests,
        responses,
        matcher,
        retry_count,
        max_concurrency,
        on_segment_started,
        on_segment_complete,
        on_segment_failed,
        is_cancelled,
    ) -> None:
        if not requests:
            return
        worker_count = max(1, int(max_concurrency))
        request_iter = iter(requests)
        futures = {}
        first_error: Exception | None = None
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="fusion-match") as executor:
            def submit_next() -> bool:
                if is_cancelled and is_cancelled():
                    return False
                try:
                    request = next(request_iter)
                except StopIteration:
                    return False
                if on_segment_started:
                    on_segment_started(request)
                futures[executor.submit(self._call_with_retry, request, matcher, retry_count)] = request
                return True

            for _ in range(min(worker_count, len(requests))):
                submit_next()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                completed = []
                for future in done:
                    request = futures.pop(future)
                    try:
                        response = future.result()
                    except Exception as exc:
                        first_error = first_error or exc
                        if on_segment_failed:
                            on_segment_failed(request, exc)
                        continue
                    completed.append((request, response))
                for request, response in completed:
                    responses[request.segment_id] = response
                    if on_segment_complete:
                        on_segment_complete(request, response)
                if first_error is None:
                    for _ in completed:
                        submit_next()
        if first_error is not None:
            raise first_error

    def _validate_items_within_core_window(self, items, request: SegmentMatchRequest) -> None:
        core_window = TimeRange.parse(request.core_window)
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"segment {request.segment_id} returned a malformed script item")
            item_window = TimeRange.parse(str(item.get("timestamp") or ""))
            if (
                item_window.start_seconds < core_window.start_seconds
                or item_window.end_seconds > core_window.end_seconds
            ):
                raise ValueError(f"segment {request.segment_id} emitted a clip outside its core window")

    @staticmethod
    def _validate_highlight_quota(items, request: SegmentMatchRequest) -> None:
        """Keep each Story Beat comprehensible by limiting original-sound detours."""
        highlights = [item for item in items if int(item.get("OST") or 0) == 1]
        if len(highlights) > 1:
            raise ValueError(
                f"segment {request.segment_id} may contain at most one original-sound highlight"
            )
        if not highlights:
            return
        beat_window = TimeRange.parse(request.core_window)
        highlight_window = TimeRange.parse(str(highlights[0].get("timestamp") or ""))
        highlight_seconds = highlight_window.end_seconds - highlight_window.start_seconds
        beat_seconds = beat_window.end_seconds - beat_window.start_seconds
        if beat_seconds and highlight_seconds > beat_seconds * 0.4:
            raise ValueError(
                f"segment {request.segment_id} original-sound highlight exceeds 40% of its Story Beat"
            )

    @staticmethod
    def _overlaps(start: float, end: float, other_start: float, other_end: float) -> bool:
        return start < other_end and other_start < end

    def _filter_visual_evidence(self, source: str, start: float, end: float) -> str:
        blocks = []
        for match in _VISUAL_BLOCK.finditer(source or ""):
            window = TimeRange.parse(match.group("range"))
            if self._overlaps(window.start_seconds, window.end_seconds, start, end):
                blocks.append(f"## {match.group('range')}\n{match.group('body').strip()}")
        return "\n\n".join(blocks)

    def _filter_candidates(self, source: str, start: float, end: float) -> str:
        selected = []
        for line in str(source or "").splitlines():
            match = _TIME_RANGE.search(line)
            if not match:
                continue
            window = TimeRange.parse(f"{match.group(1)}-{match.group(2)}")
            if self._overlaps(window.start_seconds, window.end_seconds, start, end):
                selected.append(line)
        return "\n".join(selected)

    def _filter_subtitles(self, source: str, start: float, end: float) -> str:
        blocks = re.split(r"(?m)(?=^\d+\s*$)", str(source or ""))
        selected = []
        for block in blocks:
            match = _TIME_RANGE.search(block)
            if not match:
                continue
            window = TimeRange.parse(f"{match.group(1)}-{match.group(2)}")
            if self._overlaps(window.start_seconds, window.end_seconds, start, end):
                selected.append(block.strip())
        return "\n\n".join(selected)

    @staticmethod
    def _format_range(start: float, end: float) -> str:
        def timestamp(value: float) -> str:
            milliseconds = max(0, round(value * 1000))
            hours, milliseconds = divmod(milliseconds, 3_600_000)
            minutes, milliseconds = divmod(milliseconds, 60_000)
            seconds, milliseconds = divmod(milliseconds, 1_000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        return f"{timestamp(start)}-{timestamp(end)}"

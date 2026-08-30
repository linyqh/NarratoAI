"""Deterministic validation and supplementation of a Fusion Script."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any

from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.services.fusion_models import EvidenceConflict, FinalizationRequest
from app.services.visual_claims import contains_unsupported_audio_claim


@dataclass(frozen=True, slots=True)
class FinalizationReport:
    requested_ratio: float
    achieved_ratio: float
    tolerance_percentage_points: float
    ratio_status: str
    inserted_candidates: list[str] = field(default_factory=list)
    retained_candidates: list[str] = field(default_factory=list)
    skipped_candidates: list[dict[str, str]] = field(default_factory=list)
    rejected_candidates: list[dict[str, str]] = field(default_factory=list)
    distribution_status: str = "unavailable"
    covered_story_thirds: list[str] = field(default_factory=list)
    unresolved_conflict_count: int = 0
    acknowledged_conflict_count: int = 0
    defaulted_candidate_ranges: list[str] = field(default_factory=list)
    candidate_decisions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    script: list[dict[str, Any]]
    original_script: list[dict[str, Any]]
    report: FinalizationReport
    evidence_conflicts: list[dict[str, Any]]


class _CandidateEligibilityPolicy:
    """Keep candidate admission decisions together, behind the finalizer seam."""

    def normalize(self, candidate, script, source_durations, conflicts):
        time_range = str(candidate.get("time_range") or "").strip()
        try:
            start, end = self._range(time_range)
        except ValueError:
            return None, "invalid_time_range"
        if end <= start:
            return None, "invalid_time_range"
        if not script or self._insertion_index(script, candidate) == 0:
            return None, "opening_segment_must_remain_narration"
        source_name = str(candidate.get("video_name") or script[0].get("video_name") or "")
        duration = source_durations.get(source_name)
        if duration is None:
            return None, "unknown_source_video"
        if end > float(duration):
            return None, "outside_source_duration"
        if any(self._conflicts(candidate, conflict) for conflict in conflicts):
            return None, "unresolved_evidence_conflict"
        if any(self._overlaps(candidate, item) for item in script):
            return None, "overlaps_existing_item"
        reason = str(candidate.get("reason") or "")
        if not reason.strip():
            return None, "missing_visual_reason"
        if contains_unsupported_audio_claim(reason):
            return None, "unsupported_audio_claim"
        return {**candidate, "time_range": time_range, "video_name": source_name}, ""

    @staticmethod
    def _range(value):
        parsed = TimeRange.parse(str(value or ""))
        return parsed.start_seconds, parsed.end_seconds

    def _insertion_index(self, script, candidate):
        source = str(candidate.get("video_name") or script[0].get("video_name") or "")
        candidate_start, _ = self._range(candidate["time_range"])
        matching = [index for index, item in enumerate(script) if str(item.get("video_name", "")) == source]
        for index in matching:
            if candidate_start < self._range(script[index]["timestamp"])[0]:
                return index
        return matching[-1] + 1 if matching else len(script)

    def _overlaps(self, left, right):
        if str(left.get("video_name", "")) != str(right.get("video_name", "")):
            return False
        left_start, left_end = self._range(left.get("time_range") or left.get("timestamp"))
        right_start, right_end = self._range(right.get("time_range") or right.get("timestamp"))
        return left_start < right_end and right_start < left_end

    def _conflicts(self, candidate, conflict):
        if not conflict.get("time_range") or (conflict.get("video_name") and conflict["video_name"] != candidate.get("video_name")):
            return False
        left_start, left_end = self._range(candidate["time_range"])
        right_start, right_end = self._range(conflict["time_range"])
        return left_start < right_end and right_start < left_end


class _TimelinePolicy:
    """Own timeline placement and distribution rules without becoming public API."""

    def score(self, candidate) -> int:
        values = [candidate.get(key, 3) for key in ("score", "story_importance", "visual_impact", "performance_value")]
        return sum(max(1, min(5, int(value))) if str(value).lstrip("-").isdigit() else 3 for value in values)

    def third(self, candidate, timeline) -> str:
        total = sum(self._duration(item) for item in timeline)
        if total <= 0:
            return "beginning"
        source = str(candidate.get("video_name", ""))
        candidate_range = self._range(candidate.get("time_range") or candidate.get("timestamp"))
        elapsed = 0.0
        for item in timeline:
            duration = self._duration(item)
            if str(item.get("video_name", "")) == source and self._range(item.get("time_range") or item.get("timestamp")) == candidate_range:
                elapsed += duration / 2
                break
            elapsed += duration
        relative = min(elapsed, total) / total
        return "beginning" if relative < 1 / 3 else "middle" if relative < 2 / 3 else "end"

    @staticmethod
    def _range(value):
        parsed = TimeRange.parse(str(value or ""))
        return parsed.start_seconds, parsed.end_seconds

    def _duration(self, item):
        start, end = self._range(item.get("time_range") or item.get("timestamp"))
        return max(0.0, end - start)


class FusionScriptFinalizer:
    """Finalize a model-produced Fusion Script without another model call."""

    TOLERANCE_PERCENTAGE_POINTS = 5.0

    def __init__(self) -> None:
        self._candidate_eligibility = _CandidateEligibilityPolicy()
        self._timeline_policy = _TimelinePolicy()

    def finalize(
        self,
        request: FinalizationRequest,
    ) -> FinalizationResult:
        script = list(request.script)
        requested_original_sound_ratio = request.requested_original_sound_ratio
        highlight_candidates = list(request.candidate_intake.candidates)
        evidence_conflicts = list(request.evidence_conflicts)
        source_durations = dict(request.source_durations)
        candidate_rejections = list(request.candidate_intake.rejections)
        original_script = deepcopy(script)
        finalized = deepcopy(script)
        self._validate_authored_timeline(finalized, source_durations)
        if finalized:
            default_video_name = str(finalized[0].get("video_name") or "")
            default_video_id = finalized[0].get("video_id", 1)
            highlight_candidates = [
                replace(
                    candidate,
                    video_name=candidate.video_name or default_video_name,
                    video_id=default_video_id if candidate.video_id is None else candidate.video_id,
                ) if isinstance(candidate, HighlightCandidate) else candidate
                for candidate in highlight_candidates
            ]
        candidate_payloads = [self._candidate_mapping(candidate) for candidate in highlight_candidates]
        if finalized:
            for candidate in candidate_payloads:
                candidate["video_name"] = str(candidate.get("video_name") or default_video_name)
                if candidate.get("video_id") is None:
                    candidate["video_id"] = default_video_id
        requested = max(0.0, min(100.0, float(requested_original_sound_ratio)))
        conflicts = [item.to_dict() for item in evidence_conflicts]
        unresolved = [conflict for conflict in conflicts if conflict["status"] == "unresolved"]
        for item in finalized:
            if any(self._item_conflicts(item, conflict) for conflict in unresolved):
                item["picture"] = "证据冲突，具体画面事实待审阅。"
                item["narration"] = "该时间段存在证据冲突，待审阅。"
        inserted: list[str] = []
        retained: list[str] = []
        skipped: list[dict[str, str]] = []
        rejected: list[dict[str, str]] = []
        candidate_decisions: list[dict[str, Any]] = []
        for rejection in candidate_rejections:
            record = {**rejection.to_dict(), "status": "rejected"}
            candidate_decisions.append(record)
            rejected.append({"time_range": str(record.get("time_range") or ""), "reason": str(record.get("reason") or "malformed_candidate")})
        eligible_candidate_count = 0
        defaulted_candidate_ranges = [
            str(candidate.get("time_range", ""))
            for candidate in candidate_payloads
            if isinstance(candidate, dict)
            and (candidate.get("defaulted_signals") or candidate.get("source_identity_status") == "defaulted_legacy")
        ]

        if requested > 0:
            eligible: list[dict[str, Any]] = []
            used_candidates: list[dict[str, Any]] = []
            for raw_candidate in candidate_payloads:
                existing_candidate = self._existing_ost_candidate(raw_candidate, finalized)
                if existing_candidate is not None:
                    used_candidates.append(existing_candidate)
                    if existing_candidate.pop("_was_finalizer_inserted", False):
                        inserted.append(existing_candidate["time_range"])
                        candidate_decisions.append(
                            self._decision_record(existing_candidate, "inserted")
                        )
                    else:
                        retained.append(existing_candidate["time_range"])
                        candidate_decisions.append(
                            self._decision_record(existing_candidate, "retained")
                        )
                    continue
                candidate, reason = self._candidate_eligibility.normalize(raw_candidate, finalized, source_durations, unresolved)
                if candidate is None:
                    rejected.append(
                        {"time_range": str(raw_candidate.get("time_range", "")), "reason": reason}
                    )
                    candidate_decisions.append(
                        self._decision_record(raw_candidate, "rejected", reason)
                    )
                else:
                    eligible.append(candidate)

            eligible.sort(
                key=lambda item: (
                    -self._timeline_policy.score(item),
                    self._range(item["time_range"])[0],
                )
            )
            distribution_timeline = deepcopy(finalized)
            for candidate in eligible:
                distribution_timeline = self._insert_candidate(distribution_timeline, candidate)
            covered: set[str] = {
                self._timeline_policy.third(candidate, distribution_timeline) for candidate in used_candidates
            }
            require_three_thirds = len(eligible) + len(used_candidates) >= 3
            eligible_candidate_count = len(eligible) + len(used_candidates)
            while eligible and (
                self._ratio(finalized) < requested - self.TOLERANCE_PERCENTAGE_POINTS
                or (require_three_thirds and len(covered) < 3)
            ):
                eligible.sort(
                    key=lambda item: (
                        self._timeline_policy.third(item, distribution_timeline) in covered,
                        -self._timeline_policy.score(item),
                        self._range(item["time_range"])[0],
                    )
                )
                candidate = eligible.pop(0)
                if any(self._overlaps(candidate, item) for item in finalized):
                    rejected.append({"time_range": candidate["time_range"], "reason": "overlaps_existing_item"})
                    candidate_decisions.append(
                        self._decision_record(candidate, "rejected", "overlaps_existing_item")
                    )
                    continue
                proposed = self._insert_candidate(finalized, candidate)
                if self._transition_bridge_violations(proposed) > self._transition_bridge_violations(finalized):
                    rejected.append({"time_range": candidate["time_range"], "reason": "would_remove_transition_bridge"})
                    candidate_decisions.append(
                        self._decision_record(candidate, "rejected", "would_remove_transition_bridge")
                    )
                    continue
                if self._ratio(proposed) > requested + self.TOLERANCE_PERCENTAGE_POINTS:
                    rejected.append(
                        {"time_range": candidate["time_range"], "reason": "would_exceed_ratio_tolerance"}
                    )
                    candidate_decisions.append(
                        self._decision_record(candidate, "rejected", "would_exceed_ratio_tolerance")
                    )
                    continue
                if self._has_three_consecutive_original_sound(proposed):
                    rejected.append({"time_range": candidate["time_range"], "reason": "consecutive_ost_limit"})
                    candidate_decisions.append(
                        self._decision_record(candidate, "rejected", "consecutive_ost_limit")
                    )
                    continue
                finalized = proposed
                inserted.append(candidate["time_range"])
                candidate_decisions.append(self._decision_record(candidate, "inserted"))
                used_candidates.append(candidate)
                covered.add(self._timeline_policy.third(candidate, distribution_timeline))
            skipped.extend(
                {"time_range": candidate["time_range"], "reason": "ratio_and_distribution_satisfied"}
                for candidate in eligible
            )
            candidate_decisions.extend(
                self._decision_record(candidate, "skipped", "ratio_and_distribution_satisfied")
                for candidate in eligible
            )
        else:
            skipped.extend(
                {
                    "time_range": str(candidate.get("time_range", "")),
                    "reason": "requested_ratio_is_zero",
                }
                for candidate in candidate_payloads
                if isinstance(candidate, dict)
            )
            candidate_decisions.extend(
                self._decision_record(candidate, "skipped", "requested_ratio_is_zero")
                for candidate in candidate_payloads
                if isinstance(candidate, dict)
            )

        finalized = self._renumber(finalized)
        achieved = self._ratio(finalized)
        ratio_status = self._ratio_status(achieved, requested)
        covered_thirds = sorted(
            {
                self._timeline_policy.third(candidate, finalized)
                for candidate in (used_candidates if requested > 0 else [])
            },
            key=("beginning", "middle", "end").index,
        )
        if requested <= 0 or eligible_candidate_count == 0:
            distribution_status = "unavailable"
        elif len(covered_thirds) == 3:
            distribution_status = "achieved"
        elif eligible_candidate_count < 3:
            distribution_status = "degraded"
        else:
            distribution_status = "unavailable"

        for item in finalized:
            item.pop("_finalizer_inserted", None)
        return FinalizationResult(
            script=finalized,
            original_script=original_script,
            evidence_conflicts=conflicts,
            report=FinalizationReport(
                requested_ratio=requested,
                achieved_ratio=round(achieved, 2),
                tolerance_percentage_points=self.TOLERANCE_PERCENTAGE_POINTS,
                ratio_status=ratio_status,
                inserted_candidates=inserted,
                retained_candidates=retained,
                skipped_candidates=skipped,
                rejected_candidates=rejected,
                distribution_status=distribution_status,
                covered_story_thirds=covered_thirds,
                unresolved_conflict_count=len(unresolved),
                acknowledged_conflict_count=len(conflicts) - len(unresolved),
                defaulted_candidate_ranges=defaulted_candidate_ranges,
                candidate_decisions=candidate_decisions,
            ),
        )

    @staticmethod
    def _decision_record(candidate: dict[str, Any], status: str, reason: str = "") -> dict[str, Any]:
        record = {
            "candidate_id": str(candidate.get("candidate_id") or ""),
            "video_id": candidate.get("video_id"),
            "video_name": str(candidate.get("video_name") or ""),
            "source_video_identity": candidate.get("source_video_identity"),
            "time_range": str(candidate.get("time_range") or ""),
            "status": status,
        }
        if reason:
            record["reason"] = reason
        return record

    @staticmethod
    def _candidate_mapping(candidate: HighlightCandidate) -> dict[str, Any]:
        """Project a domain candidate only at the script-construction boundary."""
        return {
            "candidate_id": candidate.candidate_id,
            "time_range": str(candidate.time_range),
            "category": candidate.category,
            "reason": candidate.reason,
            "score": candidate.score,
            "story_importance": candidate.story_importance,
            "visual_impact": candidate.visual_impact,
            "performance_value": candidate.performance_value,
            "video_id": candidate.video_id,
            "video_name": candidate.video_name,
            "source_video_identity": candidate.source_video_identity,
            "source_identity_status": candidate.source_identity_status,
            "defaulted_signals": list(candidate.defaulted_signals),
        }

    def _insert_candidate(self, script, candidate):
        item = {
            "_id": 0,
            "video_id": candidate["video_id"],
            "video_name": candidate["video_name"],
            "timestamp": candidate["time_range"],
            "picture": str(candidate.get("reason") or ""),
            "narration": "播放原片",
            "OST": 1,
            "_finalizer_inserted": True,
        }
        if candidate.get("candidate_id"):
            item["highlight_candidate_id"] = candidate["candidate_id"]
        result = deepcopy(script)
        insert_at = self._insertion_index(result, candidate)
        result.insert(insert_at, item)
        return result

    def _insertion_index(self, script, candidate):
        same_source_indices = [
            index
            for index, existing in enumerate(script)
            if str(existing.get("video_name", "")) == str(candidate.get("video_name", ""))
        ]
        if not same_source_indices:
            return len(script)
        candidate_start, _ = self._range(candidate["time_range"])
        insert_at = same_source_indices[-1] + 1
        for index in same_source_indices:
            existing_start, _ = self._range(script[index]["timestamp"])
            if candidate_start < existing_start:
                insert_at = index
                break
        return insert_at

    def _existing_ost_candidate(self, raw, script):
        if not isinstance(raw, dict) or not str(raw.get("reason") or "").strip():
            return None
        time_range = str(raw.get("time_range") or "").strip()
        default_source = str(script[0].get("video_name", "")) if script else ""
        source_name = str(raw.get("video_name") or default_source)
        try:
            candidate_range = self._range(time_range)
        except ValueError:
            return None
        for item in script:
            if (
                int(item.get("OST", 0) or 0) == 1
                and str(item.get("video_name", "")) == source_name
                and self._range(str(item.get("timestamp") or "")) == candidate_range
            ):
                return {
                    **deepcopy(raw),
                    "time_range": time_range,
                    "video_name": source_name,
                    "video_id": raw.get("video_id", item.get("video_id")),
                    "_was_finalizer_inserted": item.get("highlight_candidate_id") == raw.get("candidate_id"),
                }
        return None

    def _renumber(self, script):
        result = deepcopy(script)
        for index, item in enumerate(result, start=1):
            item["_id"] = index
            if int(item.get("OST", 0) or 0) == 1:
                item["narration"] = f"播放原片{index}"
        return result

    def _validate_authored_timeline(self, script, source_durations=None) -> None:
        if not script:
            return
        source_durations = dict(source_durations or {})
        ranges_by_source = {}
        for index, item in enumerate(script, start=1):
            source_name = str(item.get("video_name") or "")
            timestamp = str(item.get("timestamp") or item.get("time_range") or "")
            try:
                start, end = self._range(timestamp)
            except ValueError as exc:
                raise ValueError(
                    f"authored timeline contains non-positive range for {source_name or '<unknown source>'} at item {index}"
                ) from exc
            if end <= start:
                raise ValueError(
                    f"authored timeline contains non-positive range for {source_name or '<unknown source>'} at item {index}"
                )
            known_duration = source_durations.get(source_name)
            if known_duration is not None and end > float(known_duration):
                raise ValueError(
                    f"authored timeline range exceeds known duration for {source_name}: {timestamp}"
                )
            ranges_by_source.setdefault(source_name, []).append((start, end, index))
        for source_name, ranges in ranges_by_source.items():
            ranges.sort()
            for (_, previous_end, previous_index), (current_start, _, current_index) in zip(ranges, ranges[1:]):
                if current_start < previous_end:
                    raise ValueError(
                        f"authored timeline contains overlapping ranges for {source_name or '<unknown source>'}: items {previous_index} and {current_index}"
                    )
        if int(script[0].get("OST", 0) or 0) == 1:
            raise ValueError("authored timeline cannot open with OST=1")
        if self._has_three_consecutive_original_sound(script):
            raise ValueError("authored timeline contains three consecutive OST=1 items")
        if self._transition_bridge_violations(script):
            raise ValueError("authored timeline lacks a narration bridge between source videos")

    def _ratio(self, script):
        total = sum(self._duration(item) for item in script)
        original = sum(self._duration(item) for item in script if int(item.get("OST", 0) or 0) == 1)
        return (original / total * 100.0) if total > 0 else 0.0

    def _ratio_status(self, achieved, requested):
        if achieved < requested - self.TOLERANCE_PERCENTAGE_POINTS:
            return "below_target"
        if achieved > requested + self.TOLERANCE_PERCENTAGE_POINTS:
            return "above_target"
        return "compliant"

    def _duration(self, item):
        start, end = self._range(str(item.get("timestamp") or ""))
        return max(0.0, end - start)

    def _range(self, value):
        parsed = TimeRange.parse(str(value or ""))
        return parsed.start_seconds, parsed.end_seconds

    def _overlaps(self, left, right):
        if str(left.get("video_name", "")) != str(right.get("video_name", "")):
            return False
        left_start, left_end = self._range(left.get("time_range") or left.get("timestamp"))
        right_start, right_end = self._range(right.get("time_range") or right.get("timestamp"))
        return left_start < right_end and right_start < left_end

    def _conflicts(self, candidate, conflict):
        conflict_range = conflict.get("time_range")
        if not conflict_range:
            return False
        if conflict.get("video_name") and conflict.get("video_name") != candidate.get("video_name"):
            return False
        left_start, left_end = self._range(candidate["time_range"])
        right_start, right_end = self._range(str(conflict_range))
        return left_start < right_end and right_start < left_end

    def _item_conflicts(self, item, conflict):
        candidate = {
            "video_name": item.get("video_name"),
            "time_range": item.get("timestamp"),
        }
        return self._conflicts(candidate, conflict)

    def _sort_key(self, item):
        source = str(item.get("video_name", ""))
        start, _ = self._range(item.get("time_range") or item.get("timestamp"))
        return source, start

    @staticmethod
    def _has_three_consecutive_original_sound(script):
        count = 0
        for item in script:
            count = count + 1 if int(item.get("OST", 0) or 0) == 1 else 0
            if count >= 3:
                return True
        return False

    @staticmethod
    def _transition_bridge_violations(script):
        violations = 0
        for previous, current in zip(script, script[1:]):
            crosses_source = str(previous.get("video_name", "")) != str(current.get("video_name", ""))
            both_original_sound = (
                int(previous.get("OST", 0) or 0) == 1
                and int(current.get("OST", 0) or 0) == 1
            )
            if crosses_source and both_original_sound:
                violations += 1
        return violations

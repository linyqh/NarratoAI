import hashlib
import unittest

from app.services.fusion_script_finalizer import FusionScriptFinalizer
from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.services.fusion_models import CandidateRejection, EvidenceConflict, FinalizationRequest, HighlightCandidateIntake
from app.config.defaults import DEFAULT_VISION_MAX_CONCURRENCY


class FusionScriptFinalizerTests(unittest.TestCase):
    def _finalize(self, request=None, **kwargs):
        if request is not None:
            return FusionScriptFinalizer().finalize(request)
        candidates = []
        rejections = [CandidateRejection(**item) for item in kwargs.pop("candidate_rejections", [])]
        for item in kwargs.pop("highlight_candidates", []):
            if isinstance(item, HighlightCandidate):
                candidates.append(item)
                continue
            candidate_id = item.get("candidate_id") or hashlib.sha256(
                "|".join(str(item.get(field) or "") for field in ("video_name", "time_range", "category", "reason")).encode()
            ).hexdigest()[:16]
            try:
                candidates.append(HighlightCandidate(
                    time_range=TimeRange.parse(item["time_range"]),
                    category=item["category"], reason=item["reason"], score=item["score"],
                    story_importance=item.get("story_importance", 3), visual_impact=item.get("visual_impact", 3),
                    performance_value=item.get("performance_value", 3), video_id=item.get("video_id"),
                    video_name=item.get("video_name", ""), source_video_identity=item.get("source_video_identity"),
                    source_identity_status=item.get("source_identity_status", "unavailable"),
                    defaulted_signals=tuple(item.get("defaulted_signals", ())), candidate_id=candidate_id,
                ))
            except (KeyError, TypeError, ValueError):
                rejections.append(CandidateRejection(candidate_id, str(item.get("time_range") or ""), "invalid_time_range"))
        conflicts = tuple(
            item if isinstance(item, EvidenceConflict) else EvidenceConflict.from_mapping(item)
            for item in kwargs.pop("evidence_conflicts", [])
        )
        return FusionScriptFinalizer().finalize(FinalizationRequest(
            script=tuple(kwargs.pop("script", [])),
            requested_original_sound_ratio=kwargs.pop("requested_original_sound_ratio", 0),
            candidate_intake=HighlightCandidateIntake(tuple(candidates), tuple(rejections), len(candidates) + len(rejections)),
            evidence_conflicts=conflicts,
            source_durations=kwargs.pop("source_durations", {}),
        ))

    def test_finalizes_one_typed_request_and_decides_every_submission(self):
        request = FinalizationRequest(
            script=({"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场", "OST": 0},),
            requested_original_sound_ratio=0,
            candidate_intake=HighlightCandidateIntake(candidates=(), rejections=(), submitted_count=0),
            evidence_conflicts=(),
            source_durations={"film.mp4": 10.0},
        )

        result = self._finalize(request)

        self.assertEqual([], result.report.candidate_decisions)
    def test_records_artifact_rejections_even_when_ratio_is_zero(self):
        result = self._finalize(
            script=[{"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场", "OST": 0}],
            requested_original_sound_ratio=0,
            highlight_candidates=[],
            candidate_rejections=[{"candidate_id": "bad-1", "time_range": "banana", "reason": "invalid_time_range"}],
            evidence_conflicts=[],
            source_durations={"film.mp4": 10.0},
        )

        self.assertIn({"candidate_id": "bad-1", "time_range": "banana", "reason": "invalid_time_range", "status": "rejected"}, result.report.candidate_decisions)
    def test_visual_analysis_defaults_to_two_concurrent_requests(self):
        self.assertEqual(2, DEFAULT_VISION_MAX_CONCURRENCY)

    def test_supplements_a_deficient_original_sound_ratio(self):
        script = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "film.mp4",
                "timestamp": "00:00:00,000-00:00:10,000",
                "picture": "主角进入大厅。",
                "narration": "他走进大厅，却发现这里空无一人。",
                "OST": 0,
            },
            {
                "_id": 2,
                "video_id": 1,
                "video_name": "film.mp4",
                "timestamp": "00:00:20,000-00:00:30,000",
                "picture": "主角继续寻找。",
                "narration": "他继续向深处寻找。",
                "OST": 0,
            },
        ]
        candidates = [
            {
                "time_range": "00:00:10,000-00:00:20,000",
                "category": "动作场面",
                "reason": "主角翻越倒塌的栏杆。",
                "score": 5,
            }
        ]

        result = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=candidates,
            evidence_conflicts=[],
            source_durations={"film.mp4": 60.0},
        )

        self.assertEqual(0, result.script[0]["OST"])
        self.assertEqual(3, len(result.script))
        self.assertEqual("compliant", result.report.ratio_status)
        self.assertAlmostEqual(33.33, result.report.achieved_ratio, places=2)
        self.assertEqual(["00:00:10,000-00:00:20,000"], result.report.inserted_candidates)
        self.assertEqual("degraded", result.report.distribution_status)

    def test_withholds_unresolved_conflict_claims_and_rejects_overlapping_candidate(self):
        script = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "film.mp4",
                "timestamp": "00:00:00,000-00:00:10,000",
                "picture": "男人举起了手枪。",
                "narration": "他终于拿出了藏着的手枪。",
                "OST": 0,
            }
        ]
        conflict = {
            "video_name": "film.mp4",
            "time_range": "00:00:02,000-00:00:08,000",
            "subtitle_claim": "他拿出了手枪",
            "visual_observation": "画面只显示男人抬手，物体不可辨认",
            "severity": "high",
            "status": "unresolved",
        }

        result = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=[
                {
                    "time_range": "00:00:02,000-00:00:08,000",
                    "category": "悬疑线索",
                    "reason": "男人抬手。",
                    "score": 5,
                }
            ],
            evidence_conflicts=[conflict],
            source_durations={"film.mp4": 20.0},
        )

        self.assertEqual("证据冲突，具体画面事实待审阅。", result.script[0]["picture"])
        self.assertEqual("该时间段存在证据冲突，待审阅。", result.script[0]["narration"])
        self.assertEqual(1, result.report.unresolved_conflict_count)
        self.assertEqual("unresolved_evidence_conflict", result.report.rejected_candidates[0]["reason"])
        for field in (
            "video_name",
            "time_range",
            "subtitle_claim",
            "visual_observation",
            "severity",
            "status",
        ):
            self.assertEqual(conflict[field], result.evidence_conflicts[0][field])
        self.assertEqual("unverified_legacy", result.evidence_conflicts[0]["source_identity_status"])

    def test_does_not_overshoot_the_upper_ratio_tolerance_with_a_large_candidate(self):
        script = [
            {
                "_id": 1,
                "video_id": 1,
                "video_name": "film.mp4",
                "timestamp": "00:00:00,000-00:00:20,000",
                "picture": "建立场景。",
                "narration": "故事开始。",
                "OST": 0,
            }
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=20,
            highlight_candidates=[
                {
                    "time_range": "00:00:20,000-00:00:40,000",
                    "category": "视觉奇观",
                    "reason": "建筑在强光中坍塌。",
                    "score": 5,
                }
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 60.0},
        )

        self.assertEqual(1, len(result.script))
        self.assertEqual("below_target", result.report.ratio_status)
        self.assertEqual("would_exceed_ratio_tolerance", result.report.rejected_candidates[0]["reason"])

    def test_uses_highlights_across_all_story_thirds_when_ratio_allows(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场", "OST": 0},
            {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:20,000-00:00:30,000", "picture": "发展", "narration": "发展", "OST": 0},
            {"_id": 3, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:40,000-00:00:50,000", "picture": "转折", "narration": "转折", "OST": 0},
            {"_id": 4, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:01:00,000-00:01:10,000", "picture": "结尾", "narration": "结尾", "OST": 0},
        ]
        candidates = [
            {"time_range": "00:00:10,000-00:00:15,000", "category": "动作场面", "reason": "开端追逐。", "score": 5},
            {"time_range": "00:00:30,000-00:00:35,000", "category": "表演情绪", "reason": "中段落泪。", "score": 5},
            {"time_range": "00:00:50,000-00:00:55,000", "category": "视觉奇观", "reason": "末段建筑坍塌。", "score": 5},
        ]

        result = self._finalize(
            script=script,
            requested_original_sound_ratio=25,
            highlight_candidates=candidates,
            evidence_conflicts=[],
            source_durations={"film.mp4": 80.0},
        )

        self.assertEqual(3, len(result.report.inserted_candidates))
        self.assertEqual("achieved", result.report.distribution_status)
        self.assertEqual(["beginning", "middle", "end"], result.report.covered_story_thirds)
        self.assertEqual("compliant", result.report.ratio_status)

    def test_reports_a_model_selected_candidate_as_retained(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场", "OST": 0},
            {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:10,000-00:00:20,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=50,
            highlight_candidates=[
                {"time_range": "00:00:10,000-00:00:20,000", "category": "表演情绪", "reason": "人物沉默落泪。", "score": 4}
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 30.0},
        )

        self.assertEqual(["00:00:10,000-00:00:20,000"], result.report.retained_candidates)

    def test_zero_ratio_skips_candidates_without_inserting_them(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0}
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=0,
            highlight_candidates=[
                {"time_range": "00:00:10,000-00:00:15,000", "category": "动作场面", "reason": "人物奔跑。", "score": 5}
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 20.0},
        )
        self.assertEqual(script, result.script)
        self.assertEqual("compliant", result.report.ratio_status)
        self.assertEqual("requested_ratio_is_zero", result.report.skipped_candidates[0]["reason"])

    def test_reports_an_existing_ratio_above_the_upper_tolerance_without_deleting_it(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0},
            {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:10,000-00:00:30,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=[],
            evidence_conflicts=[],
            source_durations={"film.mp4": 40.0},
        )
        self.assertEqual(script, result.script)
        self.assertEqual("above_target", result.report.ratio_status)

    def test_ratio_is_compliant_at_both_five_point_boundaries(self):
        cases = (
            (
                30,
                [
                    {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:30,000", "picture": "旁白", "narration": "旁白。", "OST": 0},
                    {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:30,000-00:00:40,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
                ],
                25.0,
            ),
            (
                30,
                [
                    {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:13,000", "picture": "旁白", "narration": "旁白。", "OST": 0},
                    {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:13,000-00:00:20,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
                ],
                35.0,
            ),
        )
        for requested, script, expected in cases:
            with self.subTest(expected=expected):
                result = self._finalize(
                    script=script,
                    requested_original_sound_ratio=requested,
                    highlight_candidates=[],
                    evidence_conflicts=[],
                    source_durations={"film.mp4": 40.0},
                )
                self.assertEqual("compliant", result.report.ratio_status)
                self.assertEqual(expected, result.report.achieved_ratio)

    def test_preserves_an_acknowledged_review_state(self):
        result = self._finalize(
            script=[
                {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0}
            ],
            requested_original_sound_ratio=0,
            highlight_candidates=[],
            evidence_conflicts=[
                {
                    "video_name": "film.mp4",
                    "time_range": "00:00:02,000-00:00:03,000",
                    "subtitle_claim": "字幕事实",
                    "visual_observation": "画面事实",
                    "severity": "high",
                    "status": "acknowledged",
                }
            ],
            source_durations={"film.mp4": 10.0},
        )

        self.assertEqual("acknowledged", result.evidence_conflicts[0]["status"])
        self.assertEqual(0, result.report.unresolved_conflict_count)

    def test_rejects_candidates_outside_source_at_opening_and_after_two_ost_items(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:05,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0},
            {"_id": 2, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:10,000-00:00:15,000", "picture": "原片一", "narration": "播放原片2", "OST": 1},
            {"_id": 3, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:15,000-00:00:20,000", "picture": "原片二", "narration": "播放原片3", "OST": 1},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=80,
            highlight_candidates=[
                {"time_range": "00:00:00,000-00:00:05,000", "category": "动作场面", "reason": "人物冲入画面。", "score": 5},
                {"time_range": "00:00:20,000-00:00:25,000", "category": "表演情绪", "reason": "人物沉默落泪。", "score": 4},
                {"time_range": "00:00:29,000-00:00:35,000", "category": "视觉奇观", "reason": "建筑坍塌。", "score": 3},
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 30.0},
        )

        reasons = {item["reason"] for item in result.report.rejected_candidates}
        self.assertIn("opening_segment_must_remain_narration", reasons)
        self.assertIn("consecutive_ost_limit", reasons)
        self.assertIn("outside_source_duration", reasons)

    def test_rejected_candidate_leaves_the_input_and_original_script_recoverable(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0}
        ]
        expected = [dict(script[0])]

        result = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=[
                {"time_range": "not-a-range", "category": "动作场面", "reason": "人物奔跑。", "score": 5}
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 10.0},
        )

        self.assertEqual(expected, script)
        self.assertEqual(expected, result.original_script)
        self.assertEqual("invalid_time_range", result.report.rejected_candidates[0]["reason"])

    def test_does_not_create_an_ost_opening_for_an_empty_model_script(self):
        result = self._finalize(
            script=[],
            requested_original_sound_ratio=100,
            highlight_candidates=[
                {"time_range": "00:00:00,000-00:00:05,000", "category": "动作场面", "reason": "人物冲入画面。", "score": 5}
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 10.0},
        )

        self.assertEqual([], result.script)
        self.assertEqual("opening_segment_must_remain_narration", result.report.rejected_candidates[0]["reason"])

    def test_rejects_audio_claim_and_unknown_source_candidates(self):
        result = self._finalize(
            script=[
                {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "开场", "narration": "开场。", "OST": 0}
            ],
            requested_original_sound_ratio=50,
            highlight_candidates=[
                {"video_name": "film.mp4", "time_range": "00:00:10,000-00:00:15,000", "category": "动作场面", "reason": "背景音乐骤然响起。", "score": 5},
                {"video_name": "other.mp4", "time_range": "00:00:10,000-00:00:15,000", "category": "动作场面", "reason": "人物翻越栏杆。", "score": 4},
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 30.0},
        )

        reasons = {item["reason"] for item in result.report.rejected_candidates}
        self.assertIn("unsupported_audio_claim", reasons)
        self.assertIn("unknown_source_video", reasons)

    def test_rejects_an_authored_timeline_that_already_breaks_continuity_rules(self):
        invalid_scripts = (
            [
                {"_id": 1, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:05,000", "picture": "原片", "narration": "播放原片1", "OST": 1}
            ],
            [
                {"_id": 1, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:05,000", "picture": "旁白", "narration": "旁白。", "OST": 0},
                {"_id": 2, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:05,000-00:00:10,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
                {"_id": 3, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:10,000-00:00:15,000", "picture": "原片", "narration": "播放原片3", "OST": 1},
                {"_id": 4, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:15,000-00:00:20,000", "picture": "原片", "narration": "播放原片4", "OST": 1},
            ],
            [
                {"_id": 1, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:05,000", "picture": "旁白", "narration": "旁白。", "OST": 0},
                {"_id": 2, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:05,000-00:00:10,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
                {"_id": 3, "video_id": 2, "video_name": "b.mp4", "timestamp": "00:00:00,000-00:00:05,000", "picture": "原片", "narration": "播放原片3", "OST": 1},
            ],
        )
        for script in invalid_scripts:
            with self.subTest(script=script), self.assertRaises(ValueError):
                self._finalize(
                    script=script,
                    requested_original_sound_ratio=30,
                    highlight_candidates=[],
                    evidence_conflicts=[],
                    source_durations={"a.mp4": 20.0, "b.mp4": 20.0},
                )

    def test_preserves_authored_multi_video_story_order(self):
        script = [
            {"_id": 1, "video_id": 2, "video_name": "b.mp4", "timestamp": "00:00:20,000-00:00:30,000", "picture": "倒叙开场", "narration": "先看结果。", "OST": 0},
            {"_id": 2, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "回到之前", "narration": "故事回到之前。", "OST": 0},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=[
                {"video_id": 2, "video_name": "b.mp4", "time_range": "00:00:30,000-00:00:40,000", "category": "动作场面", "reason": "人物冲出房间。", "score": 5}
            ],
            evidence_conflicts=[],
            source_durations={"a.mp4": 60.0, "b.mp4": 60.0},
        )

        self.assertEqual(["b.mp4", "b.mp4", "a.mp4"], [item["video_name"] for item in result.script])

    def test_rejects_a_candidate_that_overlaps_a_candidate_inserted_earlier(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:20,000", "picture": "开场", "narration": "开场。", "OST": 0}
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=40,
            highlight_candidates=[
                {"time_range": "00:00:20,000-00:00:30,000", "category": "动作场面", "reason": "人物奔跑。", "score": 5},
                {"time_range": "00:00:25,000-00:00:35,000", "category": "动作场面", "reason": "人物翻越围栏。", "score": 4},
            ],
            evidence_conflicts=[],
            source_durations={"film.mp4": 60.0},
        )

        self.assertEqual(2, len(result.script))
        self.assertIn("overlaps_existing_item", [item["reason"] for item in result.report.rejected_candidates])

    def test_finalization_is_idempotent_for_the_same_candidates(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:20,000", "picture": "开场", "narration": "开场。", "OST": 0}
        ]
        candidates = [
            {"time_range": "00:00:20,000-00:00:30,000", "category": "表演情绪", "reason": "人物沉默落泪。", "score": 5}
        ]
        first = self._finalize(
            script=script,
            requested_original_sound_ratio=30,
            highlight_candidates=candidates,
            evidence_conflicts=[],
            source_durations={"film.mp4": 60.0},
        )
        second = self._finalize(
            script=first.script,
            requested_original_sound_ratio=30,
            highlight_candidates=candidates,
            evidence_conflicts=[],
            source_durations={"film.mp4": 60.0},
        )

        self.assertEqual(first.script, second.script)
        self.assertEqual(first.report, second.report)

    def test_distribution_uses_cumulative_story_time_across_multiple_videos(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "第一幕", "narration": "第一幕。", "OST": 0},
            {"_id": 2, "video_id": 2, "video_name": "b.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "第二幕", "narration": "第二幕。", "OST": 0},
            {"_id": 3, "video_id": 3, "video_name": "c.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "第三幕", "narration": "第三幕。", "OST": 0},
        ]
        candidates = [
            {"video_id": 1, "video_name": "a.mp4", "time_range": "00:00:10,000-00:00:15,000", "category": "动作场面", "reason": "第一幕高光。", "score": 5},
            {"video_id": 2, "video_name": "b.mp4", "time_range": "00:00:10,000-00:00:15,000", "category": "表演情绪", "reason": "第二幕高光。", "score": 5},
            {"video_id": 3, "video_name": "c.mp4", "time_range": "00:00:10,000-00:00:15,000", "category": "视觉奇观", "reason": "第三幕高光。", "score": 5},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=35,
            highlight_candidates=candidates,
            evidence_conflicts=[],
            source_durations={"a.mp4": 20.0, "b.mp4": 20.0, "c.mp4": 20.0},
        )

        self.assertEqual(["beginning", "middle", "end"], result.report.covered_story_thirds)
        self.assertEqual("achieved", result.report.distribution_status)

    def test_rejects_supplementation_that_removes_a_cross_video_narration_bridge(self):
        script = [
            {"_id": 1, "video_id": 1, "video_name": "a.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "桥接", "narration": "随后故事转向另一处。", "OST": 0},
            {"_id": 2, "video_id": 2, "video_name": "b.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "原片", "narration": "播放原片2", "OST": 1},
        ]
        result = self._finalize(
            script=script,
            requested_original_sound_ratio=70,
            highlight_candidates=[
                {"video_id": 1, "video_name": "a.mp4", "time_range": "00:00:10,000-00:00:20,000", "category": "动作场面", "reason": "人物冲出房间。", "score": 5}
            ],
            evidence_conflicts=[],
            source_durations={"a.mp4": 30.0, "b.mp4": 30.0},
        )

        self.assertEqual(2, len(result.script))
        self.assertEqual("would_remove_transition_bridge", result.report.rejected_candidates[0]["reason"])


if __name__ == "__main__":
    unittest.main()

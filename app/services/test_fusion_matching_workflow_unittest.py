import unittest

from app.services.fusion_matching_workflow import (
    FusionMatchingInput,
    FusionMatchingWorkflow,
)


class _FixedSegmentAdapter:
    """Fake for the configured text-model seam."""

    def match_segment(self, request):
        timestamps = {
            "segment-1": "00:00:00,000-00:00:10,000",
            "segment-2": "00:05:00,000-00:05:10,000",
        }
        return {
            "items": [
                {
                    "video_id": 1,
                    "video_name": "film.mp4",
                    "timestamp": timestamps[request.segment_id],
                    "picture": request.segment_id,
                    "narration": request.narration,
                    "OST": 0,
                    "narrative_role": "story",
                }
            ],
            "evidence_conflicts": [],
        }


class _BridgeRepairAdapter(_FixedSegmentAdapter):
    def __init__(self):
        self.matched_segment_ids = []
        self.repair_requests = []

    def match_segment(self, request):
        self.matched_segment_ids.append(request.segment_id)
        return super().match_segment(request)

    def repair_transition(self, request):
        self.repair_requests.append(request)
        return {
            "items": [
                {
                    "video_id": 1,
                    "video_name": "film.mp4",
                    "timestamp": "00:00:00,000-00:00:10,000",
                    "picture": "主角进入通道",
                    "narration": "第一句。",
                    "OST": 0,
                    "narrative_role": "story",
                },
                {
                    "video_id": 1,
                    "video_name": "film.mp4",
                    "timestamp": "00:04:50,000-00:05:00,000",
                    "picture": "场景转到封锁的出口",
                    "narration": "经过一段搜索，他终于抵达出口。",
                    "OST": 0,
                    "narrative_role": "bridge",
                },
            ],
            "evidence_conflicts": [],
        }


class _TransientFailureAdapter(_FixedSegmentAdapter):
    def __init__(self):
        self.calls = []

    def match_segment(self, request):
        self.calls.append(request.segment_id)
        if request.segment_id == "segment-2" and self.calls.count("segment-2") == 1:
            raise RuntimeError("temporary provider failure")
        response = super().match_segment(request)
        if request.segment_id == "segment-1":
            response["items"][0]["timestamp"] = "00:04:40,000-00:04:50,000"
        return response


class _CoreWindowAdapter:
    def __init__(self):
        self.matched_segment_ids = []

    def match_segment(self, request):
        self.matched_segment_ids.append(request.segment_id)
        return {
            "items": [
                {
                    "video_id": 1,
                    "video_name": "film.mp4",
                    "timestamp": request.core_window,
                    "picture": request.segment_id,
                    "narration": request.narration,
                    "OST": 0,
                    "narrative_role": "story",
                }
            ],
            "evidence_conflicts": [],
        }


class FusionMatchingWorkflowTests(unittest.TestCase):
    @staticmethod
    def _plan():
        return {
            "segments": [
                {
                    "segment_id": "segment-1",
                    "sentence_start": 1,
                    "sentence_end": 1,
                    "core_window": "00:00:00,000-00:05:00,000",
                    "active_subject": "主角",
                    "entering_state": "正在寻找出口",
                    "trigger_event": "发现通道",
                    "exiting_state": "进入通道",
                    "exception_reason": "测试单句 Story Beat",
                },
                {
                    "segment_id": "segment-2",
                    "sentence_start": 2,
                    "sentence_end": 2,
                    "core_window": "00:05:00,000-00:05:20,000",
                    "active_subject": "主角",
                    "entering_state": "进入通道",
                    "trigger_event": "出口被封锁",
                    "exiting_state": "必须寻找新路线",
                    "handoff_from_previous": {
                        "actor": "continuous", "place": "continuous", "goal": "continuous",
                        "cause": "continuous", "state": "continuous",
                    },
                    "exception_reason": "测试单句 Story Beat",
                },
            ]
        }

    def test_merged_segment_matches_with_an_unbridged_large_jump_are_not_renderable(self):
        request = FusionMatchingInput(
            narration_copy="第一句。第二句。",
            plan_payload=self._plan(),
            subtitle_evidence="",
            visual_evidence="",
            highlight_candidates="",
        )

        result = FusionMatchingWorkflow().execute(request, _FixedSegmentAdapter())

        self.assertFalse(result.renderable)
        self.assertEqual(
            "unbridged_merged_source_jump",
            result.continuity_report.findings[0].code,
        )
        self.assertEqual("segment-2", result.continuity_report.findings[0].segment_id)

    def test_targeted_repair_uses_only_affected_core_evidence_and_preserves_other_matches(self):
        adapter = _BridgeRepairAdapter()
        request = FusionMatchingInput(
            narration_copy="第一句。第二句。",
            plan_payload=self._plan(),
            subtitle_evidence=(
                "1\n00:04:52,000 --> 00:04:55,000\n相关字幕\n\n"
                "2\n00:10:00,000 --> 00:10:05,000\n无关字幕"
            ),
            visual_evidence=(
                "## 00:04:52,000-00:04:55,000\n- 相关画面\n\n"
                "## 00:10:00,000-00:10:05,000\n- 无关画面"
            ),
            highlight_candidates=(
                "- 00:04:52,000-00:04:55,000｜动作场面｜价值 4/5：相关候选。\n"
                "- 00:10:00,000-00:10:05,000｜动作场面｜价值 5/5：无关候选。"
            ),
        )

        result = FusionMatchingWorkflow().execute(request, adapter)

        self.assertTrue(result.renderable)
        self.assertEqual(("segment-1",), result.repaired_segment_ids)
        self.assertEqual(["segment-1", "segment-2"], adapter.matched_segment_ids)
        self.assertEqual(1, len(adapter.repair_requests))
        repair_request = adapter.repair_requests[0]
        self.assertEqual("00:00:00,000-00:05:00,000", str(repair_request.core_window))
        self.assertEqual("第一句。", repair_request.narration)
        self.assertIn("相关字幕", repair_request.subtitle_evidence)
        self.assertNotIn("无关字幕", repair_request.subtitle_evidence)
        self.assertIn("相关画面", repair_request.visual_evidence)
        self.assertNotIn("无关画面", repair_request.visual_evidence)
        self.assertIn("相关候选", repair_request.highlight_candidates)
        self.assertNotIn("无关候选", repair_request.highlight_candidates)

    def test_matching_attempts_are_reported_per_segment_after_retry(self):
        result = FusionMatchingWorkflow().execute(
            FusionMatchingInput(
                narration_copy="第一句。第二句。",
                plan_payload=self._plan(),
                subtitle_evidence="",
                visual_evidence="",
                highlight_candidates="",
            ),
            _TransientFailureAdapter(),
        )

        self.assertTrue(result.renderable)
        self.assertEqual({"segment-1": 1, "segment-2": 2}, result.attempts_by_segment)
        self.assertEqual({}, result.repair_attempts_by_segment)

    def test_reports_each_attempt_before_a_permanent_failure_escapes(self):
        attempts = []

        class FailingAdapter:
            def match_segment(self, _request):
                raise RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "failed after retry"):
            FusionMatchingWorkflow().execute(
                FusionMatchingInput("第一句。第二句。", self._plan(), "", "", ""),
                FailingAdapter(),
                on_segment_attempt=lambda segment, count: attempts.append(
                    (segment.segment_id, count)
                ),
            )

        self.assertIn(("segment-1", 1), attempts)
        self.assertIn(("segment-1", 2), attempts)

    def test_semantic_state_handoff_failure_is_reviewable_without_matching(self):
        plan = self._plan()
        plan["segments"][1]["handoff_from_previous"] = {
            "actor": "continuous",
            "place": "continuous",
            "goal": "continuous",
            "cause": "continuous",
            "state": "disconnected",
        }
        adapter = _CoreWindowAdapter()

        result = FusionMatchingWorkflow().execute(
            FusionMatchingInput("第一句。第二句。", plan, "", "", ""), adapter
        )

        self.assertFalse(result.renderable)
        self.assertEqual([], adapter.matched_segment_ids)
        self.assertEqual(
            "unbridged_semantic_handoff",
            result.continuity_report.findings[0].code,
        )

    def test_plan_edit_reuses_matches_outside_the_changed_beat_and_its_neighbors(self):
        plan = {"segments": []}
        for index in range(4):
            start = index * 10
            end = start + 10
            plan["segments"].append(
                {
                    "segment_id": f"segment-{index + 1}",
                    "sentence_start": index + 1,
                    "sentence_end": index + 1,
                    "core_window": f"00:00:{start:02d},000-00:00:{end:02d},000",
                    "active_subject": "主角",
                    "entering_state": f"状态 {index}",
                    "trigger_event": f"事件 {index}",
                    "exiting_state": f"状态 {index + 1}",
                    "handoff_from_previous": {
                        "actor": "continuous", "place": "continuous", "goal": "continuous",
                        "cause": "continuous", "state": "continuous",
                    },
                    "exception_reason": "测试单句 Story Beat",
                }
            )
        first_adapter = _CoreWindowAdapter()
        first = FusionMatchingWorkflow().execute(
            FusionMatchingInput("一。二。三。四。", plan, "", "", ""), first_adapter
        )
        edited_plan = {
            "segments": [dict(segment) for segment in plan["segments"]]
        }
        edited_plan["segments"][1]["trigger_event"] = "修改后的事件"
        resume_adapter = _CoreWindowAdapter()

        resumed = FusionMatchingWorkflow().execute(
            FusionMatchingInput("一。二。三。四。", edited_plan, "", "", ""),
            resume_adapter,
            resume_from=first.snapshot,
        )

        self.assertTrue(resumed.renderable)
        self.assertEqual(
            ["segment-1", "segment-2", "segment-3"],
            resume_adapter.matched_segment_ids,
        )
        self.assertEqual("segment-4", resumed.items[3]["_segment_id"])


if __name__ == "__main__":
    unittest.main()

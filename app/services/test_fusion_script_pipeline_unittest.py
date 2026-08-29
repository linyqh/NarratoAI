import unittest

from app.services.fusion_script_pipeline import FusionScriptPipeline


class FusionScriptPipelineTests(unittest.TestCase):
    @staticmethod
    def _segment(segment_id, sentence_start, sentence_end, core_window, **extra):
        return {
            "segment_id": segment_id,
            "sentence_start": sentence_start,
            "sentence_end": sentence_end,
            "core_window": core_window,
            "active_subject": "主角",
            "entering_state": "面临当前危机",
            "trigger_event": "发生新的事件",
            "exiting_state": "必须做出下一步选择",
            **extra,
        }

    def test_reports_unmarked_forward_jump_over_150_seconds(self):
        plan = {
            "segments": [
                self._segment("segment-1", 1, 1, "00:00:00,000-00:00:20,000", exception_reason="测试"),
                self._segment("segment-2", 2, 2, "00:03:00,001-00:03:20,000", exception_reason="测试"),
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。第二句。", plan)

        self.assertFalse(report.is_renderable)
        self.assertEqual("unmarked_large_forward_jump", report.findings[0].code)
        self.assertEqual("segment-2", report.findings[0].segment_id)

    def test_accepts_large_jump_with_a_narrative_bridge(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    exception_reason="测试", bridge_to_next=True,
                    bridge_reason="解说交代幸存者转移到下一个阶段",
                ),
                self._segment("segment-2", 2, 2, "00:03:00,001-00:03:20,000", exception_reason="测试"),
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。第二句。", plan)

        self.assertTrue(report.is_renderable)

    def test_requires_a_bridge_when_the_active_subject_changes(self):
        plan = {
            "segments": [
                self._segment("segment-1", 1, 1, "00:00:00,000-00:00:20,000", exception_reason="测试"),
                self._segment("segment-2", 2, 2, "00:00:21,000-00:00:40,000", exception_reason="测试", active_subject="反派"),
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。第二句。", plan)

        self.assertFalse(report.is_renderable)
        self.assertEqual("unbridged_active_subject_change", report.findings[0].code)

    def test_rejects_reverse_time_order_without_nonlinear_cue(self):
        plan = {
            "segments": [
                self._segment("segment-1", 1, 1, "00:03:00,000-00:03:20,000", exception_reason="测试"),
                self._segment("segment-2", 2, 2, "00:01:00,000-00:01:20,000", exception_reason="测试"),
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。第二句。", plan)

        self.assertEqual("unmarked_nonlinear_transition", report.findings[0].code)

    def test_accepts_reverse_time_order_with_nonlinear_mode_and_cue(self):
        plan = {
            "segments": [
                self._segment("segment-1", 1, 1, "00:03:00,000-00:03:20,000", exception_reason="测试"),
                self._segment(
                    "segment-2", 2, 2, "00:01:00,000-00:01:20,000",
                    exception_reason="测试", narrative_mode="flashback",
                    narration_cue="时间回到灾难发生之前。",
                ),
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。第二句。", plan)

        self.assertTrue(report.is_renderable)

    def test_reports_a_segment_without_a_complete_story_beat(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    exception_reason="测试", trigger_event="",
                )
            ]
        }

        report = FusionScriptPipeline().validate_continuity("第一句。", plan)

        self.assertFalse(report.is_renderable)
        self.assertEqual("incomplete_story_beat", report.findings[0].code)
        self.assertEqual("segment-1", report.findings[0].segment_id)

    def test_matches_approved_plan_with_local_evidence_and_retries_only_failed_segment(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    story_role="开场钩子", exception_reason="测试用单句开场",
                ),
                self._segment(
                    "segment-2", 2, 2, "00:00:40,000-00:01:00,000",
                    story_role="危机升级", exception_reason="测试用单句转折",
                ),
            ]
        }
        attempts = []

        def matcher(request):
            attempts.append(request.segment_id)
            if request.segment_id == "segment-2" and attempts.count("segment-2") == 1:
                raise RuntimeError("temporary provider failure")
            return {
                "items": [
                    {
                        "video_id": 1,
                        "video_name": "film.mp4",
                        "timestamp": request.core_window,
                        "picture": f"{request.segment_id} 画面",
                        "narration": request.narration,
                        "OST": 0,
                    }
                ],
                "evidence_conflicts": [],
            }

        result = FusionScriptPipeline().match_approved_plan(
            narration_copy="第一句。第二句。",
            plan_payload=plan,
            subtitle_evidence="00:00:00,000 --> 00:01:00,000\n字幕事实",
            visual_evidence=(
                "## 00:00:00,000-00:00:20,000\n- 画面摘要：开场画面\n\n"
                "## 00:00:40,000-00:01:00,000\n- 画面摘要：危机画面"
            ),
            highlight_candidates=(
                "- 00:00:40,000-00:00:45,000｜动作场面｜价值 5/5：人物奔跑。"
            ),
            matcher=matcher,
        )

        self.assertEqual(1, attempts.count("segment-1"))
        self.assertEqual(2, attempts.count("segment-2"))
        self.assertEqual(["第一句。", "第二句。"], [item["narration"] for item in result.items])
        self.assertEqual([1, 2], [item["_id"] for item in result.items])
        self.assertIn("开场画面", result.requests[0].visual_evidence)
        self.assertNotIn("危机画面", result.requests[0].visual_evidence)
        self.assertIn("人物奔跑", result.requests[1].highlight_candidates)

    def test_rejects_a_plan_that_does_not_cover_every_narration_sentence(self):
        with self.assertRaisesRegex(ValueError, "cover"):
            FusionScriptPipeline().match_approved_plan(
                narration_copy="第一句。第二句。",
                plan_payload={
                    "segments": [
                        self._segment(
                            "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                            exception_reason="测试不完整计划",
                        )
                    ]
                },
                subtitle_evidence="00:00:00,000 --> 00:00:20,000\n字幕事实",
                visual_evidence="## 00:00:00,000-00:00:20,000\n- 画面摘要：开场画面",
                highlight_candidates="",
                matcher=lambda _request: {"items": [], "evidence_conflicts": []},
            )

    def test_checkpoints_successful_in_flight_segments_before_reporting_a_failure(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    exception_reason="测试用单句检查点",
                ),
                self._segment(
                    "segment-2", 2, 2, "00:00:20,000-00:00:40,000",
                    exception_reason="测试用单句检查点",
                ),
            ]
        }
        completed_segments = []

        def matcher(request):
            if request.segment_id == "segment-2":
                raise RuntimeError("provider failure")
            return {
                "items": [
                    {
                        "timestamp": request.core_window,
                        "narration": request.narration,
                        "OST": 0,
                    }
                ]
            }

        with self.assertRaisesRegex(RuntimeError, "segment-2"):
            FusionScriptPipeline().match_approved_plan(
                narration_copy="第一句。第二句。",
                plan_payload=plan,
                subtitle_evidence="",
                visual_evidence="",
                highlight_candidates="",
                matcher=matcher,
                on_segment_complete=lambda request, _response: completed_segments.append(
                    request.segment_id
                ),
            )

        self.assertEqual(["segment-1"], completed_segments)

    def test_rejects_more_than_one_original_sound_highlight_in_a_story_beat(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    exception_reason="测试用单句高光配额",
                )
            ]
        }

        with self.assertRaisesRegex(ValueError, "at most one original-sound highlight"):
            FusionScriptPipeline().match_approved_plan(
                narration_copy="第一句。",
                plan_payload=plan,
                subtitle_evidence="",
                visual_evidence="",
                highlight_candidates="",
                matcher=lambda request: {
                    "items": [
                        {"timestamp": "00:00:00,000-00:00:04,000", "narration": request.narration, "OST": 1},
                        {"timestamp": "00:00:05,000-00:00:09,000", "narration": request.narration, "OST": 1},
                    ]
                },
            )

    def test_rejects_an_original_sound_highlight_over_40_percent_of_a_story_beat(self):
        plan = {
            "segments": [
                self._segment(
                    "segment-1", 1, 1, "00:00:00,000-00:00:20,000",
                    exception_reason="测试用单句高光时长",
                )
            ]
        }

        with self.assertRaisesRegex(ValueError, "exceeds 40%"):
            FusionScriptPipeline().match_approved_plan(
                narration_copy="第一句。",
                plan_payload=plan,
                subtitle_evidence="",
                visual_evidence="",
                highlight_candidates="",
                matcher=lambda request: {
                    "items": [
                        {"timestamp": "00:00:00,000-00:00:09,000", "narration": request.narration, "OST": 1},
                    ]
                },
            )

    def test_rejects_duplicate_segment_ids(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            FusionScriptPipeline().validate_plan(
                "第一句。第二句。",
                {
                    "segments": [
                        self._segment(
                            "same", 1, 1, "00:00:00,000-00:00:20,000",
                            exception_reason="测试唯一性",
                        ),
                        self._segment(
                            "same", 2, 2, "00:00:20,000-00:00:40,000",
                            exception_reason="测试唯一性",
                        ),
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()

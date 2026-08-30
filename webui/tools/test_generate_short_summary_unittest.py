import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.services.fusion_script_finalizer import FusionScriptFinalizer
from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.services.documentary.local_analysis_tasks import LocalAnalysisTaskStore
from app.services.fusion_models import CandidateRejection, EvidenceConflict, FinalizationRequest, HighlightCandidateIntake
from webui.tools import generate_short_summary
from webui.tools.generate_short_summary import _format_progress_status, parse_and_fix_json


class GenerateShortSummaryJsonTests(unittest.TestCase):
    def test_fusion_stream_preview_is_bounded_to_the_ui_limit(self):
        prefix = "a" * 2000
        preview = generate_short_summary._append_fusion_stream_preview(prefix, "b" * 1000)

        self.assertEqual(generate_short_summary.FUSION_STREAM_PREVIEW_LIMIT, len(preview))
        self.assertEqual("a" * 800 + "b" * 1000, preview)

    def _finalize(self, **kwargs):
        candidates = tuple(
            HighlightCandidate(
                time_range=TimeRange.parse(item["time_range"]), category=item["category"],
                reason=item["reason"], score=item["score"], video_id=item.get("video_id"),
                video_name=item.get("video_name", ""), candidate_id=item.get("candidate_id", ""),
            )
            for item in kwargs.pop("highlight_candidates", [])
        )
        rejections = tuple(CandidateRejection(**item) for item in kwargs.pop("candidate_rejections", []))
        conflicts = tuple(EvidenceConflict.from_mapping(item) for item in kwargs.pop("evidence_conflicts", []))
        return FusionScriptFinalizer().finalize(FinalizationRequest(
            script=tuple(kwargs.pop("script", [])),
            requested_original_sound_ratio=kwargs.pop("requested_original_sound_ratio", 0),
            candidate_intake=HighlightCandidateIntake(candidates, rejections, len(candidates) + len(rejections)),
            evidence_conflicts=conflicts,
            source_durations=kwargs.pop("source_durations", {}),
        ))

    def test_progress_message_does_not_prefix_fake_percentage(self):
        status = _format_progress_status(60, "正在生成文案...")

        self.assertEqual("正在生成文案...", status)
        self.assertNotIn("60%", status)

    def test_invalid_json_does_not_create_default_fake_script(self):
        self.assertIsNone(parse_and_fix_json("not a json response"))

    def test_json_code_block_is_parsed(self):
        parsed = parse_and_fix_json(
            """```json
{"items": [{"_id": 1, "timestamp": "00:00:01,000-00:00:02,000"}]}
```"""
        )

        self.assertEqual(1, parsed["items"][0]["_id"])

    def test_repair_does_not_corrupt_timestamp_values(self):
        parsed = parse_and_fix_json(
            """```json
{
  items: [
    {_id: 1, timestamp: "00:00:01,000-00:00:02,000",},
  ],
}
```"""
        )

        self.assertEqual("00:00:01,000-00:00:02,000", parsed["items"][0]["timestamp"])

    def test_finalization_result_enters_review_state_before_rendering(self):
        result = self._finalize(
            script=[
                {
                    "_id": 1,
                    "video_id": 1,
                    "video_name": "film.mp4",
                    "timestamp": "00:00:00,000-00:00:10,000",
                    "picture": "开场",
                    "narration": "开场。",
                    "OST": 0,
                }
            ],
            requested_original_sound_ratio=0,
            highlight_candidates=[],
            evidence_conflicts=[
                {
                    "video_name": "film.mp4",
                    "time_range": "00:00:02,000-00:00:03,000",
                    "subtitle_claim": "字幕事实",
                    "visual_observation": "画面事实",
                    "severity": "medium",
                    "status": "unresolved",
                }
            ],
            source_durations={"film.mp4": 10.0},
        )
        review_state = {}
        with (
            patch.object(generate_short_summary.st, "session_state", review_state),
            patch.object(
                generate_short_summary,
                "_persist_fusion_generation_result",
                return_value="audit.json",
            ) as persist,
        ):
            audit_path = generate_short_summary._store_fusion_finalization_result(result)

        self.assertEqual("audit.json", audit_path)
        self.assertEqual(result.evidence_conflicts, review_state["fusion_evidence_conflicts"])
        self.assertEqual(1, review_state["fusion_finalization_report"]["unresolved_conflict_count"])
        self.assertEqual("audit.json", review_state["fusion_generation_audit_path"])
        self.assertEqual(result.script, persist.call_args.args[0]["finalized_script"])

    def test_background_match_finalization_returns_a_renderable_script(self):
        result = generate_short_summary.finalize_fusion_matching_result(
            matched_plan={
                "items": [
                    {
                        "_id": 1,
                        "video_id": 1,
                        "video_name": "film.mp4",
                        "timestamp": "00:00:00,000-00:00:10,000",
                        "picture": "人物在废墟中前进。",
                        "narration": "人物在废墟中前进。",
                        "OST": 0,
                    }
                ],
                "evidence_conflicts": [],
                "continuity_report": {"is_renderable": True, "findings": []},
            },
            finalization_context={
                "candidate_payloads": [],
                "candidate_rejections": [],
                "original_sound_ratio": 0,
                "source_durations": {"film.mp4": 10.0},
            },
        )

        self.assertTrue(result["renderable"])
        self.assertEqual("人物在废墟中前进。", result["finalized_script"][0]["picture"])
        self.assertTrue(result["continuity_report"]["is_renderable"])

    def test_background_match_stays_out_of_finalization_when_continuity_is_unreviewable(self):
        result = generate_short_summary.finalize_fusion_matching_result(
            matched_plan={
                "items": [{"_id": 1, "timestamp": "00:00:00,000-00:00:10,000"}],
                "evidence_conflicts": [],
                "continuity_report": {
                    "is_renderable": False,
                    "findings": [{"code": "unbridged_merged_source_jump"}],
                },
            },
            finalization_context={},
        )

        self.assertFalse(result["renderable"])
        self.assertEqual("blocked_for_continuity_review", result["status"])
        self.assertEqual([], result["finalized_script"])

    def test_planning_repairs_a_continuity_failure_once_before_creator_approval(self):
        base_segment = {
            "active_subject": "主角",
            "entering_state": "面临当前危机",
            "trigger_event": "发生新的事件",
            "exiting_state": "必须做出下一步选择",
            "exception_reason": "测试单句边界",
        }
        invalid_plan = {
            "segments": [
                {**base_segment, "segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1, "core_window": "00:00:00,000-00:00:20,000"},
                {**base_segment, "segment_id": "segment-2", "sentence_start": 2, "sentence_end": 2, "core_window": "00:03:00,001-00:03:20,000"},
            ]
        }
        repaired_plan = json.loads(json.dumps(invalid_plan))
        repaired_plan["segments"][0]["bridge_to_next"] = True
        repaired_plan["segments"][0]["bridge_reason"] = "解说交代主角转移到下一阶段。"
        repaired_plan["segments"][1]["handoff_from_previous"] = {
            "actor": "continuous", "place": "changed", "goal": "changed",
            "cause": "changed", "state": "changed",
        }
        analyzer = Mock()
        analyzer.plan_narration_segments.return_value = json.dumps(invalid_plan, ensure_ascii=False)
        analyzer.repair_fusion_segment_plan.return_value = json.dumps(repaired_plan, ensure_ascii=False)

        result = generate_short_summary.create_fusion_segment_plan(
            analyzer=analyzer,
            short_name="测试影片",
            plot_analysis="剧情概要",
            subtitle_content="字幕事实",
            narration_copy="第一句。第二句。",
            narration_language="简体中文（中国）",
            drama_genre="剧情",
            visual_evidence="",
            highlight_candidates="",
            temperature=0.3,
        )

        self.assertTrue(result["segments"][0]["bridge_to_next"])
        analyzer.repair_fusion_segment_plan.assert_called_once()

    def test_fusion_segment_plan_forwards_the_live_stream_callback(self):
        valid_plan = {
            "segments": [
                {
                    "segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1,
                    "core_window": "00:00:00,000-00:00:20,000", "active_subject": "主角",
                    "entering_state": "危机", "trigger_event": "事件", "exiting_state": "选择",
                    "exception_reason": "测试单句边界",
                }
            ]
        }
        analyzer = Mock()
        analyzer.plan_narration_segments.return_value = json.dumps(valid_plan, ensure_ascii=False)
        callback = Mock()

        generate_short_summary.create_fusion_segment_plan(
            analyzer=analyzer,
            short_name="测试影片",
            plot_analysis="剧情概要",
            subtitle_content="字幕事实",
            narration_copy="第一句。",
            narration_language="简体中文（中国）",
            drama_genre="剧情",
            visual_evidence="视觉事实",
            highlight_candidates="",
            temperature=0.3,
            stream_callback=callback,
        )

        self.assertIs(callback, analyzer.plan_narration_segments.call_args.kwargs["stream_callback"])

    def test_fusion_segment_plan_retries_one_timeout_after_backoff(self):
        valid_plan = {
            "segments": [
                {
                    "segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1,
                    "core_window": "00:00:00,000-00:00:20,000", "active_subject": "主角",
                    "entering_state": "危机", "trigger_event": "事件", "exiting_state": "选择",
                    "exception_reason": "测试单句边界",
                }
            ]
        }
        analyzer = Mock()
        analyzer.plan_narration_segments.side_effect = [
            RuntimeError("Request timed out."),
            json.dumps(valid_plan, ensure_ascii=False),
        ]

        with patch.object(generate_short_summary.time, "sleep") as sleep:
            result = generate_short_summary.create_fusion_segment_plan(
                analyzer=analyzer,
                short_name="测试影片",
                plot_analysis="剧情概要",
                subtitle_content="字幕事实",
                narration_copy="第一句。",
                narration_language="简体中文（中国）",
                drama_genre="剧情",
                visual_evidence="视觉事实",
                highlight_candidates="",
                temperature=0.3,
            )

        self.assertEqual("segment-1", result["segments"][0]["segment_id"])
        self.assertEqual(2, analyzer.plan_narration_segments.call_count)
        sleep.assert_called_once_with(1.0)

    def test_fusion_match_forwards_segment_stream_and_attempt_callbacks(self):
        plan = {
            "segments": [
                {
                    "segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1,
                    "core_window": "00:00:00,000-00:00:20,000", "active_subject": "主角",
                    "entering_state": "危机", "trigger_event": "事件", "exiting_state": "选择",
                    "exception_reason": "测试单句边界",
                }
            ]
        }
        approval = generate_short_summary.approve_fusion_segment_plan(
            plan_payload=plan, narration_copy="第一句。", source_identity={}
        )

        class StreamingAnalyzer:
            def match_narration_copy_to_script(self, **kwargs):
                kwargs["stream_callback"]({"type": "content", "text": "partial"})
                return {
                    "status": "success",
                    "narration_script": json.dumps(
                        {
                            "items": [
                                {
                                    "_id": 1, "video_id": 1, "video_name": "film.mp4",
                                    "timestamp": "00:00:00,000-00:00:05,000",
                                    "picture": "主角行动。", "narration": "第一句。", "OST": 0,
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                }

        stream_events = []
        attempts = []
        result = generate_short_summary.match_approved_fusion_segment_plan(
            analyzer=StreamingAnalyzer(),
            short_name="测试影片",
            narration_copy="第一句。",
            narration_language="简体中文（中国）",
            drama_genre="剧情",
            original_sound_ratio=0,
            subtitle_content="字幕事实",
            visual_evidence="视觉事实",
            highlight_candidates="",
            plan_payload=plan,
            temperature=0.3,
            plan_approval=approval,
            on_segment_attempt=lambda segment, count: attempts.append((segment.segment_id, count)),
            on_stream_chunk=lambda segment, event: stream_events.append((segment.segment_id, event)),
        )

        self.assertEqual([("segment-1", 1)], attempts)
        self.assertEqual(
            [("segment-1", {"type": "content", "text": "partial"})], stream_events
        )
        self.assertEqual("第一句。", result["items"][0]["narration"])

    def test_fusion_matching_task_exposes_transient_stream_snapshot_then_clears_it(self):
        plan = {
            "segments": [
                {
                    "segment_id": "segment-1", "sentence_start": 1, "sentence_end": 1,
                    "core_window": "00:00:00,000-00:00:20,000", "active_subject": "主角",
                    "entering_state": "危机", "trigger_event": "事件", "exiting_state": "选择",
                    "exception_reason": "测试单句边界",
                }
            ]
        }
        approval = generate_short_summary.approve_fusion_segment_plan(
            plan_payload=plan, narration_copy="第一句。", source_identity={}
        )

        def fake_match(**kwargs):
            segment = type("Segment", (), {"segment_id": "segment-1"})()
            kwargs["on_stream_chunk"](segment, {"type": "content", "text": "partial"})
            time.sleep(0.1)
            return {"items": [], "matching_snapshot": {}}

        with tempfile.TemporaryDirectory() as directory:
            store = LocalAnalysisTaskStore(Path(directory))
            with (
                patch.object(generate_short_summary, "_fusion_matching_task_store", return_value=store),
                patch.object(generate_short_summary, "match_approved_fusion_segment_plan", side_effect=fake_match),
                patch.object(
                    generate_short_summary,
                    "finalize_fusion_matching_result",
                    return_value={"renderable": True, "finalized_script": []},
                ),
            ):
                task_id = generate_short_summary.start_fusion_matching_task(
                    short_name="测试影片", narration_copy="第一句。",
                    narration_language="简体中文（中国）", drama_genre="剧情",
                    original_sound_ratio=0, subtitle_content="字幕事实", visual_evidence="视觉事实",
                    highlight_candidates="", plan_payload=plan, plan_approval=approval,
                    temperature=0.3, source_identity={}, finalization_context={},
                )
                deadline = time.monotonic() + 2
                observed = None
                while time.monotonic() < deadline:
                    task = generate_short_summary.fusion_matching_task_status(task_id)
                    snapshot = task.get("stream_snapshot") or {}
                    if snapshot.get("content_text") == "partial":
                        observed = snapshot
                    if task.get("status") in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.01)
                final_task = generate_short_summary.fusion_matching_task_status(task_id)

        self.assertEqual("matching", observed["phase"])
        self.assertEqual("segment-1", observed["segment_id"])
        self.assertEqual("completed", final_task["status"])
        self.assertIsNone(final_task.get("stream_snapshot"))

    def test_conflict_without_video_name_receives_the_selected_source_identity(self):
        source_identity = {"algorithm": "sha256", "sha256": "a" * 64, "size_bytes": 12}

        conflicts = generate_short_summary._normalize_fusion_evidence_conflicts(
            [
                {
                    "time_range": "00:00:02,000-00:00:03,000",
                    "subtitle_claim": "字幕事实",
                    "visual_observation": "画面事实",
                    "severity": "medium",
                    "status": "acknowledged",
                }
            ],
            default_video_name="film.mp4",
            identity_by_video={},
            default_source_identity=source_identity,
        )

        self.assertEqual("film.mp4", conflicts[0].video_name)
        self.assertEqual(source_identity, conflicts[0].source_video_identity)
        self.assertEqual("acknowledged", conflicts[0].status)

    def test_acknowledged_conflict_survives_finalization_without_redacting_the_script(self):
        result = self._finalize(
            script=[
                {"_id": 1, "video_id": 1, "video_name": "film.mp4", "timestamp": "00:00:00,000-00:00:10,000", "picture": "人物站立。", "narration": "人物站立。", "OST": 0}
            ],
            requested_original_sound_ratio=0,
            highlight_candidates=[],
            evidence_conflicts=[{"video_name": "film.mp4", "time_range": "00:00:02,000-00:00:03,000", "subtitle_claim": "字幕事实", "visual_observation": "画面事实", "severity": "medium", "status": "acknowledged"}],
            source_durations={"film.mp4": 10.0},
        )

        self.assertEqual("acknowledged", result.evidence_conflicts[0]["status"])
        self.assertEqual("人物站立。", result.script[0]["picture"])
        self.assertEqual(0, result.report.unresolved_conflict_count)
        self.assertEqual(1, result.report.acknowledged_conflict_count)

    def test_acknowledging_an_audit_updates_both_conflict_counts(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as audit_file:
            json.dump({"evidence_conflicts": [], "finalization_report": {"unresolved_conflict_count": 1}}, audit_file)
            audit_path = audit_file.name
        try:
            generate_short_summary.acknowledge_fusion_audit(audit_path, [{"status": "acknowledged"}])
            with open(audit_path, encoding="utf-8") as audit_file:
                report = json.load(audit_file)["finalization_report"]
            self.assertEqual(0, report["unresolved_conflict_count"])
            self.assertEqual(1, report["acknowledged_conflict_count"])
        finally:
            os.unlink(audit_path)

    def test_malformed_conflict_cannot_cross_the_domain_boundary(self):
        with self.assertRaisesRegex(ValueError, "time range"):
            generate_short_summary._normalize_fusion_evidence_conflicts(
                [
                    {
                        "subtitle_claim": "字幕事实",
                        "visual_observation": "画面事实",
                        "severity": "medium",
                    }
                ],
                default_video_name="film.mp4",
                identity_by_video={},
            )

    def test_regression_only_audit_persists_the_source_identity_waiver(self):
        result = self._finalize(
            script=[],
            requested_original_sound_ratio=0,
            highlight_candidates=[],
            evidence_conflicts=[],
            source_durations={},
        )
        with (
            patch.object(generate_short_summary.st, "session_state", {}),
            patch.object(
                generate_short_summary,
                "_persist_fusion_generation_result",
                return_value="audit.json",
            ) as persist,
        ):
            generate_short_summary._store_fusion_finalization_result(
                result,
                regression_only=True,
                source_verified=False,
            )

        payload = persist.call_args.args[0]
        self.assertEqual("regression_only", payload["status"])
        self.assertTrue(payload["regression_only"])
        self.assertTrue(payload["source_identity_waiver"])
        self.assertFalse(payload["source_verified"])


if __name__ == "__main__":
    unittest.main()

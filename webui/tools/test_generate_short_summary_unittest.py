import unittest
from unittest.mock import patch

from app.services.fusion_script_finalizer import FusionScriptFinalizer
from webui.tools import generate_short_summary
from webui.tools.generate_short_summary import _format_progress_status, parse_and_fix_json


class GenerateShortSummaryJsonTests(unittest.TestCase):
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
        result = FusionScriptFinalizer().finalize(
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
        self.assertEqual("unresolved", conflicts[0].status)

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
        result = FusionScriptFinalizer().finalize(
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

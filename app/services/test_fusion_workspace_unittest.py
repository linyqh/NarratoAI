import unittest

from app.services.fusion_workspace import (
    compare_fusion_versions,
    locate_fusion_review_item,
    project_fusion_review_context,
    project_fusion_task_center_details,
    project_fusion_workspace,
)


class FusionWorkspaceProjectionTests(unittest.TestCase):
    def test_blockers_precede_warnings_and_quality_suggestions(self):
        workspace = project_fusion_workspace(
            task={"task_id": "task-1", "status": "failed", "stream_snapshot": {"failure_category": "timed_out_after_progress"}},
            finalization={"preflight": {"blockers": [{"code": "segment_match_failed"}], "warnings": [{"code": "unresolved_evidence_conflict"}]}},
            quality_findings=[{"code": "repetitive_narration"}],
        )

        self.assertEqual("blocked", workspace["phase"])
        self.assertEqual(["blocker", "warning", "quality"], [item["kind"] for item in workspace["review_queue"]])
        self.assertEqual("timed_out_after_progress", workspace["task_center"]["failure_category"])

    def test_renderable_finalization_projects_an_approved_workspace(self):
        workspace = project_fusion_workspace(finalization={
            "renderable": True, "preflight": {}, "active_version_id": "finalized-script"
        })

        self.assertEqual("approved", workspace["phase"])
        self.assertEqual([], workspace["review_queue"])
        self.assertEqual("finalized-script", workspace["active_version_id"])

    def test_task_center_details_expose_actions_and_bounded_diagnostics(self):
        detail = project_fusion_task_center_details({
            "task_id": "task-1",
            "status": "interrupted",
            "progress": 0.5,
            "error_message": "retry needed",
            "request": {"api_key": "must-not-leak"},
            "stream_snapshot": {
                "failure_category": "timed_out_after_progress",
                "failure_diagnostics": {"last_chunk_at": 1},
            },
            "segment_matches": [{"segment_id": "segment-1", "status": "failed"}],
        })

        self.assertTrue(detail["can_resume"])
        self.assertFalse(detail["can_cancel"])
        self.assertEqual("timed_out_after_progress", detail["failure_category"])
        self.assertNotIn("request", detail)

    def test_selected_review_item_resolves_to_its_evidence_window(self):
        location = locate_fusion_review_item(
            narrative_map={"beats": [{"segment_id": "segment-2", "evidence_window": "00:01:00,000-00:01:10,000", "active_subject": "主角"}]},
            segment_id="segment-2",
        )

        self.assertEqual("00:01:00,000-00:01:10,000", location["time_range"])

    def test_review_context_links_one_segment_to_timeline_and_evidence(self):
        context = project_fusion_review_context(
            task={
                "request": {
                    "plan_payload": {"segments": [{
                        "segment_id": "segment-1",
                        "core_window": "00:00:00,000-00:00:10,000",
                    }]},
                    "subtitle_content": "1\n00:00:01,000 --> 00:00:02,000\n字幕内容",
                    "visual_evidence": "## 00:00:01,000-00:00:02,000\n画面内容",
                    "highlight_candidates": "00:00:01,000-00:00:02,000 | 高光",
                }
            },
            finalization={
                "narrative_map": {"beats": [{"segment_id": "segment-1", "active_subject": "主角"}]},
                "finalized_script": [{
                    "_id": 1, "_segment_id": "segment-1", "timestamp": "00:00:01,000-00:00:02,000",
                    "narration": "旁白", "picture": "画面", "OST": 0,
                }],
            },
            segment_id="segment-1",
        )

        self.assertEqual("主角", context["story_beat"]["active_subject"])
        self.assertEqual("旁白", context["timeline_items"][0]["narration"])
        self.assertIn("字幕内容", context["subtitle_evidence"])
        self.assertIn("画面内容", context["visual_evidence"])
        self.assertIn("高光", context["highlight_candidates"])

    def test_version_comparison_reports_renderability_and_script_changes(self):
        comparison = compare_fusion_versions(
            versions=[
                {
                    "version_id": "before-repair",
                    "kind": "finalized_script",
                    "snapshot": {
                        "finalized_script": [{"_id": 1, "narration": "旧解说"}],
                        "renderable": True,
                        "preflight": {"blockers": [], "warnings": []},
                        "narrative_quality_findings": [{"code": "repetitive_narration"}],
                    },
                },
                {
                    "version_id": "after-repair",
                    "kind": "quality_repair_output",
                    "snapshot": {
                        "finalized_script": [{"_id": 1, "narration": "新解说"}, {"_id": 2}],
                        "renderable": False,
                        "preflight": {"blockers": [{"code": "evidence_conflict"}], "warnings": []},
                        "narrative_quality_findings": [],
                    },
                },
            ],
            baseline_version_id="before-repair",
            candidate_version_id="after-repair",
        )

        self.assertTrue(comparison["changed"])
        self.assertIn("script", comparison["changed_fields"])
        self.assertIn("renderable", comparison["changed_fields"])
        self.assertEqual(1, comparison["baseline"]["script_item_count"])
        self.assertEqual(2, comparison["candidate"]["script_item_count"])

    def test_version_comparison_reports_ost_conflict_and_range_changes(self):
        comparison = compare_fusion_versions(
            versions=[
                {"version_id": "before", "snapshot": {
                    "finalized_script": [{"timestamp": "00:00:00,000-00:00:10,000", "OST": 0}],
                    "evidence_conflicts": [],
                }},
                {"version_id": "after", "snapshot": {
                    "finalized_script": [{"timestamp": "00:00:10,000-00:00:20,000", "OST": 1}],
                    "evidence_conflicts": [{"severity": "medium", "time_range": "00:00:10,000-00:00:11,000", "status": "unresolved"}],
                }},
            ],
            baseline_version_id="before",
            candidate_version_id="after",
        )

        self.assertTrue({"ost_ratio", "evidence_conflicts", "timeline_ranges"}.issubset(comparison["changed_fields"]))

    def test_ignored_quality_finding_leaves_blockers_and_warnings_in_queue(self):
        workspace = project_fusion_workspace(
            finalization={
                "preflight": {
                    "blockers": [{"code": "segment_match_failed"}],
                    "warnings": [{"code": "evidence_conflict"}],
                },
                "narrative_quality_findings": [
                    {"code": "repetitive_narration", "segment_id": "segment-2"}
                ],
                "review_decisions": [
                    {
                        "kind": "quality",
                        "action": "ignored",
                        "segment_id": "segment-2",
                        "code": "repetitive_narration",
                    }
                ],
            }
        )

        self.assertEqual(["blocker", "warning"], [item["kind"] for item in workspace["review_queue"]])


if __name__ == "__main__":
    unittest.main()

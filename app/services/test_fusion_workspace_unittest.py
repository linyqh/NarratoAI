import unittest

from app.services.fusion_workspace import (
    compare_fusion_versions,
    locate_fusion_review_item,
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
        workspace = project_fusion_workspace(finalization={"renderable": True, "preflight": {}})

        self.assertEqual("approved", workspace["phase"])
        self.assertEqual([], workspace["review_queue"])

    def test_selected_review_item_resolves_to_its_evidence_window(self):
        location = locate_fusion_review_item(
            narrative_map={"beats": [{"segment_id": "segment-2", "evidence_window": "00:01:00,000-00:01:10,000", "active_subject": "主角"}]},
            segment_id="segment-2",
        )

        self.assertEqual("00:01:00,000-00:01:10,000", location["time_range"])

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

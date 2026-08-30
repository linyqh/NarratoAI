import unittest

from app.services.fusion_workspace import locate_fusion_review_item, project_fusion_workspace


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


if __name__ == "__main__":
    unittest.main()

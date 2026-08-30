import unittest

from app.services.fusion_workspace import project_fusion_workspace


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


if __name__ == "__main__":
    unittest.main()

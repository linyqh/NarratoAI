import tempfile
import unittest
from pathlib import Path

from app.services.fusion_projects import FusionProjectStore, project_projection


class FusionProjectStoreTests(unittest.TestCase):
    def test_project_survives_reopening_and_preserves_local_source_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("电影解说项目")
            project = store.update(
                project["project_id"],
                source_video_sequence=[
                    {
                        "source_id": "source-1",
                        "kind": "local_reference",
                        "path": "D:/movies/example.mp4",
                        "available": True,
                    }
                ],
            )

            reopened = FusionProjectStore(Path(directory)).read(project["project_id"])
            store.trash(project["project_id"])

        self.assertEqual("电影解说项目", reopened["name"])
        self.assertEqual("D:/movies/example.mp4", reopened["source_video_sequence"][0]["path"])

    def test_projection_uses_blocker_before_running_task_status(self):
        project = {
            "project_id": "project1",
            "name": "测试",
            "trash_state": None,
            "review_decisions": [],
            "task_refs": [{"status": "running"}],
            "review_findings": [{"severity": "blocker", "status": "open"}],
            "render_outcomes": [],
            "active_stage": "review",
        }

        projection = project_projection(project)

        self.assertEqual("blocked", projection["status"])
        self.assertEqual("Resolve review blocker", projection["next_action"])

    def test_task_result_with_old_input_version_becomes_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("版本项目")
            store.update(project["project_id"], active_version_id="version-2")

            result = store.admit_task_result(
                project["project_id"],
                task_id="task-1",
                input_version_id="version-1",
                artifact_ref="artifact-1",
            )

        self.assertEqual("stale", result["admission"])

    def test_applying_content_draft_creates_version_and_invalidates_dependents(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("草稿项目")
            store.update(
                project["project_id"],
                artifact_refs={"narration": "old", "segment_matches": ["match-1"]},
            )
            draft = store.save_content_draft(
                project["project_id"], kind="narration", content="new narration"
            )

            impact = store.preview_draft_impact(project["project_id"], draft["draft_id"])
            applied = store.apply_content_draft(
                project["project_id"], draft["draft_id"], impact_confirmed=True
            )

        self.assertIn("segment_matches", impact["invalidated_artifacts"])
        self.assertEqual("new narration", applied["artifact_refs"]["narration"])
        self.assertTrue(applied["active_version_id"])
        self.assertNotIn("segment_matches", applied["artifact_refs"])

    def test_review_decision_can_be_undone_and_render_outcomes_are_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("审核项目")
            store.update(project["project_id"], active_version_id="version-1")
            decision = store.record_review_decision(
                project["project_id"], finding_id="finding-1", action="acknowledge"
            )
            undone = store.undo_review_decision(project["project_id"], decision["decision_id"])
            first = store.add_render_outcome(
                project["project_id"], media_path="first.mp4", preflight={"blockers": []}
            )
            second = store.add_render_outcome(
                project["project_id"], media_path="second.mp4", preflight={"blockers": []}
            )

        self.assertEqual("undone", undone["review_decisions"][0]["status"])
        self.assertNotEqual(first["outcome_id"], second["outcome_id"])
        self.assertEqual(2, len(second["project"]["render_outcomes"]))

    def test_managed_asset_is_copied_into_project_and_local_reference_is_never_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FusionProjectStore(root / "projects")
            project = store.create("素材项目")

            managed = store.add_managed_asset(
                project["project_id"], filename="../unsafe movie.mp4", content=b"video"
            )
            referenced = store.add_local_reference(
                project["project_id"], path=str(root / "original.mp4")
            )
            plan = store.permanent_delete_plan(project["project_id"])

            managed_content = Path(managed["path"]).read_bytes()

        self.assertEqual("managed_asset", managed["kind"])
        self.assertEqual("unsafe movie.mp4", Path(managed["path"]).name)
        self.assertEqual(b"video", managed_content)
        self.assertEqual("local_reference", referenced["kind"])
        self.assertIn(referenced["path"], plan["referenced_local_sources_preserved"])

    def test_refresh_source_availability_detects_offline_and_reconnected_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FusionProjectStore(root / "projects")
            project = store.create("离线检测")
            movie = root / "movie.mp4"
            source = store.add_local_reference(project["project_id"], path=str(movie))
            self.assertFalse(source["available"])

            movie.write_bytes(b"video")
            refreshed = store.refresh_source_availability(project["project_id"])

        self.assertTrue(refreshed["source_video_sequence"][0]["available"])
        self.assertTrue(refreshed["source_video_sequence"][0]["identity"]["size"])

    def test_stage_readiness_explains_why_matching_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("阶段检查")

            readiness = store.stage_readiness(project["project_id"])

        self.assertFalse(readiness["matching"]["ready"])
        self.assertIn("解说词", readiness["matching"]["blockers"])
        self.assertIn("Fusion Segment Plan", readiness["matching"]["blockers"])

    def test_archive_rename_and_restore_preserve_project_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("旧名称")
            renamed = store.rename(project["project_id"], "新名称")
            archived = store.archive(project["project_id"])
            restored = store.unarchive(project["project_id"])

        self.assertEqual(project["project_id"], renamed["project_id"])
        self.assertEqual("新名称", renamed["name"])
        self.assertIsNotNone(archived["archive_state"])
        self.assertIsNone(restored["archive_state"])


if __name__ == "__main__":
    unittest.main()

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

    def test_task_policy_allows_different_source_analysis_but_serializes_content_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("任务并发")
            store.attach_task(
                project["project_id"], task_id="visual-1", kind="visual_analysis",
                source_id="source-1", status="running",
            )

            other_source = store.task_start_projection(
                project["project_id"], kind="visual_analysis", source_id="source-2"
            )
            same_source = store.task_start_projection(
                project["project_id"], kind="visual_analysis", source_id="source-1"
            )
            store.attach_task(
                project["project_id"], task_id="matching-1", kind="fusion_matching",
                status="running",
            )
            narration = store.task_start_projection(
                project["project_id"], kind="narration_generation"
            )

        self.assertTrue(other_source["allowed"])
        self.assertFalse(same_source["allowed"])
        self.assertFalse(narration["allowed"])

    def test_restart_reconciliation_marks_unfinished_tasks_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("恢复任务")
            store.attach_task(
                project["project_id"], task_id="task-1", kind="visual_analysis",
                status="running",
            )

            reconciled = store.reconcile_unfinished_tasks(project["project_id"])

        self.assertEqual("interrupted", reconciled["task_refs"][0]["status"])
        self.assertTrue(reconciled["task_refs"][0]["recoverable"])

    def test_task_diagnostics_projection_does_not_expose_request_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("诊断")
            store.attach_task(
                project["project_id"], task_id="secret-task-id", kind="fusion_matching",
                status="failed",
            )
            store.update_task_summary(
                project["project_id"], "secret-task-id",
                message="请求失败", error_message="超时", failure_category="total_timeout",
                request={"api_key": "do-not-show"},
            )

            diagnostic = store.task_diagnostic_projection(project["project_id"], "secret-task-id")

        self.assertEqual("total_timeout", diagnostic["failure_category"])
        self.assertNotIn("request", diagnostic)
        self.assertNotIn("task_id", diagnostic)
        self.assertNotIn("do-not-show", str(diagnostic))

    def test_visual_evidence_is_owned_by_its_source_and_combined_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("多视频")
            first = store.add_local_reference(project["project_id"], path="first.mp4")
            second = store.add_local_reference(project["project_id"], path="second.mp4")

            store.attach_source_visual_evidence(
                project["project_id"], source_id=first["source_id"],
                evidence="00:00-00:06 第一段", artifact_path="first.json",
            )
            updated = store.attach_source_visual_evidence(
                project["project_id"], source_id=second["source_id"],
                evidence="00:00-00:06 第二段", artifact_path="second.json",
            )

        by_source = updated["artifact_refs"]["visual_evidence_by_source"]
        self.assertEqual(2, len(by_source))
        self.assertIn("第一段", updated["artifact_refs"]["visual_evidence"])
        self.assertIn("第二段", updated["artifact_refs"]["visual_evidence"])
        self.assertTrue(all(source["visual_evidence_status"] == "completed" for source in updated["source_video_sequence"]))

    def test_matching_completion_updates_active_project_only_for_same_input_version(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("匹配")
            store.update(project["project_id"], active_version_id="version-1")
            store.attach_task(
                project["project_id"], task_id="matching-1", kind="fusion_matching",
                input_version_id="version-1", status="running",
            )
            finalization = {
                "active_version_id": "matched-1",
                "preflight": {"blockers": [{"code": "gap", "message": "时间线缺口"}], "warnings": []},
                "narrative_quality_findings": [{"code": "pace", "segment_id": "s1"}],
            }

            admitted = store.admit_matching_completion(
                project["project_id"], task_id="matching-1", finalization=finalization
            )

        self.assertEqual("active", admitted["admission"])
        self.assertEqual("matched-1", admitted["project"]["active_version_id"])
        self.assertEqual("blocker", admitted["project"]["review_findings"][0]["severity"])

    def test_matching_completion_for_old_version_is_visible_but_not_active(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("过期匹配")
            store.update(project["project_id"], active_version_id="version-2")
            store.attach_task(
                project["project_id"], task_id="matching-old", kind="fusion_matching",
                input_version_id="version-1", status="running",
            )

            admitted = store.admit_matching_completion(
                project["project_id"], task_id="matching-old",
                finalization={"active_version_id": "matched-old", "preflight": {}},
            )

        self.assertEqual("stale", admitted["admission"])
        self.assertEqual("version-2", admitted["project"]["active_version_id"])
        self.assertNotIn("finalization", admitted["project"]["artifact_refs"])

    def test_creator_review_sync_updates_only_the_admitted_matching_task(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("Narrative Map")
            store.update(project["project_id"], active_version_id="v1")
            store.attach_task(
                project["project_id"], task_id="matching-1", kind="fusion_matching",
                input_version_id="v1", status="running",
            )
            store.admit_matching_completion(
                project["project_id"], task_id="matching-1",
                finalization={"active_version_id": "matched-1", "preflight": {}},
            )

            synced = store.sync_admitted_matching_state(
                project["project_id"], task_id="matching-1",
                finalization={
                    "active_version_id": "narrative-map-2",
                    "narrative_map": {"approval_status": "approved"},
                    "preflight": {"blockers": [], "warnings": []},
                },
            )

        self.assertEqual("narrative-map-2", synced["active_version_id"])
        self.assertEqual("approved", synced["artifact_refs"]["narrative_map"]["approval_status"])


if __name__ == "__main__":
    unittest.main()

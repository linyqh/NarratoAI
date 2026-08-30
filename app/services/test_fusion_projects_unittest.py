import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

from app.services.fusion_projects import FusionProjectStore, project_projection


class FusionProjectStoreTests(unittest.TestCase):
    def _render_authorization(self, store, project, root, configuration=None):
        movie = Path(root) / "render-source.mp4"
        movie.write_bytes(b"video")
        store.add_local_reference(project["project_id"], path=str(movie))
        finalization = {
            "active_version_id": "version-1",
            "renderable": True,
            "finalized_script": [{"_id": 1}],
            "preflight": {
                "blockers": [], "warnings": [], "renderable": True,
            },
        }
        store.update(
            project["project_id"], active_version_id="version-1",
            artifact_refs={"finalization": finalization},
        )
        return store.create_render_authorization(
            project["project_id"], configuration_snapshot=configuration or {}
        )

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
        self.assertEqual("解决审核阻断项", projection["next_action"])

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

    def test_concurrent_task_updates_do_not_lose_project_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FusionProjectStore(root)
            project = store.create("并发更新")

            def attach(index):
                FusionProjectStore(root).attach_task(
                    project["project_id"], task_id=f"task-{index}",
                    kind="visual_analysis", source_id=f"source-{index}",
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(attach, range(20)))
            reopened = store.read(project["project_id"])

        self.assertEqual(20, len(reopened["task_refs"]))
        self.assertGreaterEqual(reopened["revision"], 21)

    def test_task_reservation_atomically_blocks_duplicate_content_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = FusionProjectStore(root).create("任务互斥")

            def reserve(index):
                try:
                    FusionProjectStore(root).reserve_task(
                        project["project_id"], task_id=f"plan-{index}", kind="fusion_plan"
                    )
                    return "started"
                except ValueError:
                    return "blocked"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(reserve, range(2)))

        self.assertEqual(["blocked", "started"], sorted(results))

    def test_cancelled_run_cannot_commit_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("取消竞争")
            store.reserve_task(
                project["project_id"], task_id="plan-1", kind="fusion_plan",
                run_id="run-1",
            )
            store.cancel_task_run(
                project["project_id"], task_id="plan-1", run_id="run-1"
            )

            with self.assertRaisesRegex(ValueError, "no longer current"):
                store.commit_task_artifacts(
                    project["project_id"], task_id="plan-1", run_id="run-1",
                    artifact_changes={"fusion_segment_plan_draft": {"segments": []}},
                    message="不应提交",
                )
            reopened = store.read(project["project_id"])

        self.assertNotIn("fusion_segment_plan_draft", reopened["artifact_refs"])
        self.assertEqual("cancelled", reopened["task_refs"][0]["status"])

    def test_completed_run_cannot_be_relabelled_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("完成后取消")
            store.reserve_task(
                project["project_id"], task_id="plan-1", kind="fusion_plan",
                run_id="run-1",
            )
            store.commit_task_artifacts(
                project["project_id"], task_id="plan-1", run_id="run-1",
                artifact_changes={"fusion_segment_plan_draft": {"segments": []}},
                message="已完成",
            )

            with self.assertRaisesRegex(ValueError, "no longer cancellable"):
                store.cancel_task_run(
                    project["project_id"], task_id="plan-1", run_id="run-1"
                )
            reopened = store.read(project["project_id"])

        self.assertEqual("completed", reopened["task_refs"][0]["status"])
        self.assertIn("fusion_segment_plan_draft", reopened["artifact_refs"])

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
            authorization = self._render_authorization(
                store, project, directory
            )
            decision = store.record_review_decision(
                project["project_id"], finding_id="finding-1", action="acknowledge"
            )
            undone = store.undo_review_decision(project["project_id"], decision["decision_id"])
            first = store.add_render_outcome(
                project["project_id"], media_path="first.mp4",
                render_authorization=authorization,
            )
            second = store.add_render_outcome(
                project["project_id"], media_path="second.mp4",
                render_authorization=authorization,
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

    def test_replacing_source_at_same_path_invalidates_old_evidence_and_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "movie.mp4"
            movie.write_bytes(b"old-video")
            store = FusionProjectStore(root / "projects")
            project = store.create("身份变化")
            source = store.add_local_reference(project["project_id"], path=str(movie))
            store.attach_source_visual_evidence(
                project["project_id"], source_id=source["source_id"],
                evidence="旧画面", artifact_path="old.json",
            )
            store.update(
                project["project_id"], active_version_id="v1",
                artifact_refs={
                    **store.read(project["project_id"])["artifact_refs"],
                    "fusion_segment_plan": {"segments": []},
                    "finalization": {"active_version_id": "v1"},
                },
            )
            original_stat = movie.stat()
            movie.write_bytes(b"new-video")
            os.utime(movie, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

            refreshed = store.refresh_source_availability(project["project_id"])

        self.assertEqual("changed", refreshed["source_video_sequence"][0]["identity_status"])
        self.assertEqual("stale", refreshed["source_video_sequence"][0]["visual_evidence_status"])
        self.assertFalse(refreshed["active_version_id"])
        self.assertNotIn("finalization", refreshed["artifact_refs"])
        self.assertEqual("source_identity_changed", refreshed["review_findings"][0]["code"])

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
            root = Path(directory)
            (root / "first.mp4").write_bytes(b"first")
            (root / "second.mp4").write_bytes(b"second")
            store = FusionProjectStore(root / "projects")
            project = store.create("多视频")
            first = store.add_local_reference(project["project_id"], path=str(root / "first.mp4"))
            second = store.add_local_reference(project["project_id"], path=str(root / "second.mp4"))

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

    def test_migration_is_explicit_and_creates_a_normal_durable_project(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))

            migrated = store.migrate_legacy_project(
                name="旧 Fusion 工作",
                source_paths=["D:/movie.mp4"],
                finalized_script=[{"_id": 1, "timestamp": "00:00:00,000-00:00:05,000"}],
                preflight={"blockers": [], "warnings": [], "renderable": True},
            )
            reopened = store.read(migrated["project_id"])

        self.assertEqual("legacy_fusion_import", reopened["migration_state"]["kind"])
        self.assertEqual("requires_revalidation", reopened["migration_state"]["status"])
        self.assertEqual("review", reopened["active_stage"])
        self.assertTrue(reopened["active_version_id"])
        self.assertFalse(reopened["artifact_refs"]["finalization"]["renderable"])
        self.assertEqual(
            "legacy_import_requires_revalidation",
            reopened["review_findings"][0]["code"],
        )

    def test_legacy_migration_can_be_revalidated_against_current_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "movie.mp4"
            movie.write_bytes(b"video")
            store = FusionProjectStore(root / "projects")
            migrated = store.migrate_legacy_project(
                name="可迁移项目", source_paths=[str(movie)],
                finalized_script=[{
                    "_id": 1, "video_name": movie.name, "OST": 0,
                    "narration": "开场", "timestamp": "00:00:00,000-00:00:05,000",
                }],
                preflight={"blockers": [], "warnings": [], "renderable": True},
            )

            revalidated = store.revalidate_legacy_project(
                migrated["project_id"], source_durations={movie.name: 10.0}
            )

        self.assertEqual("revalidated", revalidated["migration_state"]["status"])
        self.assertTrue(revalidated["artifact_refs"]["finalization"]["renderable"])
        self.assertFalse(revalidated["review_findings"])

    def test_render_outcome_freezes_configuration_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("输出")
            configuration = {"voice": "voice-a", "subtitle_enabled": True}
            authorization = self._render_authorization(
                store, project, directory, configuration
            )

            outcome = store.add_render_outcome(
                project["project_id"], media_path="movie.mp4",
                render_authorization=authorization,
            )
            configuration["voice"] = "changed"

        self.assertEqual("voice-a", outcome["configuration_snapshot"]["voice"])

    def test_render_completion_for_changed_version_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory) / "projects")
            project = store.create("过期输出")
            authorization = self._render_authorization(store, project, directory)
            store.attach_task(
                project["project_id"], task_id="render-1", kind="render",
                input_version_id="version-1", status="running",
            )
            store.update(project["project_id"], active_version_id="version-2")

            outcome = store.add_render_outcome(
                project["project_id"], media_path="old.mp4",
                render_authorization=authorization, render_task_id="render-1",
            )

        self.assertEqual("stale", outcome["admission"])
        self.assertEqual("version-1", outcome["version_id"])
        self.assertEqual("render", outcome["project"]["stale_task_results"][0]["kind"])

    def test_render_authorization_rechecks_current_media_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory) / "projects")
            project = store.create("授权身份")
            self._render_authorization(store, project, directory)
            source = store.read(project["project_id"])["source_video_sequence"][0]
            movie = Path(source["path"])
            original_stat = movie.stat()
            movie.write_bytes(b"other")
            os.utime(movie, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

            with self.assertRaisesRegex(ValueError, "content changed"):
                store.create_render_authorization(project["project_id"])

    def test_warning_override_requires_reason_and_blockers_remain_unoverridable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FusionProjectStore(Path(directory))
            project = store.create("Preflight")
            store.update(
                project["project_id"], active_version_id="v1",
                artifact_refs={
                    "finalization": {
                        "active_version_id": "v1", "version_history": [],
                        "preflight": {"blockers": [], "warnings": [{"code": "warning"}]},
                    }
                },
            )
            with self.assertRaisesRegex(ValueError, "reason"):
                store.override_render_warnings(project["project_id"], reason="")
            overridden = store.override_render_warnings(
                project["project_id"], reason="人工确认画面与旁白一致"
            )
            blocked_finalization = dict(overridden["artifact_refs"]["finalization"])
            blocked_finalization["preflight"] = {
                "blockers": [{"code": "gap"}], "warnings": []
            }
            store.update(project["project_id"], artifact_refs={"finalization": blocked_finalization})
            with self.assertRaisesRegex(ValueError, "blockers"):
                store.override_render_warnings(project["project_id"], reason="不能覆盖")

        self.assertTrue(overridden["artifact_refs"]["finalization"]["preflight"]["renderable"])

    def test_project_projection_covers_creator_facing_state_matrix(self):
        base = {
            "project_id": "project1", "name": "状态", "trash_state": None,
            "archive_state": None, "review_findings": [], "task_refs": [],
            "render_outcomes": [], "active_stage": "setup", "active_version_id": "",
            "source_video_sequence": [], "stale_task_results": [],
        }
        cases = [
            ({}, "draft"),
            ({"task_refs": [{"status": "running"}]}, "running"),
            ({"task_refs": [{"status": "interrupted"}]}, "interrupted"),
            ({"review_findings": [{"severity": "warning", "status": "open"}]}, "waiting_for_review"),
            ({"active_version_id": "v1"}, "waiting_for_review"),
            ({
                "active_version_id": "v1",
                "artifact_refs": {"finalization": {
                    "active_version_id": "v1", "renderable": True,
                    "preflight": {"blockers": [], "warnings": [], "renderable": True},
                }},
            }, "ready_to_render"),
            ({
                "active_version_id": "v1",
                "render_outcomes": [{"outcome_id": "o1", "version_id": "v1", "admission": "active"}],
            }, "completed"),
            ({"source_video_sequence": [{"available": False}]}, "source_offline"),
            ({"stale_task_results": [{"task_id": "old"}]}, "stale_result"),
            ({"review_findings": [{"severity": "blocker", "status": "open"}], "task_refs": [{"status": "running"}]}, "blocked"),
        ]

        for changes, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, project_projection({**base, **changes})["status"])

    def test_uploaded_subtitle_is_project_owned_and_source_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FusionProjectStore(root / "projects")
            project = store.create("字幕归属")
            first = store.add_local_reference(project["project_id"], path=str(root / "first.mp4"))
            second = store.add_local_reference(project["project_id"], path=str(root / "second.mp4"))

            updated = store.save_source_subtitle_upload(
                project["project_id"], source_id=first["source_id"],
                filename="dialogue.srt", content=b"1\n00:00:00,000 --> 00:00:01,000\nhello\n",
            )

        sources = updated["source_video_sequence"]
        saved = next(item for item in sources if item["source_id"] == first["source_id"])
        untouched = next(item for item in sources if item["source_id"] == second["source_id"])
        self.assertEqual("uploaded", saved["subtitle_origin"])
        self.assertEqual("available", saved["subtitle_status"])
        self.assertEqual("missing", untouched["subtitle_status"])

    def test_unverified_visual_artifact_is_regression_only_and_blocks_narration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            movie = root / "movie.mp4"
            movie.write_bytes(b"video")
            store = FusionProjectStore(root / "projects")
            project = store.create("旧产物")
            source = store.add_local_reference(project["project_id"], path=str(movie))
            store.set_source_subtitle(
                project["project_id"], source_id=source["source_id"], subtitle_path=str(root / "missing.srt")
            )

            updated = store.import_source_visual_evidence_artifact(
                project["project_id"], source_id=source["source_id"],
                artifact={
                    "artifact_version": "documentary-frame-analysis-v4",
                    "batches": [{"time_range": "00:00:00-00:00:01", "overall_activity_summary": "人物走进房间"}],
                },
                artifact_path="legacy.json", allow_unverified_source=True,
            )
            narration_blockers = store.stage_readiness(project["project_id"])["narration"]["blockers"]

        source_state = updated["source_video_sequence"][0]
        self.assertEqual("regression_only", source_state["visual_evidence_status"])
        self.assertIn("未验证视觉证据仅可回归测试", narration_blockers)


if __name__ == "__main__":
    unittest.main()

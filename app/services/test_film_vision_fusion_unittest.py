"""Tests for the public visual-evidence seam used by fusion narration."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.film_vision_fusion import (
    format_highlight_candidates,
    format_visual_evidence,
    load_visual_evidence_artifact,
)
from app.services.documentary.frame_analysis_service import DocumentaryFrameAnalysisService
from app.services.documentary.frame_analysis_models import DocumentaryAnalysisConfig
from app.services.visual_evidence_artifact import (
    ARTIFACT_VERSION,
    build_source_video_identity,
    highlight_candidate_state,
    usable_highlight_candidates,
    highlight_candidate_rejections,
    read_highlight_candidate_intake,
)


class VisualEvidenceFormattingTests(unittest.TestCase):
    def test_explicit_higher_visual_concurrency_is_honored(self):
        analysis_config = DocumentaryAnalysisConfig(
            video_path="film.mp4",
            frame_interval_seconds=6,
            vision_batch_size=8,
            vision_llm_provider="openai",
            vision_model_name="vision-model",
            max_concurrency=7,
        )

        self.assertEqual(7, analysis_config.max_concurrency)

    def test_formats_successful_batches_in_timeline_order(self):
        artifact = {
            "batches": [
                {
                    "status": "success",
                    "time_range": "00:00:10,000-00:00:20,000",
                    "overall_activity_summary": "幸存者躲进走廊。",
                    "frame_observations": [
                        {"timestamp": "00:00:12,000", "observation": "丧尸撞击玻璃门。"},
                    ],
                },
                {
                    "status": "success",
                    "time_range": "00:00:00,000-00:00:10,000",
                    "overall_activity_summary": "人群在街道上逃跑。",
                    "frame_observations": [],
                },
                {
                    "status": "failed",
                    "time_range": "00:00:20,000-00:00:30,000",
                    "error_message": "rate limited",
                },
            ]
        }

        context = format_visual_evidence(artifact)

        self.assertTrue(context.startswith("# 视觉证据"))
        self.assertLess(context.index("00:00:00,000"), context.index("00:00:10,000"))
        self.assertIn("丧尸撞击玻璃门", context)
        self.assertNotIn("rate limited", context)

    def test_rejects_an_artifact_without_usable_visual_evidence(self):
        with self.assertRaisesRegex(ValueError, "可用视觉证据"):
            format_visual_evidence({"batches": [{"status": "failed"}]})

    def test_formats_only_usable_highlight_candidates_in_timeline_order(self):
        context = format_highlight_candidates(
            {
                "batches": [
                    {"batch_index": 0, "time_range": "00:00:00,000-00:00:40,000"}
                ],
                "highlight_candidates": [
                    {
                        "time_range": "00:00:20,000-00:00:30,000",
                        "category": "表演情绪",
                        "reason": "人物沉默后落泪，表情和停顿有表演价值。",
                        "score": 4,
                    },
                    {
                        "time_range": "00:00:05,000-00:00:10,000",
                        "category": "悬疑线索",
                        "reason": "空旷走廊尽头的警报灯反复闪烁，画面制造紧张感。",
                        "score": 5,
                    },
                    {"time_range": "00:00:40,000-00:00:50,000", "category": "其他"},
                ]
            }
        )

        self.assertTrue(context.startswith("# 原片高光候选"))
        self.assertLess(context.index("00:00:05,000"), context.index("00:00:20,000"))
        self.assertIn("悬疑线索", context)
        self.assertNotIn("00:00:40,000", context)

    def test_preserves_valid_highlight_candidates_from_a_vision_response(self):
        result = DocumentaryFrameAnalysisService()._parse_batch_response(
            batch_index=0,
            raw_response='''{
              "frame_observations": [{"timestamp": "00:00:01,000", "observation": "两人对峙。"}],
              "overall_activity_summary": "两人在房间内紧张对峙。",
              "highlight_candidates": [
                {"time_range": "00:00:01,000-00:00:05,000", "category": "表演情绪", "reason": "人物长时间沉默对视，表情变化值得保留。", "score": 8},
                {"category": "其他", "reason": ""}
              ]
            }''',
            frame_paths=["keyframe_000000_000001000.jpg"],
            time_range="00:00:01,000-00:00:07,000",
        )

        self.assertEqual("success", result.status)
        self.assertEqual(
            [
                {
                    "time_range": "00:00:01,000-00:00:05,000",
                    "category": "表演情绪",
                    "reason": "人物长时间沉默对视，表情变化值得保留。",
                    "score": 5,
                    "story_importance": 3,
                    "visual_impact": 3,
                    "performance_value": 3,
                }
            ],
            [candidate.to_dict() for candidate in result.highlight_candidates],
        )

    def test_discards_candidate_outside_its_batch_range(self):
        result = DocumentaryFrameAnalysisService()._parse_batch_response(
            batch_index=0,
            raw_response='''{"frame_observations": [{"timestamp": "00:00:01,000", "observation": "人物对峙。"}], "highlight_candidates": [{"time_range": "00:00:08,000-00:00:09,000", "category": "动作场面", "reason": "画面追逐。", "score": 5}]}''',
            frame_paths=["frame.jpg"],
            time_range="00:00:01,000-00:00:07,000",
        )
        self.assertEqual([], result.highlight_candidates)

    def test_filters_audio_claims_from_every_visual_output_field(self):
        result = DocumentaryFrameAnalysisService()._parse_batch_response(
            batch_index=0,
            raw_response='''{
              "frame_observations": [{"timestamp": "00:00:01,000", "observation": "枪声响起，人物转身。"}],
              "overall_activity_summary": "背景音乐响起，人物开始奔跑。",
              "highlight_candidates": [
                {"time_range": "00:00:01,000-00:00:05,000", "category": "动作场面", "reason": "爆炸声震耳欲聋。", "score": 5}
              ]
            }''',
            frame_paths=["keyframe_000000_000001000.jpg"],
            time_range="00:00:01,000-00:00:07,000",
        )

        self.assertEqual("", result.frame_observations[0]["observation"])
        self.assertEqual("", result.overall_activity_summary)
        self.assertEqual([], result.highlight_candidates)


class VisualEvidenceArtifactImportTests(unittest.TestCase):
    def test_highlight_candidate_intake_accounts_for_every_batch_submission_once(self):
        artifact = self._artifact()
        artifact["batches"][0]["highlight_candidates"] = [
            {"category": "表演情绪", "reason": "人物沉默对视。", "score": 5},
            {"time_range": "00:00:08,000-00:00:09,000", "category": "动作场面", "reason": "人物奔跑。", "score": 5},
        ]

        intake = read_highlight_candidate_intake(artifact)

        self.assertEqual(2, intake.submitted_count)
        self.assertEqual("00:00:00,000-00:00:06,000", str(intake.candidates[0].time_range))
        self.assertEqual("outside_batch_range", intake.rejections[0].reason)
    def _artifact(self, *, version=ARTIFACT_VERSION, identity=None, highlights=None):
        artifact = {
            "artifact_version": version,
            "batches": [
                {
                    "status": "success",
                    "batch_index": 0,
                    "time_range": "00:00:00,000-00:00:06,000",
                    "overall_activity_summary": "两人在走廊内对峙。",
                }
            ],
        }
        if identity is not None:
            artifact["source_video_identity"] = identity
        if highlights is not None:
            artifact["highlight_candidates"] = highlights
        return artifact

    def test_imports_v4_artifact_only_for_the_identical_video(self):
        with TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "source.mp4"
            video_path.write_bytes(b"same-video-content")
            artifact = self._artifact(
                identity=build_source_video_identity(str(video_path)),
                highlights=[
                    {
                        "time_range": "00:00:00,000-00:00:06,000",
                        "category": "表演情绪",
                        "reason": "人物沉默对峙。",
                        "score": 5,
                    }
                ],
            )

            evidence = load_visual_evidence_artifact(
                artifact,
                source_video_path=str(video_path),
                artifact_path="fixture.json",
            )

        self.assertTrue(evidence.source_verified)
        self.assertEqual("available", evidence.highlight_state)
        self.assertIn("原片高光候选", evidence.highlight_candidates)

    def test_legacy_artifact_requires_explicit_unverified_confirmation(self):
        with TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "source.mp4"
            video_path.write_bytes(b"same-video-content")
            artifact = self._artifact(version="documentary-frame-analysis-v2")

            with self.assertRaisesRegex(ValueError, "没有视频内容校验信息"):
                load_visual_evidence_artifact(
                    artifact,
                    source_video_path=str(video_path),
                    artifact_path="legacy.json",
                )

            evidence = load_visual_evidence_artifact(
                artifact,
                source_video_path=str(video_path),
                artifact_path="legacy.json",
                allow_unverified_source=True,
            )

        self.assertFalse(evidence.source_verified)
        self.assertEqual("unavailable_legacy", evidence.highlight_state)
        self.assertEqual("", evidence.highlight_candidates)

    def test_rejects_unknown_artifact_version(self):
        with TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "source.mp4"
            video_path.write_bytes(b"same-video-content")
            with self.assertRaisesRegex(ValueError, "受支持"):
                load_visual_evidence_artifact(
                    self._artifact(version="documentary-frame-analysis-v999"),
                    source_video_path=str(video_path),
                    artifact_path="future.json",
                    allow_unverified_source=True,
                )

    def test_ignores_malformed_candidates_but_scans_all_batches(self):
        artifact = self._artifact()
        artifact["batches"] = [
            {
                "batch_index": 0,
                "time_range": "00:00:00,000-00:00:06,000",
                "highlight_candidates": [{"reason": "缺少时间范围", "score": 5}],
            },
            {
                "batch_index": 1,
                "time_range": "00:00:10,000-00:00:12,000",
                "highlight_candidates": [
                    {
                        "time_range": "00:00:10,000-00:00:12,000",
                        "category": "动作场面",
                        "reason": "人物翻越栏杆。",
                        "score": 5,
                    }
                ]
            },
        ]
        self.assertEqual("available", highlight_candidate_state(artifact))

    def test_rejects_a_non_timestamp_candidate_range_at_the_artifact_boundary(self):
        artifact = self._artifact(
            highlights=[
                {
                    "time_range": "banana-carrot",
                    "category": "动作场面",
                    "reason": "人物奔跑。",
                    "score": 5,
                }
            ]
        )

        self.assertEqual([], usable_highlight_candidates(artifact))
        self.assertEqual("analyzed_empty", highlight_candidate_state(artifact))
        self.assertEqual("invalid_time_range", highlight_candidate_rejections(artifact)[0]["reason"])

    def test_rejects_artifact_candidate_outside_its_declared_batch(self):
        artifact = self._artifact(
            highlights=[
                {
                    "batch_index": 0,
                    "time_range": "00:01:00,000-00:01:05,000",
                    "category": "动作场面",
                    "reason": "人物奔跑。",
                    "score": 5,
                }
            ]
        )

        self.assertEqual([], usable_highlight_candidates(artifact))

    def test_legacy_candidate_receives_neutral_marked_defaults(self):
        artifact = self._artifact(
            version="documentary-frame-analysis-v3",
            highlights=[
                {
                    "time_range": "00:00:01,000-00:00:04,000",
                    "category": "表演情绪",
                    "reason": "人物沉默对视。",
                    "score": 4,
                }
            ],
        )

        candidate = usable_highlight_candidates(artifact)[0]

        self.assertEqual(3, candidate.story_importance)
        self.assertEqual(3, candidate.visual_impact)
        self.assertEqual(3, candidate.performance_value)
        self.assertEqual("defaulted_legacy", candidate.source_identity_status)
        self.assertEqual(
            ("story_importance", "visual_impact", "performance_value"),
            candidate.defaulted_signals,
        )

    def test_rejects_artifact_for_a_different_video(self):
        with TemporaryDirectory() as tmp_dir:
            analyzed_video = Path(tmp_dir) / "analyzed.mp4"
            selected_video = Path(tmp_dir) / "selected.mp4"
            analyzed_video.write_bytes(b"analyzed-video")
            selected_video.write_bytes(b"different-video")
            artifact = self._artifact(identity=build_source_video_identity(str(analyzed_video)))

            with self.assertRaisesRegex(ValueError, "来源不一致"):
                load_visual_evidence_artifact(
                    artifact,
                    source_video_path=str(selected_video),
                    artifact_path="mismatch.json",
                )

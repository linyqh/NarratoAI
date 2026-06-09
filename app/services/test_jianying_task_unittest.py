import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.schema import VideoClipParams
from app.services import jianying_draft_builder, jianying_task


DraftPathPlaceholder = "##_draftpath_placeholder_0E685133-18CE-45ED-8CB8-2904A212EC80_##"


class JianyingTaskTests(unittest.TestCase):
    def test_normalize_indextts_uses_valid_param_reference(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as ref:
            params = VideoClipParams(tts_engine="indextts", voice_name=ref.name)

            jianying_task._normalize_indextts_reference_audio(params)

            self.assertEqual(f"indextts:{ref.name}", params.voice_name)

    def test_normalize_indextts_uses_config_reference_when_param_is_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ref_path = Path(temp_dir) / "reference.wav"
            ref_path.write_bytes(b"fake wav")
            params = VideoClipParams(tts_engine="indextts", voice_name="zh-CN-YunjianNeural")

            with patch.dict(jianying_task.config.indextts, {"reference_audio": str(ref_path)}, clear=False):
                jianying_task._normalize_indextts_reference_audio(params)

            self.assertEqual(f"indextts:{ref_path}", params.voice_name)

    def test_normalize_indextts2_uses_valid_param_reference(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as ref:
            params = VideoClipParams(tts_engine="indextts2", voice_name=f"indextts2:{ref.name}")

            jianying_task._normalize_indextts_reference_audio(params)

            self.assertEqual("indextts2", params.tts_engine)
            self.assertEqual(f"indextts2:{ref.name}", params.voice_name)

    def test_normalize_indextts2_uses_config_reference_when_param_is_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ref_path = Path(temp_dir) / "reference.wav"
            ref_path.write_bytes(b"fake wav")
            params = VideoClipParams(tts_engine="indextts2", voice_name="zh-CN-YunjianNeural")

            with patch.dict(jianying_task.config.indextts2, {"reference_audio": str(ref_path)}, clear=False):
                jianying_task._normalize_indextts_reference_audio(params)

            self.assertEqual(f"indextts2:{ref_path}", params.voice_name)

    def test_normalize_omnivoice_clone_uses_valid_param_reference(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as ref:
            params = VideoClipParams(tts_engine="omnivoice", voice_name=f"omnivoice:{ref.name}")

            with patch.dict(jianying_task.config.omnivoice, {"mode": "voice_clone"}, clear=False):
                jianying_task._normalize_indextts_reference_audio(params)

            self.assertEqual(f"omnivoice:{ref.name}", params.voice_name)

    def test_normalize_omnivoice_auto_does_not_require_reference(self):
        params = VideoClipParams(tts_engine="omnivoice", voice_name="omnivoice:auto")

        with patch.dict(jianying_task.config.omnivoice, {"mode": "auto", "reference_audio": ""}, clear=False):
            jianying_task._normalize_indextts_reference_audio(params)

        self.assertEqual("omnivoice:auto", params.voice_name)

    def test_normalize_indextts_requires_existing_reference_audio(self):
        params = VideoClipParams(tts_engine="indextts", voice_name="zh-CN-YunjianNeural")

        with patch.dict(jianying_task.config.indextts, {"reference_audio": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "IndexTTS-1.5 参考音频不存在"):
                jianying_task._normalize_indextts_reference_audio(params)

    def test_floor_duration_to_milliseconds(self):
        self.assertAlmostEqual(6.997, jianying_task._floor_duration_to_milliseconds(6.997333))
        self.assertAlmostEqual(7.0, jianying_task._floor_duration_to_milliseconds(7.000999))

    def test_clamp_duration_to_media_uses_actual_media_duration(self):
        duration_cache = {}

        with patch.object(jianying_task, "get_media_duration_ffprobe", return_value=4.2809):
            duration = jianying_task._clamp_duration_to_media(
                requested_duration=4.31,
                media_file="/tmp/clip.mp4",
                duration_cache=duration_cache,
                media_label="视频素材",
            )

        self.assertAlmostEqual(4.28, duration)

    def test_clamp_duration_to_media_respects_source_start_time(self):
        duration_cache = {}

        with patch.object(jianying_task, "get_media_duration_ffprobe", return_value=10.0):
            duration = jianying_task._clamp_duration_to_media(
                requested_duration=4.0,
                media_file="/tmp/original.mp4",
                duration_cache=duration_cache,
                media_label="原始视频素材",
                source_start_time=8.5,
            )

        self.assertAlmostEqual(1.5, duration)

    def test_format_seconds_for_trange_uses_millisecond_precision(self):
        self.assertEqual("4.280s", jianying_task._format_seconds_for_trange(4.28))

    def test_write_plaintext_jianying_draft_creates_root_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "drafts"
            output_dir = Path(temp_dir) / "task"
            root_path.mkdir()
            output_dir.mkdir()
            video_path = output_dir / "clip:01.mp4"
            audio_path = output_dir / "audio_00_00_00,000-00_00_04,310.mp3"
            video_path.write_bytes(b"fake video")
            audio_path.write_bytes(b"fake audio")

            params = VideoClipParams(
                video_origin_path=str(video_path),
                original_volume=0.4,
                tts_volume=0.9,
            )
            script = [
                {
                    "OST": 0,
                    "start_time": 0.0,
                    "duration": 4.31,
                    "timestamp": "00:00:00,000-00:00:04,310",
                    "video": str(video_path),
                    "audio": str(audio_path),
                }
            ]

            def fake_duration(file_path):
                return 4.2809 if file_path == str(video_path) else 5.0

            with (
                patch.object(jianying_draft_builder, "_get_media_duration_ffprobe", side_effect=fake_duration),
                patch.object(
                    jianying_draft_builder,
                    "_get_video_metadata_ffprobe",
                    return_value=(4_280_000, 720, 1280),
                ),
            ):
                draft_path, draft_name = jianying_draft_builder.write_plaintext_jianying_draft(
                    str(root_path),
                    "NarratoAI_test",
                    script,
                    params,
                    str(output_dir),
                )

            draft_dir = Path(draft_path)
            self.assertEqual("NarratoAI_test", draft_name)
            self.assertTrue((draft_dir / "draft_info.json").exists())
            self.assertTrue((draft_dir / "template-2.tmp").exists())
            self.assertTrue((draft_dir / "template.tmp").exists())
            self.assertTrue((draft_dir / "draft_cover.jpg").exists())
            self.assertFalse((draft_dir / "draft_content_legacy.json").exists())
            self.assertFalse((draft_dir / "Timelines" / "project.json").exists())
            self.assertTrue((draft_dir / "assets" / "video" / "clip_01.mp4").exists())
            self.assertTrue((draft_dir / "assets" / "audio" / audio_path.name).exists())

            draft_info = json.loads((draft_dir / "draft_info.json").read_text(encoding="utf-8"))
            self.assertEqual("169.0.0", draft_info["new_version"])
            self.assertEqual("NarratoAI_test", draft_info["name"])
            self.assertEqual(54, len(draft_info["materials"]))
            self.assertEqual(
                f"{DraftPathPlaceholder}/assets/video/clip_01.mp4",
                draft_info["materials"]["videos"][0]["path"],
            )
            self.assertEqual(
                f"{DraftPathPlaceholder}/assets/audio/{audio_path.name}",
                draft_info["materials"]["audios"][0]["path"],
            )
            self.assertEqual(4_280_000, draft_info["tracks"][0]["segments"][0]["source_timerange"]["duration"])
            self.assertEqual(4_280_000, draft_info["tracks"][1]["segments"][0]["source_timerange"]["duration"])

            attachment_editing = json.loads((draft_dir / "attachment_editing.json").read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", attachment_editing["editing_draft"]["version"])
            self.assertFalse(attachment_editing["editing_draft"]["is_use_audio_separation"])

            empty_template = json.loads((draft_dir / "template.tmp").read_text(encoding="utf-8"))
            self.assertEqual("75.0.0", empty_template["new_version"])
            self.assertEqual([], empty_template["tracks"])

            root_meta = json.loads((root_path / "root_meta_info.json").read_text(encoding="utf-8"))
            self.assertEqual("NarratoAI_test", root_meta["all_draft_store"][0]["draft_name"])
            self.assertEqual(str(draft_dir / "draft_info.json"), root_meta["all_draft_store"][0]["draft_json_file"])

    def test_write_plaintext_jianying_draft_uses_source_timerange_and_writes_subtitles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "drafts"
            output_dir = Path(temp_dir) / "task"
            root_path.mkdir()
            output_dir.mkdir()
            video_path = output_dir / "source.mp4"
            audio_path = output_dir / "audio_00_00_02,000-00_00_04,000.mp3"
            subtitle_path = output_dir / "script_subtitles.srt"
            video_path.write_bytes(b"fake source video")
            audio_path.write_bytes(b"fake audio")
            subtitle_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,500\n测试字幕\n",
                encoding="utf-8",
            )

            params = VideoClipParams(
                video_origin_path=str(video_path),
                original_volume=0.4,
                tts_volume=0.9,
                subtitle_enabled=True,
                font_size=60,
                text_fore_color="#FFFFFF",
            )
            script = [
                {
                    "OST": 0,
                    "start_time": 2.0,
                    "source_start_time": 2.0,
                    "duration": 3.0,
                    "timestamp": "00:00:02,000-00:00:05,000",
                    "video": str(video_path),
                    "audio": str(audio_path),
                    "use_source_timerange": True,
                }
            ]

            def fake_duration(file_path):
                return 10.0 if file_path == str(video_path) else 3.0

            with (
                patch.object(jianying_draft_builder, "_get_media_duration_ffprobe", side_effect=fake_duration),
                patch.object(
                    jianying_draft_builder,
                    "_get_video_metadata_ffprobe",
                    return_value=(10_000_000, 1920, 1080),
                ),
            ):
                draft_path, _ = jianying_draft_builder.write_plaintext_jianying_draft(
                    str(root_path),
                    "NarratoAI_source",
                    script,
                    params,
                    str(output_dir),
                    subtitle_path=str(subtitle_path),
                )

            draft_info = json.loads((Path(draft_path) / "draft_info.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(draft_info["materials"]["videos"]))
            self.assertEqual(1, len(draft_info["materials"]["texts"]))
            self.assertIn("测试字幕", draft_info["materials"]["texts"][0]["content"])

            video_segment = draft_info["tracks"][0]["segments"][0]
            self.assertEqual(2_000_000, video_segment["source_timerange"]["start"])
            self.assertEqual(3_000_000, video_segment["source_timerange"]["duration"])
            self.assertEqual(0.0, video_segment["volume"])

            text_tracks = [track for track in draft_info["tracks"] if track["type"] == "text"]
            self.assertEqual(1, len(text_tracks))
            self.assertEqual(1, len(text_tracks[0]["segments"]))
            self.assertEqual(1_500_000, text_tracks[0]["segments"][0]["target_timerange"]["duration"])

    def test_build_jianying_draft_script_references_original_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_one = Path(temp_dir) / "one.mp4"
            video_two = Path(temp_dir) / "two.mp4"
            audio_path = Path(temp_dir) / "audio.mp3"
            video_one.write_bytes(b"one")
            video_two.write_bytes(b"two")
            audio_path.write_bytes(b"audio")

            params = VideoClipParams(
                video_origin_path=str(video_one),
                video_origin_paths=[str(video_one), str(video_two)],
            )
            script = [
                {
                    "_id": 9,
                    "video_id": 2,
                    "timestamp": "00:00:05,000-00:00:07,000",
                    "narration": "解说",
                    "OST": 0,
                }
            ]
            tts_results = [
                {
                    "_id": 9,
                    "timestamp": "00:00:05,000-00:00:07,000",
                    "audio_file": str(audio_path),
                    "subtitle_file": "",
                    "duration": 1.25,
                }
            ]

            draft_script = jianying_task._build_jianying_draft_script(script, params, tts_results)

            self.assertEqual(str(video_two), draft_script[0]["video"])
            self.assertEqual(str(audio_path), draft_script[0]["audio"])
            self.assertEqual(5.0, draft_script[0]["source_start_time"])
            self.assertEqual(1.25, draft_script[0]["duration"])
            self.assertTrue(draft_script[0]["use_source_timerange"])

    def test_get_original_subtitle_paths_falls_back_to_matching_video_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            video_path = temp_path / "episode_20260608010240.mp4"
            older_subtitle = temp_path / "episode_fun_asr_20260608000100.srt"
            newer_subtitle = temp_path / "episode_fun_asr_20260608010100.srt"
            video_path.write_bytes(b"video")
            older_subtitle.write_text("old", encoding="utf-8")
            newer_subtitle.write_text("new", encoding="utf-8")

            params = VideoClipParams(video_origin_path=str(video_path))

            with patch.object(jianying_task.utils, "subtitle_dir", return_value=str(temp_path)):
                subtitle_paths = jianying_task._get_original_subtitle_paths(params)

            self.assertEqual([str(newer_subtitle)], subtitle_paths)

    def test_create_jianying_subtitle_file_includes_original_audio_subtitles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            task_dir = temp_path / "task"
            task_dir.mkdir()
            video_path = temp_path / "episode.mp4"
            subtitle_path = temp_path / "episode.srt"
            video_path.write_bytes(b"video")
            subtitle_path.write_text(
                "1\n00:00:05,000 --> 00:00:06,500\n原片对白\n",
                encoding="utf-8",
            )

            params = VideoClipParams(video_origin_path=str(video_path), subtitle_enabled=True)
            draft_script = jianying_task._build_jianying_draft_script(
                [
                    {
                        "_id": 1,
                        "timestamp": "00:00:05,000-00:00:07,000",
                        "narration": "播放原片1",
                        "OST": 1,
                    }
                ],
                params,
                [],
            )

            with (
                patch.object(jianying_task.utils, "subtitle_dir", return_value=str(temp_path)),
                patch.object(jianying_task.utils, "task_dir", return_value=str(task_dir)),
            ):
                output_path = jianying_task._create_jianying_subtitle_file(
                    "task-id",
                    draft_script,
                    params,
                )

            self.assertTrue(output_path)
            self.assertIn("原片对白", Path(output_path).read_text(encoding="utf-8"))

    def test_start_export_jianying_draft_does_not_clip_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "drafts"
            task_dir = Path(temp_dir) / "task"
            root_path.mkdir()
            task_dir.mkdir()
            video_path = Path(temp_dir) / "source.mp4"
            audio_path = task_dir / "audio.mp3"
            script_path = Path(temp_dir) / "script.json"
            subtitle_path = task_dir / "script_subtitles.srt"
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")
            script_path.write_text(
                json.dumps([
                    {
                        "_id": 1,
                        "timestamp": "00:00:01,000-00:00:03,000",
                        "narration": "测试解说",
                        "OST": 0,
                    }
                ], ensure_ascii=False),
                encoding="utf-8",
            )

            params = VideoClipParams(
                video_clip_json_path=str(script_path),
                video_origin_path=str(video_path),
                tts_engine="edge_tts",
                voice_name="zh-CN-YunjianNeural",
                subtitle_enabled=True,
                draft_name="NarratoAI_no_clip",
            )
            tts_results = [
                {
                    "_id": 1,
                    "timestamp": "00:00:01,000-00:00:03,000",
                    "audio_file": str(audio_path),
                    "subtitle_file": "",
                    "duration": 1.5,
                }
            ]

            with (
                patch.dict(jianying_task.config.ui, {"jianying_draft_path": str(root_path)}, clear=False),
                patch.object(jianying_task.utils, "task_dir", return_value=str(task_dir)),
                patch.object(jianying_task.voice, "tts_multiple", return_value=tts_results),
                patch.object(jianying_task, "_create_jianying_subtitle_file", return_value=str(subtitle_path)),
                patch.object(jianying_task, "write_plaintext_jianying_draft", return_value=(str(root_path / "draft"), "NarratoAI_no_clip")) as write_draft,
                patch.object(jianying_task.clip_video, "clip_video_unified") as clip_video_unified,
            ):
                result = jianying_task.start_export_jianying_draft("task-id", params)

            clip_video_unified.assert_not_called()
            write_kwargs = write_draft.call_args.kwargs
            self.assertTrue(write_kwargs["new_script_list"][0]["use_source_timerange"])
            self.assertEqual(str(audio_path), write_kwargs["new_script_list"][0]["audio"])
            self.assertEqual(str(subtitle_path), write_kwargs["subtitle_path"])
            self.assertEqual(str(subtitle_path), result["subtitles"][0])


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

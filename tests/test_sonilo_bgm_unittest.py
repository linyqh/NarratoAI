import base64
import json
import os
import tempfile
import unittest
from unittest import mock

from app.services import sonilo


def _ndjson_lines(*events):
    return [json.dumps(event) for event in events]


class ConsumeNdjsonStreamTests(unittest.TestCase):
    def test_returns_first_stream_audio_grouped_by_index(self):
        lines = _ndjson_lines(
            {"type": "audio_chunk", "stream_index": 0, "data": base64.b64encode(b"ab").decode()},
            {"type": "audio_chunk", "stream_index": 1, "data": base64.b64encode(b"zz").decode()},
            {"type": "audio_chunk", "stream_index": 0, "data": base64.b64encode(b"cd").decode()},
            {"type": "title", "data": "some title"},
            {"type": "complete"},
        )

        self.assertEqual(b"abcd", sonilo._consume_ndjson_stream(lines))

    def test_ignores_blank_and_unparseable_lines(self):
        lines = [
            "",
            "   ",
            "not json",
            json.dumps({"type": "audio_chunk", "stream_index": 0, "data": base64.b64encode(b"ok").decode()}),
            json.dumps({"type": "complete"}),
        ]

        self.assertEqual(b"ok", sonilo._consume_ndjson_stream(lines))

    def test_error_event_raises(self):
        lines = _ndjson_lines(
            {"type": "audio_chunk", "stream_index": 0, "data": base64.b64encode(b"ab").decode()},
            {"type": "error", "message": "boom"},
        )

        with self.assertRaises(sonilo.SoniloError):
            sonilo._consume_ndjson_stream(lines)

    def test_missing_complete_event_raises(self):
        lines = _ndjson_lines(
            {"type": "audio_chunk", "stream_index": 0, "data": base64.b64encode(b"ab").decode()},
        )

        with self.assertRaises(sonilo.SoniloError):
            sonilo._consume_ndjson_stream(lines)

    def test_complete_without_audio_raises(self):
        lines = _ndjson_lines({"type": "complete"})

        with self.assertRaises(sonilo.SoniloError):
            sonilo._consume_ndjson_stream(lines)


class GenerateBgmTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.video_path = os.path.join(self._tmp_dir.name, "combined.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"fake video")
        self.save_path = os.path.join(self._tmp_dir.name, "sonilo_bgm.m4a")

    def test_returns_empty_without_api_key(self):
        with mock.patch.object(sonilo, "get_api_key", return_value=""):
            self.assertEqual("", sonilo.generate_bgm(self.video_path, self.save_path))

    def test_returns_empty_when_video_missing(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"):
            missing = os.path.join(self._tmp_dir.name, "missing.mp4")
            self.assertEqual("", sonilo.generate_bgm(missing, self.save_path))

    def test_skips_upload_when_duration_exceeds_limit(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=361.0), \
                mock.patch.object(sonilo, "_request_video_to_music") as request_mock:
            self.assertEqual("", sonilo.generate_bgm(self.video_path, self.save_path))
            request_mock.assert_not_called()

    def test_saves_audio_on_success(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=60.0), \
                mock.patch.object(sonilo, "_request_video_to_music", return_value=b"audio-bytes"):
            self.assertEqual(self.save_path, sonilo.generate_bgm(self.video_path, self.save_path))

        with open(self.save_path, "rb") as f:
            self.assertEqual(b"audio-bytes", f.read())

    def test_request_failure_degrades_to_empty(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=60.0), \
                mock.patch.object(
                    sonilo,
                    "_request_video_to_music",
                    side_effect=sonilo.SoniloError("timeout"),
                ):
            self.assertEqual("", sonilo.generate_bgm(self.video_path, self.save_path))

        self.assertFalse(os.path.exists(self.save_path))


class ResolveBgmPathTests(unittest.TestCase):
    """任务层的 BGM 解析：Sonilo 模式失败时回退到现有 BGM 逻辑。"""

    def _make_params(self, bgm_type, bgm_file=""):
        params = mock.Mock()
        params.bgm_type = bgm_type
        params.bgm_file = bgm_file
        return params

    def test_non_sonilo_type_uses_existing_logic(self):
        from app.services import task

        params = self._make_params("custom", "/tmp/some_bgm.mp3")
        with mock.patch.object(task.utils, "get_bgm_file", return_value="/tmp/some_bgm.mp3") as get_bgm, \
                mock.patch.object(task.sonilo, "generate_bgm") as generate_bgm:
            result = task._resolve_bgm_path("task-id", params, "/tmp/combined.mp4")

        self.assertEqual("/tmp/some_bgm.mp3", result)
        get_bgm.assert_called_once_with(bgm_type="custom", bgm_file="/tmp/some_bgm.mp3")
        generate_bgm.assert_not_called()

    def test_sonilo_type_uses_generated_bgm(self):
        from app.services import task

        params = self._make_params("sonilo")
        with mock.patch.object(task.utils, "task_dir", return_value="/tmp/task-id"), \
                mock.patch.object(
                    task.sonilo, "generate_bgm", return_value="/tmp/task-id/sonilo_bgm.m4a"
                ) as generate_bgm, \
                mock.patch.object(task.utils, "get_bgm_file") as get_bgm:
            result = task._resolve_bgm_path("task-id", params, "/tmp/combined.mp4")

        self.assertEqual("/tmp/task-id/sonilo_bgm.m4a", result)
        generate_bgm.assert_called_once_with(
            "/tmp/combined.mp4", os.path.join("/tmp/task-id", "sonilo_bgm.m4a")
        )
        get_bgm.assert_not_called()

    def test_sonilo_failure_falls_back_to_random_bgm(self):
        from app.services import task

        params = self._make_params("sonilo")
        with mock.patch.object(task.utils, "task_dir", return_value="/tmp/task-id"), \
                mock.patch.object(task.sonilo, "generate_bgm", return_value=""), \
                mock.patch.object(
                    task.utils, "get_bgm_file", return_value="/resource/songs/output000.mp3"
                ) as get_bgm:
            result = task._resolve_bgm_path("task-id", params, "/tmp/combined.mp4")

        self.assertEqual("/resource/songs/output000.mp3", result)
        get_bgm.assert_called_once_with(bgm_type="random", bgm_file="")


if __name__ == "__main__":
    unittest.main()

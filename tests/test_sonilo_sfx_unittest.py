import os
import tempfile
import unittest
from unittest import mock

import requests

from app.services import sonilo


def _response(status_code=200, json_body=None, content=b"{}"):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.content = content
    if json_body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_body
    return resp


class SubmitSfxTaskTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.video_path = os.path.join(self._tmp_dir.name, "combined.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"fake video")

    def test_returns_task_id(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(
                    sonilo.requests,
                    "post",
                    return_value=_response(202, {"task_id": "task-123"}),
                ) as post_mock:
            self.assertEqual("task-123", sonilo._submit_sfx_task(self.video_path))

        args, kwargs = post_mock.call_args
        self.assertTrue(args[0].endswith("/v1/video-to-sfx"))
        self.assertEqual("Bearer sk-test", kwargs["headers"]["Authorization"])

    def test_http_error_raises(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(
                    sonilo.requests,
                    "post",
                    return_value=_response(402, content=b'{"detail": "no credits"}'),
                ):
            with self.assertRaises(sonilo.SoniloError):
                sonilo._submit_sfx_task(self.video_path)

    def test_missing_task_id_raises(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(
                    sonilo.requests, "post", return_value=_response(202, {})
                ):
            with self.assertRaises(sonilo.SoniloError):
                sonilo._submit_sfx_task(self.video_path)


class PollSfxTaskTests(unittest.TestCase):
    def test_returns_body_when_succeeded(self):
        responses = [
            _response(200, {"status": "processing"}),
            _response(
                200,
                {"status": "succeeded", "audio": {"url": "https://cdn/x.m4a"}},
            ),
        ]
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_sleep"), \
                mock.patch.object(sonilo.requests, "get", side_effect=responses):
            body = sonilo._poll_sfx_task("task-123")

        self.assertEqual("succeeded", body["status"])

    def test_failed_status_raises_with_task_id(self):
        response = _response(
            200,
            {
                "status": "failed",
                "error": {"code": "GENERATION_FAILED", "message": "boom"},
                "refunded": True,
            },
        )
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_sleep"), \
                mock.patch.object(sonilo.requests, "get", return_value=response):
            with self.assertRaises(sonilo.SoniloError) as ctx:
                sonilo._poll_sfx_task("task-123")

        self.assertIn("task-123", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_transient_error_retries_until_succeeded(self):
        responses = [
            requests.exceptions.ConnectionError("blip"),
            _response(
                200,
                {"status": "succeeded", "audio": {"url": "https://cdn/x.m4a"}},
            ),
        ]
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_sleep"), \
                mock.patch.object(sonilo.requests, "get", side_effect=responses):
            body = sonilo._poll_sfx_task("task-123")

        self.assertEqual("succeeded", body["status"])

    def test_non_recoverable_http_error_raises(self):
        response = _response(401, content=b'{"detail": "bad key"}')
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_sleep"), \
                mock.patch.object(sonilo.requests, "get", return_value=response):
            with self.assertRaises(sonilo.SoniloError):
                sonilo._poll_sfx_task("task-123")

    def test_timeout_raises_with_task_id(self):
        response = _response(200, {"status": "processing"})
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_sleep"), \
                mock.patch.object(sonilo, "_get_timeout_seconds", return_value=0.0), \
                mock.patch.object(sonilo.requests, "get", return_value=response):
            with self.assertRaises(sonilo.SoniloError) as ctx:
                sonilo._poll_sfx_task("task-123")

        self.assertIn("task-123", str(ctx.exception))


class DownloadSfxAudioTests(unittest.TestCase):
    def test_returns_content_without_auth_headers(self):
        response = _response(200, content=b"audio-bytes")
        with mock.patch.object(
            sonilo.requests, "get", return_value=response
        ) as get_mock:
            self.assertEqual(
                b"audio-bytes", sonilo._download_sfx_audio("https://cdn/x.m4a")
            )

        # 预签名 URL 自带鉴权，绝不能把 API Key 发给存储域名。
        _, kwargs = get_mock.call_args
        self.assertNotIn("headers", kwargs)

    def test_http_error_raises(self):
        with mock.patch.object(
            sonilo.requests, "get", return_value=_response(403, content=b"denied")
        ):
            with self.assertRaises(sonilo.SoniloError):
                sonilo._download_sfx_audio("https://cdn/x.m4a")

    def test_empty_content_raises(self):
        with mock.patch.object(
            sonilo.requests, "get", return_value=_response(200, content=b"")
        ):
            with self.assertRaises(sonilo.SoniloError):
                sonilo._download_sfx_audio("https://cdn/x.m4a")


class ExtractSfxAudioUrlTests(unittest.TestCase):
    def test_returns_audio_url(self):
        body = {"status": "succeeded", "audio": {"url": "https://cdn/x.m4a"}}
        self.assertEqual(
            "https://cdn/x.m4a", sonilo._extract_sfx_audio_url(body, "task-123")
        )

    def test_missing_audio_raises(self):
        with self.assertRaises(sonilo.SoniloError):
            sonilo._extract_sfx_audio_url({"status": "succeeded"}, "task-123")


class GenerateSfxTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.video_path = os.path.join(self._tmp_dir.name, "combined.mp4")
        with open(self.video_path, "wb") as f:
            f.write(b"fake video")
        self.save_path = os.path.join(self._tmp_dir.name, "sonilo_sfx.m4a")

    def test_returns_empty_without_api_key(self):
        with mock.patch.object(sonilo, "get_api_key", return_value=""):
            self.assertEqual("", sonilo.generate_sfx(self.video_path, self.save_path))

    def test_returns_empty_when_video_missing(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"):
            missing = os.path.join(self._tmp_dir.name, "missing.mp4")
            self.assertEqual("", sonilo.generate_sfx(missing, self.save_path))

    def test_skips_upload_when_duration_exceeds_limit(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=181.0), \
                mock.patch.object(sonilo, "_request_video_to_sfx") as request_mock:
            self.assertEqual("", sonilo.generate_sfx(self.video_path, self.save_path))
            request_mock.assert_not_called()

    def test_saves_audio_on_success(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=60.0), \
                mock.patch.object(sonilo, "_request_video_to_sfx", return_value=b"audio-bytes"):
            self.assertEqual(self.save_path, sonilo.generate_sfx(self.video_path, self.save_path))

        with open(self.save_path, "rb") as f:
            self.assertEqual(b"audio-bytes", f.read())

    def test_request_failure_degrades_to_empty(self):
        with mock.patch.object(sonilo, "get_api_key", return_value="sk-test"), \
                mock.patch.object(sonilo, "_probe_video_duration", return_value=60.0), \
                mock.patch.object(
                    sonilo,
                    "_request_video_to_sfx",
                    side_effect=sonilo.SoniloError("timeout"),
                ):
            self.assertEqual("", sonilo.generate_sfx(self.video_path, self.save_path))

        self.assertFalse(os.path.exists(self.save_path))


class GetSfxVolumeTests(unittest.TestCase):
    def test_default_when_unset(self):
        with mock.patch.object(sonilo.config, "app", {}):
            self.assertEqual(sonilo.DEFAULT_SFX_VOLUME, sonilo._get_sfx_volume())

    def test_default_when_invalid(self):
        with mock.patch.object(sonilo.config, "app", {"sonilo_sfx_volume": "abc"}):
            self.assertEqual(sonilo.DEFAULT_SFX_VOLUME, sonilo._get_sfx_volume())

    def test_default_when_non_positive(self):
        with mock.patch.object(sonilo.config, "app", {"sonilo_sfx_volume": 0}):
            self.assertEqual(sonilo.DEFAULT_SFX_VOLUME, sonilo._get_sfx_volume())

    def test_clamped_to_upper_bound(self):
        with mock.patch.object(sonilo.config, "app", {"sonilo_sfx_volume": 5}):
            self.assertEqual(2.0, sonilo._get_sfx_volume())

    def test_valid_value_passes_through(self):
        with mock.patch.object(sonilo.config, "app", {"sonilo_sfx_volume": 0.8}):
            self.assertEqual(0.8, sonilo._get_sfx_volume())


class MixSfxUnderOriginalTests(unittest.TestCase):
    def _run(self, has_audio, returncode=0, run_side_effect=None):
        run_mock = mock.Mock(return_value=mock.Mock(returncode=returncode, stderr=b"err"))
        if run_side_effect is not None:
            run_mock = mock.Mock(side_effect=run_side_effect)
        with mock.patch.object(sonilo, "_get_ffmpeg_binary", return_value="ffmpeg"), \
                mock.patch.object(sonilo, "_probe_has_audio_stream", return_value=has_audio), \
                mock.patch.object(sonilo, "_get_sfx_volume", return_value=0.6), \
                mock.patch.object(sonilo.subprocess, "run", run_mock):
            result = sonilo._mix_sfx_under_original(
                "/tmp/combined.mp4", "/tmp/sfx.m4a", "/tmp/merger_sfx.mp4"
            )
        return result, run_mock

    def test_mixes_under_existing_audio_with_amix(self):
        result, run_mock = self._run(has_audio=True)

        self.assertEqual("/tmp/merger_sfx.mp4", result)
        cmd = run_mock.call_args[0][0]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("volume=0.6", filter_complex)
        self.assertIn("amix", filter_complex)
        # 视频流直接复制，不重编码画面。
        self.assertIn("copy", cmd[cmd.index("-c:v") + 1])
        self.assertNotIn("-shortest", cmd)

    def test_sfx_becomes_audio_track_when_video_has_no_audio(self):
        result, run_mock = self._run(has_audio=False)

        self.assertEqual("/tmp/merger_sfx.mp4", result)
        cmd = run_mock.call_args[0][0]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        self.assertNotIn("amix", filter_complex)
        self.assertIn("-shortest", cmd)

    def test_ffmpeg_failure_returns_empty(self):
        result, _ = self._run(has_audio=True, returncode=1)
        self.assertEqual("", result)

    def test_ffmpeg_oserror_returns_empty(self):
        result, _ = self._run(has_audio=True, run_side_effect=OSError("no ffmpeg"))
        self.assertEqual("", result)


class ApplySfxTests(unittest.TestCase):
    def test_success_returns_output_path(self):
        with mock.patch.object(
            sonilo, "generate_sfx", return_value="/tmp/merger_sfx.m4a"
        ) as generate_mock, mock.patch.object(
            sonilo, "_mix_sfx_under_original", return_value="/tmp/merger_sfx.mp4"
        ) as mix_mock:
            result = sonilo.apply_sfx("/tmp/combined.mp4", "/tmp/merger_sfx.mp4")

        self.assertEqual("/tmp/merger_sfx.mp4", result)
        generate_mock.assert_called_once_with("/tmp/combined.mp4", "/tmp/merger_sfx.m4a")
        mix_mock.assert_called_once_with(
            "/tmp/combined.mp4", "/tmp/merger_sfx.m4a", "/tmp/merger_sfx.mp4"
        )

    def test_generation_failure_skips_mixing(self):
        with mock.patch.object(sonilo, "generate_sfx", return_value=""), \
                mock.patch.object(sonilo, "_mix_sfx_under_original") as mix_mock:
            self.assertEqual(
                "", sonilo.apply_sfx("/tmp/combined.mp4", "/tmp/merger_sfx.mp4")
            )
            mix_mock.assert_not_called()

    def test_mixing_failure_returns_empty(self):
        with mock.patch.object(
            sonilo, "generate_sfx", return_value="/tmp/merger_sfx.m4a"
        ), mock.patch.object(sonilo, "_mix_sfx_under_original", return_value=""):
            self.assertEqual(
                "", sonilo.apply_sfx("/tmp/combined.mp4", "/tmp/merger_sfx.mp4")
            )


class ApplySoniloSfxTaskTests(unittest.TestCase):
    """任务层的音效挂载：默认关闭，失败时沿用原视频，绝不中断成片任务。"""

    def _make_params(self, sfx_enabled):
        params = mock.Mock()
        params.sonilo_sfx_enabled = sfx_enabled
        return params

    def test_disabled_returns_original_path_without_calling_sonilo(self):
        from app.services import task

        params = self._make_params(False)
        with mock.patch.object(task.sonilo, "apply_sfx") as apply_mock:
            result = task._apply_sonilo_sfx("task-id", params, "/tmp/merger.mp4")

        self.assertEqual("/tmp/merger.mp4", result)
        apply_mock.assert_not_called()

    def test_enabled_returns_sfx_video_path(self):
        from app.services import task

        params = self._make_params(True)
        with mock.patch.object(task.utils, "task_dir", return_value="/tmp/task-id"), \
                mock.patch.object(
                    task.sonilo, "apply_sfx", return_value="/tmp/task-id/merger_sfx.mp4"
                ) as apply_mock:
            result = task._apply_sonilo_sfx("task-id", params, "/tmp/merger.mp4")

        self.assertEqual("/tmp/task-id/merger_sfx.mp4", result)
        apply_mock.assert_called_once_with(
            "/tmp/merger.mp4", os.path.join("/tmp/task-id", "merger_sfx.mp4")
        )

    def test_failure_falls_back_to_original_path(self):
        from app.services import task

        params = self._make_params(True)
        with mock.patch.object(task.utils, "task_dir", return_value="/tmp/task-id"), \
                mock.patch.object(task.sonilo, "apply_sfx", return_value=""):
            result = task._apply_sonilo_sfx("task-id", params, "/tmp/merger.mp4")

        self.assertEqual("/tmp/merger.mp4", result)


if __name__ == "__main__":
    unittest.main()

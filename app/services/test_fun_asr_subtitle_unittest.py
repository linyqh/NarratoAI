import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from app.config import config as cfg
from app.services import fun_asr_subtitle as fasr


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8") if isinstance(text, str) else b""

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class InvalidJsonResponse(FakeResponse):
    def json(self):
        raise ValueError("invalid json")


class FakeSession:
    def __init__(self, local_result):
        self.calls = []
        self.local_result = local_result

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url == fasr.UPLOAD_POLICY_URL:
            return FakeResponse(
                {
                    "data": {
                        "policy": "policy-token",
                        "signature": "signature-token",
                        "upload_dir": "dashscope-instant/test-dir",
                        "upload_host": "https://dashscope-file-test.oss-cn-beijing.aliyuncs.com",
                        "oss_access_key_id": "oss-ak",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                        "max_file_size_mb": 1,
                    }
                }
            )
        if url == "https://result.example/transcription.json":
            return FakeResponse(self.local_result)
        return FakeResponse({}, 404)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url == "https://dashscope-file-test.oss-cn-beijing.aliyuncs.com":
            return FakeResponse({})
        if url == fasr.TRANSCRIPTION_URL:
            return FakeResponse({"output": {"task_status": "PENDING", "task_id": "task-123"}})
        if url == fasr.TASK_URL_TEMPLATE.format(task_id="task-123"):
            return FakeResponse(
                {
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [
                            {
                                "file_url": "oss://dashscope-instant/test-dir/audio.wav",
                                "transcription_url": "https://result.example/transcription.json",
                                "subtask_status": "SUCCEEDED",
                            }
                        ],
                    }
                }
            )
        return FakeResponse({}, 404)


OFFICIAL_SHAPE_RESULT = {
    "transcripts": [
        {
            "sentences": [
                {
                    "begin_time": 0,
                    "end_time": 3600,
                    "text": "你好欢迎观看今天的内容",
                    "speaker_id": 0,
                    "words": [
                        {"begin_time": 0, "end_time": 400, "text": "你好", "punctuation": "，"},
                        {"begin_time": 400, "end_time": 900, "text": "欢迎", "punctuation": ""},
                        {"begin_time": 900, "end_time": 1300, "text": "观看", "punctuation": ""},
                        {"begin_time": 1300, "end_time": 1800, "text": "今天", "punctuation": ""},
                        {"begin_time": 1800, "end_time": 2400, "text": "的内容", "punctuation": "。"},
                    ],
                }
            ]
        }
    ]
}


class FunAsrSrtConversionTests(unittest.TestCase):
    def test_official_shape_words_convert_ms_and_speaker_label(self):
        srt = fasr.fun_asr_result_to_srt(OFFICIAL_SHAPE_RESULT, max_chars=20, max_duration=3.5)

        self.assertIn("1\n00:00:00,000 --> 00:00:00,400\n说话人1: 你好，", srt)
        self.assertIn("2\n00:00:00,400 --> 00:00:02,400\n说话人1: 欢迎观看今天的内容。", srt)
        self.assertNotIn("00:06:40,000", srt, "milliseconds must not be treated as seconds")

    def test_long_word_sequence_splits_into_fine_blocks(self):
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": 0,
                            "end_time": 6000,
                            "speaker_id": 1,
                            "words": [
                                {"begin_time": i * 500, "end_time": (i + 1) * 500, "text": token, "punctuation": ""}
                                for i, token in enumerate(["这是", "一个", "很长", "字幕", "需要", "拆分"])
                            ],
                        }
                    ]
                }
            ]
        }
        srt = fasr.fun_asr_result_to_srt(result, max_chars=4, max_duration=10)

        self.assertGreaterEqual(srt.count("\n说话人2:"), 3)
        self.assertIn("1\n00:00:00,000", srt)

    def test_sentence_fallback_uses_ms_without_zero_duration(self):
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": 1000,
                            "end_time": 3000,
                            "text": "没有词级时间戳也可以拆分。",
                            "speaker_id": 0,
                            "words": [],
                        }
                    ]
                }
            ]
        }
        srt = fasr.fun_asr_result_to_srt(result, max_chars=5)

        self.assertIn("00:00:01,000", srt)
        self.assertIn("说话人1:", srt)
        self.assertNotIn("--> 00:00:01,000\n", srt)

    def test_empty_result_raises_clear_error(self):
        with self.assertRaises(fasr.FunAsrError):
            fasr.fun_asr_result_to_srt({"transcripts": []})

    def test_malformed_word_timestamp_raises_fun_asr_error(self):
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": 0,
                            "end_time": 1000,
                            "speaker_id": 0,
                            "words": [
                                {"begin_time": "bad", "end_time": 500, "text": "坏时间", "punctuation": ""}
                            ],
                        }
                    ]
                }
            ]
        }

        with self.assertRaises(fasr.FunAsrError):
            fasr.fun_asr_result_to_srt(result)

    def test_malformed_sentence_timestamp_raises_fun_asr_error(self):
        result = {
            "transcripts": [
                {
                    "sentences": [
                        {
                            "begin_time": "bad",
                            "end_time": 1000,
                            "text": "坏时间",
                            "speaker_id": 0,
                            "words": [],
                        }
                    ]
                }
            ]
        }

        with self.assertRaises(fasr.FunAsrError):
            fasr.fun_asr_result_to_srt(result)


class FunAsrServiceTests(unittest.TestCase):
    def test_create_with_fun_asr_uses_expected_rest_flow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            subtitle_file = Path(tmp_dir) / "out.srt"
            session = FakeSession(OFFICIAL_SHAPE_RESULT)

            result_path = fasr.create_with_fun_asr(
                str(local_file),
                subtitle_file=str(subtitle_file),
                api_key="sk-test",
                speaker_count=2,
                poll_interval=0,
                session=session,
            )

            self.assertEqual(str(subtitle_file), result_path)
            self.assertTrue(subtitle_file.exists())
            self.assertIn("说话人1:", subtitle_file.read_text(encoding="utf-8"))

        policy_call = session.calls[0]
        self.assertEqual("GET", policy_call[0])
        self.assertEqual(fasr.UPLOAD_POLICY_URL, policy_call[1])
        self.assertEqual({"action": "getPolicy", "model": "fun-asr"}, policy_call[2]["params"])
        self.assertEqual("Bearer sk-test", policy_call[2]["headers"]["Authorization"])

        upload_call = session.calls[1]
        self.assertEqual("POST", upload_call[0])
        self.assertEqual("https://dashscope-file-test.oss-cn-beijing.aliyuncs.com", upload_call[1])
        upload_data = upload_call[2]["data"]
        self.assertEqual("oss-ak", upload_data["OSSAccessKeyId"])
        self.assertEqual("policy-token", upload_data["policy"])
        self.assertEqual("signature-token", upload_data["Signature"])
        self.assertEqual("dashscope-instant/test-dir/audio.wav", upload_data["key"])
        self.assertEqual("200", upload_data["success_action_status"])

        submit_call = session.calls[2]
        self.assertEqual(fasr.TRANSCRIPTION_URL, submit_call[1])
        headers = submit_call[2]["headers"]
        self.assertEqual("enable", headers["X-DashScope-Async"])
        self.assertEqual("enable", headers["X-DashScope-OssResourceResolve"])
        payload = submit_call[2]["json"]
        self.assertEqual("fun-asr", payload["model"])
        self.assertEqual(["oss://dashscope-instant/test-dir/audio.wav"], payload["input"]["file_urls"])
        self.assertTrue(payload["parameters"]["diarization_enabled"])
        self.assertEqual(2, payload["parameters"]["speaker_count"])

        poll_call = session.calls[3]
        self.assertEqual("POST", poll_call[0])
        self.assertTrue(poll_call[1].endswith("/api/v1/tasks/task-123"))

        download_call = session.calls[4]
        self.assertEqual(("GET", "https://result.example/transcription.json"), download_call[:2])

    def test_upload_policy_size_validation_fails_before_upload(self):
        policy = fasr.UploadPolicy(
            upload_host="https://upload.example",
            upload_dir="dashscope-instant/test",
            policy="p",
            signature="s",
            oss_access_key_id="ak",
            max_file_size_mb=0.000001,
        )
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"too-large")
            f.flush()
            with self.assertRaises(fasr.FunAsrError):
                fasr.upload_to_temporary_oss(f.name, policy, session=FakeSession({}))

    def test_failed_subtask_raises(self):
        class FailedSession(FakeSession):
            def post(self, url, **kwargs):
                if url == fasr.TASK_URL_TEMPLATE.format(task_id="task-123"):
                    return FakeResponse(
                        {
                            "output": {
                                "task_status": "SUCCEEDED",
                                "results": [{"subtask_status": "FAILED"}],
                            }
                        }
                    )
                return super().post(url, **kwargs)

        with self.assertRaises(fasr.FunAsrError):
            fasr.poll_transcription_task("sk-test", "task-123", poll_interval=0, session=FailedSession({}))

    def test_missing_api_key_raises_before_request(self):
        session = FakeSession(OFFICIAL_SHAPE_RESULT)

        with self.assertRaises(fasr.FunAsrError):
            fasr.request_upload_policy("", session=session)

        self.assertEqual([], session.calls)

    def test_upload_policy_http_error_raises(self):
        class PolicyHttpErrorSession(FakeSession):
            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return FakeResponse({}, status_code=403)

        with self.assertRaises(fasr.FunAsrError):
            fasr.request_upload_policy("sk-test", session=PolicyHttpErrorSession({}))

    def test_malformed_upload_policy_raises(self):
        class MalformedPolicySession(FakeSession):
            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return FakeResponse({"data": {"policy": "missing-required-fields"}})

        with self.assertRaises(fasr.FunAsrError):
            fasr.request_upload_policy("sk-test", session=MalformedPolicySession({}))

    def test_upload_http_failure_raises(self):
        class UploadFailureSession(FakeSession):
            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({}, status_code=500)

        policy = fasr.UploadPolicy(
            upload_host="https://upload.example",
            upload_dir="dashscope-instant/test",
            policy="p",
            signature="s",
            oss_access_key_id="ak",
            max_file_size_mb=1,
        )
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"audio")
            f.flush()
            with self.assertRaises(fasr.FunAsrError):
                fasr.upload_to_temporary_oss(f.name, policy, session=UploadFailureSession({}))

    def test_submit_failure_raises(self):
        class SubmitFailureSession(FakeSession):
            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({}, status_code=500)

        with self.assertRaises(fasr.FunAsrError):
            fasr.submit_transcription_task("sk-test", "oss://file", session=SubmitFailureSession({}))

    def test_poll_timeout_raises(self):
        class PendingSession(FakeSession):
            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"output": {"task_status": "RUNNING"}})

        with self.assertRaises(fasr.FunAsrError):
            fasr.poll_transcription_task("sk-test", "task-123", poll_interval=0, timeout=-1, session=PendingSession({}))

    def test_task_failed_status_raises(self):
        class FailedTaskSession(FakeSession):
            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"output": {"task_status": "FAILED"}})

        with self.assertRaises(fasr.FunAsrError):
            fasr.poll_transcription_task("sk-test", "task-123", poll_interval=0, session=FailedTaskSession({}))

    def test_missing_transcription_url_raises(self):
        with self.assertRaises(fasr.FunAsrError):
            fasr.download_transcription_result("", session=FakeSession({}))

    def test_malformed_downloaded_json_raises(self):
        class MalformedDownloadSession(FakeSession):
            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return InvalidJsonResponse()

        with self.assertRaises(fasr.FunAsrError):
            fasr.download_transcription_result("https://result.example/bad.json", session=MalformedDownloadSession({}))


class LocalFunAsrServiceTests(unittest.TestCase):
    def test_request_local_fun_asr_posts_file_and_options(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好", "srt_file": "/tmp/out.srt"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            session = LocalSession()

            result = fasr.request_local_fun_asr(
                str(local_file),
                api_url="127.0.0.1:7860",
                hotword="NarratoAI",
                enable_spk=True,
                timeout=123,
                session=session,
            )

        self.assertEqual("你好", result["text"])
        self.assertEqual("POST", session.calls[0][0])
        self.assertEqual("http://127.0.0.1:7860/asr", session.calls[0][1])
        self.assertEqual({"hotword": "NarratoAI", "enable_spk": "true"}, session.calls[0][2]["data"])
        self.assertEqual(123, session.calls[0][2]["timeout"])
        self.assertIn("file", session.calls[0][2]["files"])

    def test_request_local_fun_asr_falls_back_to_openai_transcriptions_on_404(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                if url.endswith("/asr"):
                    return FakeResponse({"detail": "Not Found"}, status_code=404)
                return FakeResponse(
                    {
                        "text": "你好",
                        "segments": [{"start": 0.0, "end": 1.2, "text": "你好"}],
                    }
                )

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            session = LocalSession()

            result = fasr.request_local_fun_asr(
                str(local_file),
                api_url="http://127.0.0.1:7860",
                enable_spk=True,
                session=session,
            )

        self.assertEqual("你好", result["text"])
        self.assertEqual("http://127.0.0.1:7860/asr", session.calls[0][1])
        self.assertEqual("http://127.0.0.1:7860/v1/audio/transcriptions", session.calls[1][1])
        self.assertEqual(
            {"model": "sensevoice", "response_format": "verbose_json", "spk": "true"},
            session.calls[1][2]["data"],
        )

    def test_request_local_fun_asr_prefers_explicit_openai_base_url(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            session = LocalSession()

            fasr.request_local_fun_asr(
                str(local_file),
                api_url="http://127.0.0.1:8000/v1",
                session=session,
            )

        self.assertEqual(1, len(session.calls))
        self.assertEqual("http://127.0.0.1:8000/v1/audio/transcriptions", session.calls[0][1])
        self.assertEqual(
            {"model": "sensevoice", "response_format": "verbose_json"},
            session.calls[0][2]["data"],
        )

    def test_create_with_local_fun_asr_copies_pack_srt_file(self):
        class LocalSession:
            def __init__(self, srt_file):
                self.srt_file = srt_file
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好", "srt_file": str(self.srt_file)})

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            pack_srt = Path(tmp_dir) / "pack.srt"
            pack_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")
            subtitle_file = Path(tmp_dir) / "out.srt"

            result_path = fasr.create_with_local_fun_asr(
                str(local_file),
                subtitle_file=str(subtitle_file),
                api_url="http://127.0.0.1:7860",
                session=LocalSession(pack_srt),
            )

            self.assertEqual(str(subtitle_file), result_path)
            self.assertEqual(pack_srt.read_text(encoding="utf-8"), subtitle_file.read_text(encoding="utf-8"))

    def test_create_with_local_fun_asr_downloads_relative_srt(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好", "downloads": {"srt": "/download/result.srt"}})

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return FakeResponse(text="1\n00:00:00,000 --> 00:00:01,000\n你好\n")

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            subtitle_file = Path(tmp_dir) / "out.srt"
            session = LocalSession()

            result_path = fasr.create_with_local_fun_asr(
                str(local_file),
                subtitle_file=str(subtitle_file),
                api_url="http://127.0.0.1:7860/asr",
                session=session,
            )

            self.assertEqual(str(subtitle_file), result_path)
            self.assertEqual("http://127.0.0.1:7860/download/result.srt", session.calls[1][1])
            self.assertIn("你好", subtitle_file.read_text(encoding="utf-8"))

    def test_local_fun_asr_result_to_srt_uses_raw_timestamps(self):
        result = {
            "raw": [
                {
                    "text": "你好，世界。",
                    "timestamp": [[0, 300], [300, 600], [600, 900], [900, 1200]],
                }
            ]
        }

        srt = fasr.local_fun_asr_result_to_srt(result, max_chars=20)

        self.assertIn("00:00:00,000 --> 00:00:00,600\n你好，", srt)
        self.assertIn("世界。", srt)

    def test_local_fun_asr_result_to_srt_uses_openai_segments(self):
        result = {
            "text": "你好世界",
            "segments": [
                {"start": 1.2, "end": 2.4, "text": "你好"},
                {"start": 2.4, "end": 3.6, "text": "世界"},
            ],
        }

        srt = fasr.local_fun_asr_result_to_srt(result, max_chars=20)

        self.assertIn("00:00:01,200 --> 00:00:02,400\n你好", srt)
        self.assertIn("00:00:02,400 --> 00:00:03,600\n世界", srt)


class LocalFireRedAsrServiceTests(unittest.TestCase):
    def test_request_local_firered_asr_posts_file_and_options(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好", "srt_url": "/outputs/out.srt"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            session = LocalSession()

            result = fasr.request_local_firered_asr(
                str(local_file),
                api_url="127.0.0.1:7867",
                enable_vad=True,
                enable_lid=False,
                enable_punc=True,
                return_timestamp=True,
                timeout=456,
                session=session,
            )

        self.assertEqual("你好", result["text"])
        self.assertEqual("POST", session.calls[0][0])
        self.assertEqual("http://127.0.0.1:7867/asr", session.calls[0][1])
        self.assertEqual(
            {
                "enable_vad": "true",
                "enable_lid": "false",
                "enable_punc": "true",
                "return_timestamp": "true",
            },
            session.calls[0][2]["data"],
        )
        self.assertEqual(456, session.calls[0][2]["timeout"])
        self.assertIn("file", session.calls[0][2]["files"])

    def test_create_with_local_firered_asr_downloads_srt_url(self):
        class LocalSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse({"text": "你好", "srt_url": "/outputs/result.srt"})

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return FakeResponse(text="1\n00:00:00,000 --> 00:00:01,000\n你好\n")

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_file = Path(tmp_dir) / "audio.wav"
            local_file.write_bytes(b"audio")
            subtitle_file = Path(tmp_dir) / "out.srt"
            session = LocalSession()

            result_path = fasr.create_with_local_firered_asr(
                str(local_file),
                subtitle_file=str(subtitle_file),
                api_url="http://127.0.0.1:7867",
                session=session,
            )

            self.assertEqual(str(subtitle_file), result_path)
            self.assertEqual("http://127.0.0.1:7867/outputs/result.srt", session.calls[1][1])
            self.assertIn("你好", subtitle_file.read_text(encoding="utf-8"))

    def test_firered_asr_result_to_srt_uses_sentence_timestamps(self):
        result = {
            "sentences": [
                {"text": "你好。", "start_ms": 40, "end_ms": 900},
                {"text": "欢迎观看。", "start_ms": 900, "end_ms": 2100},
            ]
        }

        srt = fasr.firered_asr_result_to_srt(result)

        self.assertIn("1\n00:00:00,040 --> 00:00:00,900\n你好。", srt)
        self.assertIn("2\n00:00:00,900 --> 00:00:02,100\n欢迎观看。", srt)


class FunAsrConfigTests(unittest.TestCase):
    def test_save_config_persists_fun_asr_section(self):
        original_config_file = cfg.config_file
        original_fun_asr = cfg.fun_asr
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = Path(tmp_dir) / "config.toml"
                cfg.config_file = str(config_path)
                cfg.fun_asr = {"api_key": "sk-local", "model": "fun-asr"}
                cfg.save_config()
                saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
        finally:
            cfg.config_file = original_config_file
            cfg.fun_asr = original_fun_asr

        self.assertEqual("sk-local", saved["fun_asr"]["api_key"])
        self.assertEqual("fun-asr", saved["fun_asr"]["model"])

    def test_config_example_fun_asr_section_parses(self):
        config_data = tomllib.loads(Path("config.example.toml").read_text(encoding="utf-8"))
        self.assertEqual("local", config_data["fun_asr"]["backend"])
        self.assertEqual("http://127.0.0.1:7860", config_data["fun_asr"]["api_url"])
        self.assertEqual("http://127.0.0.1:7867", config_data["fun_asr"]["firered_api_url"])
        self.assertEqual("fun-asr", config_data["fun_asr"]["model"])
        self.assertIn("api_key", config_data["fun_asr"])


if __name__ == "__main__":
    unittest.main()

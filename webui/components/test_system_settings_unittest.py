import unittest

from webui.components.system_settings import clear_application_cache


class SystemSettingsCacheTests(unittest.TestCase):
    def test_clear_application_cache_clears_runtime_caches(self):
        session_state = {
            "fonts_cache": ["SimHei"],
            "video_files_cache": ["a.mp4"],
            "songs_cache": ["bgm.mp3"],
            "ffmpeg_engine_report": {"ffmpeg_available": True},
            "unrelated": "keep",
        }
        calls = []

        errors = clear_application_cache(
            session_state=session_state,
            clear_streamlit_cache=lambda: calls.append("streamlit"),
            clear_llm_cache=lambda: calls.append("llm"),
            clear_keyframes_cache=lambda: calls.append("keyframes"),
            reset_ffmpeg_detection=lambda: calls.append("ffmpeg"),
        )

        self.assertEqual([], errors)
        self.assertEqual(["streamlit", "llm", "keyframes", "ffmpeg"], calls)
        self.assertEqual({"unrelated": "keep"}, session_state)

    def test_clear_application_cache_reports_clear_failures(self):
        def fail():
            raise RuntimeError("boom")

        errors = clear_application_cache(
            session_state={},
            clear_streamlit_cache=fail,
            clear_llm_cache=lambda: None,
            clear_keyframes_cache=lambda: None,
            reset_ffmpeg_detection=lambda: None,
        )

        self.assertEqual(1, len(errors))
        self.assertIn("boom", errors[0])


if __name__ == "__main__":
    unittest.main()

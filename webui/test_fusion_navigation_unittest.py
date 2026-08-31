import unittest

from webui.components.fusion_project_ui import _options_with_current, _plan_input_fingerprint, _tts_configuration_issue

from webui.fusion_navigation import (
    LEGACY_MODES_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    enter_legacy_modes,
    exit_legacy_modes,
    route_for_legacy_mode,
    selected_route,
    traditional_compatibility_projection,
    traditional_session_to_project_draft,
    transfer_project_to_traditional,
)


class FusionNavigationTests(unittest.TestCase):
    def test_plan_fingerprint_changes_when_same_version_inputs_change(self):
        project = {"project_id": "p1", "active_version_id": "v1"}
        first = _plan_input_fingerprint(
            project, {"subtitle_content": "旧字幕", "visual_evidence": "画面"}, "解说"
        )
        second = _plan_input_fingerprint(
            project, {"subtitle_content": "新字幕", "visual_evidence": "画面"}, "解说"
        )

        self.assertNotEqual(first, second)

    def test_unknown_saved_option_is_preserved(self):
        options, index = _options_with_current(["9:16", "16:9"], "21:9")

        self.assertEqual("21:9", options[index])

    def test_application_defaults_to_project_library(self):
        self.assertEqual(PROJECT_LIBRARY_ROUTE, selected_route({}))

    def test_legacy_fusion_mode_opens_explicit_traditional_fusion(self):
        state = {}

        route_for_legacy_mode("film_vision_fusion", state)

        self.assertEqual(LEGACY_MODES_ROUTE, state["fusion_ui_route"])
        self.assertTrue(state["fusion_traditional_fusion_mode"])

    def test_switching_from_fusion_to_another_legacy_mode_clears_compatibility_label(self):
        state = {"fusion_traditional_fusion_mode": True}

        route_for_legacy_mode("short", state)

        self.assertFalse(state["fusion_traditional_fusion_mode"])
        self.assertFalse(traditional_compatibility_projection(state)["visible"])

    def test_entering_traditional_fusion_preserves_explicit_selection(self):
        state = {}

        enter_legacy_modes(state, fusion=True)

        self.assertEqual(LEGACY_MODES_ROUTE, state["fusion_ui_route"])
        self.assertEqual("film_vision_fusion", state["video_clip_json_path"])

    def test_leaving_traditional_mode_returns_to_project_library(self):
        state = {
            "fusion_ui_route": LEGACY_MODES_ROUTE,
            "fusion_traditional_fusion_mode": True,
            "video_clip_json_path": "film_vision_fusion",
            "fusion_traditional_transfer": {"project_name": "旧转移"},
            "fusion_traditional_transfer_pending": True,
            "fusion_traditional_transfer_active": True,
        }

        route = exit_legacy_modes(state)

        self.assertEqual(PROJECT_LIBRARY_ROUTE, route)
        self.assertEqual(PROJECT_LIBRARY_ROUTE, state["fusion_ui_route"])
        self.assertFalse(state["fusion_traditional_fusion_mode"])
        self.assertNotIn("fusion_traditional_transfer", state)
        self.assertNotIn("fusion_traditional_transfer_pending", state)
        self.assertNotIn("fusion_traditional_transfer_active", state)

    def test_traditional_fusion_projects_an_explicit_session_boundary(self):
        projection = traditional_compatibility_projection({
            "fusion_ui_route": LEGACY_MODES_ROUTE,
            "fusion_traditional_fusion_mode": True,
        })

        self.assertTrue(projection["visible"])
        self.assertEqual("Traditional Compatibility Mode", projection["title"])
        self.assertIn("不会回写", projection["notice"])

    def test_non_fusion_legacy_mode_does_not_show_project_return(self):
        projection = traditional_compatibility_projection({
            "fusion_ui_route": LEGACY_MODES_ROUTE,
            "fusion_traditional_fusion_mode": False,
        })

        self.assertFalse(projection["visible"])

    def test_project_transfer_copies_only_non_secret_configuration_and_sources(self):
        state = {}
        project = {
            "name": "测试项目",
            "project_settings": {
                "tts_engine": "edge_tts", "voice_profile": "zh-CN-XiaoxiaoNeural",
                "voice_parameters": {"rate": 1.1}, "subtitle_policy": "source_or_asr",
            },
            "source_video_sequence": [
                {"path": "D:/movies/one.mp4", "subtitle_path": "D:/movies/one.srt"},
            ],
        }

        transfer_project_to_traditional(project, state)

        self.assertEqual(LEGACY_MODES_ROUTE, state["fusion_ui_route"])
        self.assertEqual("film_vision_fusion", state["video_clip_json_path"])
        self.assertEqual("D:/movies/one.mp4", state["fusion_traditional_transfer"]["source_paths"][0])
        self.assertNotIn("api_key", state["fusion_traditional_transfer"])

    def test_traditional_session_can_be_adopted_as_a_non_secret_project_draft(self):
        draft = traditional_session_to_project_draft({
            "video_theme": "旧会话", "video_origin_paths": ["D:/movies/one.mp4"],
            "subtitle_paths": ["D:/movies/one.srt"], "tts_engine": "edge_tts",
            "voice_name": "zh-CN-XiaoxiaoNeural", "voice_rate": 1.1,
            "voice_volume": 0.8, "voice_pitch": 1.0, "api_key": "must-not-copy",
        })

        self.assertEqual("旧会话", draft["name"])
        self.assertEqual(["D:/movies/one.mp4"], draft["source_paths"])
        self.assertEqual("edge_tts", draft["settings"]["tts_engine"])
        self.assertNotIn("api_key", draft["settings"])

    def test_cloud_tts_without_credentials_is_blocked_before_render(self):
        from app.config import config
        from unittest.mock import patch

        with patch.dict(config.azure, {"speech_region": "", "speech_key": ""}, clear=False):
            issue = _tts_configuration_issue({"tts_engine": "azure_speech", "voice_profile": "voice"})

        self.assertIn("Azure Speech", issue)


if __name__ == "__main__":
    unittest.main()

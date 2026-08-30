import unittest

from webui.components.fusion_project_ui import _options_with_current, _plan_input_fingerprint

from webui.fusion_navigation import (
    LEGACY_MODES_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    enter_legacy_modes,
    route_for_legacy_mode,
    selected_route,
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

    def test_entering_traditional_fusion_preserves_explicit_selection(self):
        state = {}

        enter_legacy_modes(state, fusion=True)

        self.assertEqual(LEGACY_MODES_ROUTE, state["fusion_ui_route"])
        self.assertEqual("film_vision_fusion", state["video_clip_json_path"])

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


if __name__ == "__main__":
    unittest.main()

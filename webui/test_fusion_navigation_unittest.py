import unittest

from webui.components.fusion_project_ui import _options_with_current, _plan_input_fingerprint

from webui.fusion_navigation import (
    LEGACY_MODES_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    enter_legacy_modes,
    route_for_legacy_mode,
    selected_route,
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

    def test_legacy_fusion_mode_redirects_to_project_library(self):
        state = {}

        route_for_legacy_mode("film_vision_fusion", state)

        self.assertEqual(PROJECT_LIBRARY_ROUTE, state["fusion_ui_route"])
        self.assertTrue(state["fusion_legacy_redirect_notice"])

    def test_entering_traditional_modes_clears_stale_fusion_selection(self):
        state = {"video_clip_json_path": "film_vision_fusion"}

        enter_legacy_modes(state)

        self.assertEqual(LEGACY_MODES_ROUTE, state["fusion_ui_route"])
        self.assertEqual("", state["video_clip_json_path"])


if __name__ == "__main__":
    unittest.main()

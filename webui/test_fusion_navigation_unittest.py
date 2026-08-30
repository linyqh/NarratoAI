import unittest

from webui.fusion_navigation import (
    LEGACY_MODES_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    enter_legacy_modes,
    route_for_legacy_mode,
    selected_route,
)


class FusionNavigationTests(unittest.TestCase):
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

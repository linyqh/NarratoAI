import unittest

from webui.fusion_navigation import (
    PROJECT_LIBRARY_ROUTE,
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


if __name__ == "__main__":
    unittest.main()

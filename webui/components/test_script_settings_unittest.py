import unittest
from unittest.mock import patch

from webui.components import script_settings


class FilmVisionFusionOutputGuardTests(unittest.TestCase):
    def test_unverified_fusion_artifact_is_regression_only(self):
        state = {
            "video_clip_json_path": script_settings.MODE_FILM_VISION_FUSION,
            "fusion_visual_regression_only": True,
        }

        with patch.object(script_settings.st, "session_state", state):
            self.assertTrue(script_settings.is_unverified_fusion_regression())

    def test_verified_fusion_and_other_script_modes_are_not_blocked(self):
        cases = (
            {
                "video_clip_json_path": script_settings.MODE_FILM_VISION_FUSION,
                "fusion_visual_regression_only": False,
            },
        )
        for state in cases:
            with self.subTest(state=state), patch.object(
                script_settings.st, "session_state", state
            ):
                self.assertFalse(script_settings.is_unverified_fusion_regression())


if __name__ == "__main__":
    unittest.main()

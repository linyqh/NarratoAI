import unittest

from webui.components.subtitle_settings import _normalize_subtitle_preview_orientation


class SubtitleSettingsPreviewOrientationTests(unittest.TestCase):
    def test_normalize_subtitle_preview_orientation_accepts_canonical_values(self):
        self.assertEqual("portrait", _normalize_subtitle_preview_orientation("portrait"))
        self.assertEqual("landscape", _normalize_subtitle_preview_orientation("landscape"))

    def test_normalize_subtitle_preview_orientation_migrates_legacy_labels(self):
        self.assertEqual("portrait", _normalize_subtitle_preview_orientation("Portrait Safe Area"))
        self.assertEqual("landscape", _normalize_subtitle_preview_orientation("Landscape Safe Area"))

    def test_normalize_subtitle_preview_orientation_falls_back_to_portrait(self):
        self.assertEqual("portrait", _normalize_subtitle_preview_orientation(None))
        self.assertEqual("portrait", _normalize_subtitle_preview_orientation("unexpected"))


if __name__ == "__main__":
    unittest.main()

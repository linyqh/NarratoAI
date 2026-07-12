import unittest

from webui.components.audio_settings import (
    _normalize_source_pills_value,
    get_tts_engine_options,
)


def zh_tr(key):
    return {
        "Select from Resource Directory": "从资源目录选择",
        "Upload Reference Audio": "上传参考音频",
        "Upload Background Music": "上传背景音乐",
    }.get(key, key)


class AudioSettingsSourcePillsTests(unittest.TestCase):
    def test_tts_engine_options_include_indextts_15_macos_as_local_engine(self):
        options = get_tts_engine_options(lambda key: {
            "Local Deployment": "本地部署",
            "Cloud Service": "云服务",
        }.get(key, key))

        self.assertEqual(
            "IndexTTS-1.5-macOS [本地部署]",
            options["indextts_macos"],
        )

    def test_normalize_source_pills_value_keeps_canonical_value(self):
        options = {
            "resource": "Select from Resource Directory",
            "upload": "Upload Reference Audio",
        }

        self.assertEqual("upload", _normalize_source_pills_value("upload", options, "resource", zh_tr))

    def test_normalize_source_pills_value_migrates_current_translated_label(self):
        options = {
            "resource": "Select from Resource Directory",
            "upload": "Upload Reference Audio",
        }

        self.assertEqual("resource", _normalize_source_pills_value("从资源目录选择", options, "upload", zh_tr))

    def test_normalize_source_pills_value_migrates_untranslated_label_key(self):
        options = {
            "resource": "Select from Resource Directory",
            "upload": "Upload Background Music",
        }

        self.assertEqual("upload", _normalize_source_pills_value("Upload Background Music", options, "resource", zh_tr))

    def test_normalize_source_pills_value_falls_back_to_default(self):
        options = {
            "resource": "Select from Resource Directory",
            "upload": "Upload Reference Audio",
        }

        self.assertEqual("resource", _normalize_source_pills_value("invalid", options, "resource", zh_tr))


if __name__ == "__main__":
    unittest.main()

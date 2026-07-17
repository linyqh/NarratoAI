import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from app.config import config as cfg
from app.config.defaults import (
    DEFAULT_ATLASCLOUD_BASE_URL,
    DEFAULT_ATLASCLOUD_TEXT_MODEL_NAME,
    get_openai_compatible_ui_values,
    normalize_openai_compatible_model_name,
)


class ConfigBootstrapDefaultsTests(unittest.TestCase):
    def test_save_config_keeps_macos_tts_settings_independent(self):
        macos_settings = {
            "api_url": "http://127.0.0.1:7866",
            "reference_audio": "/tmp/macos-reference.wav",
            "speed": 1.1,
        }
        windows_settings = {
            "api_url": "http://127.0.0.1:8081/tts",
            "reference_audio": "/tmp/windows-reference.wav",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            with (
                patch.object(cfg, "config_file", str(config_path)),
                patch.object(cfg, "indextts_macos", dict(macos_settings)),
                patch.object(cfg, "indextts", dict(windows_settings)),
            ):
                cfg.save_config()
            saved_config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(macos_settings, saved_config["indextts_macos"])
        self.assertEqual(windows_settings, saved_config["indextts"])

    def test_load_config_bootstraps_webui_llm_defaults(self):
        original_root_dir = cfg.root_dir
        original_config_file = cfg.config_file

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            example_file = tmp_path / "config.example.toml"
            example_file.write_text(
                """
[app]
vision_llm_provider = "openai"
vision_openai_model_name = "gemini/gemini-2.0-flash-lite"
vision_openai_api_key = ""
vision_openai_base_url = ""
text_llm_provider = "openai"
text_openai_model_name = "deepseek/deepseek-chat"
text_openai_api_key = ""
text_openai_base_url = ""
hide_config = true
""".strip()
                + "\n",
                encoding="utf-8",
            )

            config_path = tmp_path / "config.toml"
            try:
                cfg.root_dir = str(tmp_path)
                cfg.config_file = str(config_path)

                config_data = cfg.load_config()
                saved_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            finally:
                cfg.root_dir = original_root_dir
                cfg.config_file = original_config_file

        self.assertEqual("openai", config_data["app"]["vision_llm_provider"])
        self.assertEqual("Qwen/Qwen3.5-122B-A10B", config_data["app"]["vision_openai_model_name"])
        self.assertEqual("https://api.siliconflow.cn/v1", config_data["app"]["vision_openai_base_url"])
        self.assertEqual(1.0, config_data["app"]["vision_openai_temperature"])
        self.assertEqual(0.95, config_data["app"]["vision_openai_top_p"])
        self.assertEqual("openai", config_data["app"]["text_llm_provider"])
        self.assertEqual("Pro/zai-org/GLM-5", config_data["app"]["text_openai_model_name"])
        self.assertEqual("https://api.siliconflow.cn/v1", config_data["app"]["text_openai_base_url"])
        self.assertEqual(DEFAULT_ATLASCLOUD_TEXT_MODEL_NAME, config_data["app"]["text_atlascloud_model_name"])
        self.assertEqual(DEFAULT_ATLASCLOUD_BASE_URL, config_data["app"]["text_atlascloud_base_url"])
        self.assertEqual("", config_data["app"]["text_atlascloud_api_key"])
        self.assertEqual(1.0, config_data["app"]["text_openai_temperature"])
        self.assertEqual(0.95, config_data["app"]["text_openai_top_p"])
        self.assertEqual("Qwen/Qwen3.5-122B-A10B", saved_config["app"]["vision_openai_model_name"])
        self.assertEqual("Pro/zai-org/GLM-5", saved_config["app"]["text_openai_model_name"])
        self.assertTrue(saved_config["app"]["hide_config"])

    def test_legacy_indextts2_config_is_migrated_to_indextts_15(self):
        migrated = cfg.migrate_indextts_config(
            {
                "indextts2": {"api_url": "http://127.0.0.1:8081/tts"},
                "ui": {
                    "tts_engine": "indextts2",
                    "voice_name": "indextts2:/tmp/reference.wav",
                },
            }
        )

        self.assertEqual("http://127.0.0.1:8081/tts", migrated["indextts"]["api_url"])
        self.assertNotIn("indextts2", migrated)
        self.assertEqual("indextts", migrated["ui"]["tts_engine"])
        self.assertEqual("indextts:/tmp/reference.wav", migrated["ui"]["voice_name"])

    def test_indextts2_config_is_kept_as_separate_engine(self):
        migrated = cfg.migrate_indextts_config(
            {
                "indextts": {"api_url": "http://127.0.0.1:8081/tts"},
                "indextts2": {
                    "api_url": "http://192.168.3.6:7863/tts",
                    "emotion_mode": "speaker",
                },
                "ui": {
                    "tts_engine": "indextts2",
                    "voice_name": "indextts2:/tmp/reference.wav",
                },
            }
        )

        self.assertEqual("http://127.0.0.1:8081/tts", migrated["indextts"]["api_url"])
        self.assertEqual("http://192.168.3.6:7863/tts", migrated["indextts2"]["api_url"])
        self.assertEqual("indextts2", migrated["ui"]["tts_engine"])
        self.assertEqual("indextts2:/tmp/reference.wav", migrated["ui"]["voice_name"])


class OpenAICompatibleModelDefaultsTests(unittest.TestCase):
    def test_ui_keeps_full_model_name_and_openai_provider(self):
        provider, model_name = get_openai_compatible_ui_values(
            "Qwen/Qwen3.5-122B-A10B",
            "fallback-model",
        )

        self.assertEqual("openai", provider)
        self.assertEqual("Qwen/Qwen3.5-122B-A10B", model_name)

    def test_normalize_only_strips_openai_prefix(self):
        self.assertEqual(
            "Qwen/Qwen3.5-122B-A10B",
            normalize_openai_compatible_model_name("openai/Qwen/Qwen3.5-122B-A10B"),
        )
        self.assertEqual(
            "Qwen/Qwen3.5-122B-A10B",
            normalize_openai_compatible_model_name("Qwen/Qwen3.5-122B-A10B"),
        )


if __name__ == "__main__":
    unittest.main()

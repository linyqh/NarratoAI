import os
import socket
import toml
import shutil
from loguru import logger

from app.config.defaults import build_default_app_config, merge_missing_app_defaults

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config_file = f"{root_dir}/config.toml"
version_file = f"{root_dir}/project_version"
INDEXTTS_ENGINE = "indextts"
INDEXTTS_LEGACY_ENGINE = "indextts2"
INDEXTTS_DISPLAY_NAME = "IndexTTS-1.5"
INDEXTTS_VOICE_PREFIX = f"{INDEXTTS_ENGINE}:"
INDEXTTS_LEGACY_VOICE_PREFIX = f"{INDEXTTS_LEGACY_ENGINE}:"


def normalize_tts_engine_name(tts_engine: str) -> str:
    if tts_engine == INDEXTTS_LEGACY_ENGINE:
        return INDEXTTS_ENGINE
    return tts_engine


def normalize_indextts_voice_prefix(voice_name: str) -> str:
    if isinstance(voice_name, str) and voice_name.startswith(INDEXTTS_LEGACY_VOICE_PREFIX):
        return f"{INDEXTTS_VOICE_PREFIX}{voice_name[len(INDEXTTS_LEGACY_VOICE_PREFIX):]}"
    return voice_name


def migrate_indextts_config(config_data):
    if "indextts" not in config_data and INDEXTTS_LEGACY_ENGINE in config_data:
        config_data["indextts"] = config_data[INDEXTTS_LEGACY_ENGINE]

    ui_config = config_data.get("ui")
    if isinstance(ui_config, dict):
        if "tts_engine" in ui_config:
            ui_config["tts_engine"] = normalize_tts_engine_name(ui_config.get("tts_engine", ""))
        if "voice_name" in ui_config:
            ui_config["voice_name"] = normalize_indextts_voice_prefix(ui_config.get("voice_name", ""))
    return config_data


def get_version_from_file():
    """从project_version文件中读取版本号"""
    try:
        if os.path.isfile(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "0.1.0"  # 默认版本号
    except Exception as e:
        logger.error(f"读取版本号文件失败: {str(e)}")
        return "0.1.0"  # 默认版本号


def load_config():
    # fix: IsADirectoryError: [Errno 21] Is a directory: '/NarratoAI/config.toml'
    if os.path.isdir(config_file):
        shutil.rmtree(config_file)

    if not os.path.isfile(config_file):
        _config_ = build_default_config()
        write_config_file(_config_)
        logger.info("create config.toml with shared defaults")
        return migrate_indextts_config(_config_)

    logger.info(f"load config from file: {config_file}")

    _config_ = load_toml_file(config_file)
    _config_["app"] = merge_missing_app_defaults(_config_.get("app", {}))
    return migrate_indextts_config(_config_)


def load_toml_file(file_path):
    """Load a TOML file and fall back to utf-8-sig when needed."""
    try:
        return toml.load(file_path)
    except Exception as e:
        logger.warning(f"load config failed: {str(e)}, try to load as utf-8-sig")
        with open(file_path, mode="r", encoding="utf-8-sig") as fp:
            _cfg_content = fp.read()
            return toml.loads(_cfg_content)


def build_default_config():
    """Build the initial config file content for a fresh installation."""
    example_file = f"{root_dir}/config.example.toml"
    config_data = {}
    if os.path.isfile(example_file):
        config_data = load_toml_file(example_file)

    config_data["app"] = build_default_app_config(config_data.get("app", {}))
    return migrate_indextts_config(config_data)


def write_config_file(config_data):
    parent_dir = os.path.dirname(config_file)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(config_file, "w", encoding="utf-8") as f:
        f.write(toml.dumps(config_data))


def save_config():
    with open(config_file, "w", encoding="utf-8") as f:
        _cfg["app"] = app
        _cfg["proxy"] = proxy
        _cfg["azure"] = azure
        _cfg["tencent"] = tencent
        _cfg["soulvoice"] = soulvoice
        _cfg["ui"] = ui
        _cfg["tts_qwen"] = tts_qwen
        _cfg["fun_asr"] = fun_asr
        _cfg["indextts"] = indextts
        _cfg.pop(INDEXTTS_LEGACY_ENGINE, None)
        _cfg["doubaotts"] = doubaotts
        f.write(toml.dumps(_cfg))


_cfg = load_config()
app = _cfg.get("app", {})
whisper = _cfg.get("whisper", {})
proxy = _cfg.get("proxy", {})
azure = _cfg.get("azure", {})
tencent = _cfg.get("tencent", {})
soulvoice = _cfg.get("soulvoice", {})
ui = _cfg.get("ui", {})
frames = _cfg.get("frames", {})
tts_qwen = _cfg.get("tts_qwen", {})
fun_asr = _cfg.get("fun_asr", {})
indextts = _cfg.get("indextts", _cfg.get(INDEXTTS_LEGACY_ENGINE, {}))
doubaotts = _cfg.get("doubaotts", {})

hostname = socket.gethostname()

log_level = _cfg.get("log_level", "DEBUG")
listen_host = _cfg.get("listen_host", "0.0.0.0")
listen_port = _cfg.get("listen_port", 8080)
project_name = _cfg.get("project_name", "NarratoAI")
project_description = _cfg.get(
    "project_description",
    "<a href='https://github.com/linyqh/NarratoAI'>https://github.com/linyqh/NarratoAI</a>",
)
# 从文件读取版本号，而不是从配置文件中获取
project_version = get_version_from_file()
reload_debug = False

imagemagick_path = app.get("imagemagick_path", "")
if imagemagick_path and os.path.isfile(imagemagick_path):
    os.environ["IMAGEMAGICK_BINARY"] = imagemagick_path

ffmpeg_path = app.get("ffmpeg_path", "")
if ffmpeg_path and os.path.isfile(ffmpeg_path):
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path

logger.info(f"{project_name} v{project_version}")

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
INDEXTTS_DISPLAY_NAME = "IndexTTS-1.5-windows"
INDEXTTS_MACOS_ENGINE = "indextts_macos"
INDEXTTS_MACOS_DISPLAY_NAME = "IndexTTS-1.5-macOS"
INDEXTTS2_ENGINE = "indextts2"
INDEXTTS2_DISPLAY_NAME = "IndexTTS-2"
OMNIVOICE_ENGINE = "omnivoice"
OMNIVOICE_DISPLAY_NAME = "OmniVoice"
VOXCPM_ENGINE = "voxcpm_05b"
VOXCPM_DISPLAY_NAME = "VoxCPM-0.5B"
VOXCPM2_ENGINE = "voxcpm_2b"
VOXCPM2_DISPLAY_NAME = "VoxCPM-2B"
INDEXTTS_VOICE_PREFIX = f"{INDEXTTS_ENGINE}:"
INDEXTTS_MACOS_VOICE_PREFIX = f"{INDEXTTS_MACOS_ENGINE}:"
INDEXTTS2_VOICE_PREFIX = f"{INDEXTTS2_ENGINE}:"
OMNIVOICE_VOICE_PREFIX = f"{OMNIVOICE_ENGINE}:"
VOXCPM_VOICE_PREFIX = f"{VOXCPM_ENGINE}:"
VOXCPM2_VOICE_PREFIX = f"{VOXCPM2_ENGINE}:"
INDEXTTS2_EMOTION_VECTOR_FIELDS = (
    ("happy", "vec_happy"),
    ("angry", "vec_angry"),
    ("sad", "vec_sad"),
    ("afraid", "vec_afraid"),
    ("disgusted", "vec_disgusted"),
    ("melancholic", "vec_melancholic"),
    ("surprised", "vec_surprised"),
    ("calm", "vec_calm"),
)


def normalize_tts_engine_name(tts_engine: str) -> str:
    return tts_engine


def normalize_indextts_voice_prefix(voice_name: str) -> str:
    return voice_name


def get_indextts2_pack_emotion(indextts2_config) -> str:
    """Return the MLX Pack emotion string for current or legacy settings."""
    if not isinstance(indextts2_config, dict):
        return ""

    configured_emotion = str(indextts2_config.get("emotion", "")).strip()
    if configured_emotion:
        return configured_emotion

    emotion_mode = indextts2_config.get("emotion_mode", "speaker")
    if emotion_mode == "text":
        return str(indextts2_config.get("emotion_text", "")).strip()
    if emotion_mode != "vector":
        return ""

    weights = []
    for emotion, field in INDEXTTS2_EMOTION_VECTOR_FIELDS:
        try:
            weight = float(indextts2_config.get(field, 0.0))
        except (TypeError, ValueError):
            continue
        if weight > 0:
            weights.append(f"{emotion}:{weight:g}")
    return ",".join(weights)


def _is_legacy_indextts2_config(indextts2_config) -> bool:
    if not isinstance(indextts2_config, dict):
        return False
    api_url = str(indextts2_config.get("api_url", ""))
    has_indextts2_fields = any(
        key in indextts2_config
        for key in (
            "emotion_mode",
            "emotion_alpha",
            "max_text_tokens_per_segment",
            "max_mel_tokens",
            "vec_calm",
        )
    )
    return "8081" in api_url and not has_indextts2_fields


def migrate_indextts_config(config_data):
    migrated_legacy_indextts2 = _is_legacy_indextts2_config(config_data.get(INDEXTTS2_ENGINE))
    if migrated_legacy_indextts2:
        if "indextts" not in config_data:
            config_data["indextts"] = config_data[INDEXTTS2_ENGINE]
        config_data.pop(INDEXTTS2_ENGINE, None)

    ui_config = config_data.get("ui")
    if isinstance(ui_config, dict):
        if migrated_legacy_indextts2 and ui_config.get("tts_engine") == INDEXTTS2_ENGINE:
            ui_config["tts_engine"] = INDEXTTS_ENGINE
        if ui_config.get("voice_name", "").startswith(INDEXTTS2_VOICE_PREFIX) and ui_config.get("tts_engine") == INDEXTTS_ENGINE:
            ui_config["voice_name"] = f"{INDEXTTS_VOICE_PREFIX}{ui_config['voice_name'][len(INDEXTTS2_VOICE_PREFIX):]}"
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
        _cfg["indextts_macos"] = indextts_macos
        _cfg["indextts2"] = indextts2
        _cfg["omnivoice"] = omnivoice
        _cfg["voxcpm_05b"] = voxcpm_05b
        _cfg["voxcpm_2b"] = voxcpm_2b
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
indextts = _cfg.get("indextts", {})
indextts_macos = _cfg.get("indextts_macos", {})
indextts2 = _cfg.get("indextts2", {})
omnivoice = _cfg.get("omnivoice", {})
voxcpm_05b = _cfg.get("voxcpm_05b", {})
voxcpm_2b = _cfg.get("voxcpm_2b", {})
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

_applied_ffmpeg_dir = None


def apply_ffmpeg_path(ffmpeg_binary: str = "") -> None:
    """Apply the configured FFmpeg binary to this Python process."""
    global _applied_ffmpeg_dir

    if not ffmpeg_binary or not os.path.isfile(ffmpeg_binary):
        return

    ffmpeg_binary = os.path.abspath(os.path.expanduser(ffmpeg_binary))
    ffmpeg_dir = os.path.dirname(ffmpeg_binary)
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_binary

    current_paths = os.environ.get("PATH", "").split(os.pathsep)
    normalized_ffmpeg_dir = os.path.normcase(os.path.abspath(ffmpeg_dir))
    normalized_previous_dir = (
        os.path.normcase(os.path.abspath(_applied_ffmpeg_dir))
        if _applied_ffmpeg_dir
        else None
    )
    filtered_paths = []
    for path_item in current_paths:
        if not path_item:
            continue
        normalized_item = os.path.normcase(os.path.abspath(path_item))
        if normalized_item == normalized_ffmpeg_dir:
            continue
        if normalized_previous_dir and normalized_item == normalized_previous_dir:
            continue
        filtered_paths.append(path_item)

    os.environ["PATH"] = os.pathsep.join([ffmpeg_dir, *filtered_paths])
    _applied_ffmpeg_dir = ffmpeg_dir


ffmpeg_path = app.get("ffmpeg_path", "")
apply_ffmpeg_path(ffmpeg_path)

logger.info(f"{project_name} v{project_version}")

"""
Sonilo (https://sonilo.com) AI 配乐（BGM）集成 —— 可选功能，默认关闭。

将合成完成的视频（未加 BGM）上传到 Sonilo API（`POST /v1/video-to-music`），
根据画面内容与剪辑节奏生成一段背景音乐，作为普通音频文件交还给现有的
合成流程混音。生成的音乐已获授权、可商用（以条款为准）。

设计约束（完全不影响现有 BGM 逻辑）：
  * 默认关闭。仅当用户在 WebUI 中把背景音乐来源切换为 Sonilo，且配置了
    Sonilo API Key（config.toml 的 `sonilo_api_key`，或环境变量
    `SONILO_API_KEY` 兜底）时才会启用。
  * 本模块只负责生成音频文件；音量、淡出、循环与混音全部复用
    app/services/generate_video.py 中现有的音频处理逻辑，解说配音的
    音量压制策略保持不变。
  * 任何失败（超时、HTTP 错误、流中断、时长超限）都只记录日志并返回
    空字符串，由调用方回退到现有的 BGM 逻辑，绝不中断成片任务。
  * 上传属于计费操作，上传前先用 ffprobe 在本地校验视频时长（接口
    目前拒绝超过 6 分钟的视频），避免白传一次注定被拒绝的成片。

接口返回 NDJSON 事件流：`audio_chunk`（base64 音频分片，按 stream_index
分组）、`title`、`complete`（成功终止事件）与 `error`（失败终止事件）。
进度事件与无法解析的行一律忽略。生成的音频为 AAC 编码的 .m4a 文件。

配置（config.toml 的 [app] 段）：
    sonilo_api_key = "..."             # 必填，启用开关
    # sonilo_base_url = "https://api.sonilo.com"
    # sonilo_timeout_seconds = 600
    # sonilo_bgm_prompt = ""           # 可选：配乐风格提示
"""

import base64
import binascii
import json
import os
import subprocess
from typing import Iterable, Optional

import requests
from loguru import logger

from app.config import config

DEFAULT_BASE_URL = "https://api.sonilo.com"
VIDEO_TO_MUSIC_PATH = "/v1/video-to-music"
# 后端生成接口的读超时约为 600 秒。生成一旦开始就会计费，客户端过早超时
# 只会浪费一次已经付费的请求，所以默认读超时与后端保持一致，并允许覆盖。
DEFAULT_TIMEOUT_SECONDS = 600
_CONNECT_TIMEOUT_SECONDS = 15
# 接口目前拒绝超过 6 分钟的视频；上传前先在本地校验时长。
MAX_VIDEO_DURATION_SECONDS = 360


class SoniloError(Exception):
    """Sonilo 配乐生成失败。"""


def get_api_key() -> str:
    """返回配置的 Sonilo API Key（优先 config.toml，其次环境变量）。"""
    api_key = config.app.get("sonilo_api_key", "") or os.getenv("SONILO_API_KEY", "")
    return str(api_key).strip()


def is_enabled() -> bool:
    """仅当配置了 Sonilo API Key 时返回 True。"""
    return bool(get_api_key())


def generate_bgm(video_path: str, save_path: str) -> str:
    """
    上传合成完成的视频（未加 BGM）到 Sonilo，生成配乐并保存到
    `save_path`（.m4a）。

    成功时返回音频文件路径，任何失败都返回空字符串，由调用方回退到
    现有的 BGM 逻辑。本函数绝不抛出异常 —— 配乐问题绝不能中断成片任务。
    """
    if not is_enabled():
        logger.warning("Sonilo 配乐已跳过: 未配置 API Key")
        return ""

    if not video_path or not os.path.isfile(video_path):
        logger.warning(f"Sonilo 配乐已跳过: 视频文件不存在: {video_path}")
        return ""

    # 上传即计费，先在本地校验时长，避免白传一次注定被拒绝的成片。
    duration = _probe_video_duration(video_path)
    if duration and duration > MAX_VIDEO_DURATION_SECONDS:
        logger.warning(
            f"Sonilo 配乐已跳过: 视频时长 {duration:.1f}s 超过接口上限 "
            f"{MAX_VIDEO_DURATION_SECONDS}s"
        )
        return ""

    try:
        audio = _request_video_to_music(video_path)
    except Exception as e:
        # 任何失败（超时、HTTP 错误、流中断）都降级，由调用方回退到
        # 现有 BGM 逻辑，绝不让配乐问题中断成片任务。
        logger.error(f"Sonilo 配乐生成失败: {str(e)}")
        return ""

    try:
        with open(save_path, "wb") as f:
            f.write(audio)
    except OSError as e:
        logger.error(f"Sonilo 配乐文件保存失败: {str(e)}")
        return ""

    logger.success(f"Sonilo 配乐已生成: {save_path}")
    return save_path


def _get_ffprobe_binary() -> str:
    """与 generate_video 保持一致的 ffprobe 查找逻辑（环境变量优先）。"""
    for env_name in ("NARRATO_FFPROBE_EXE", "IMAGEIO_FFPROBE_EXE"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate and os.path.isfile(candidate):
            return candidate
    return "ffprobe"


def _probe_video_duration(video_path: str) -> float:
    """
    尽力而为的本地 ffprobe 时长探测。ffprobe 不可用、超时或输出无法解析
    时返回 0.0，交给后端做最终校验。
    """
    try:
        result = subprocess.run(
            [
                _get_ffprobe_binary(),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                video_path,
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    if result.returncode != 0:
        return 0.0
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0.0


def _error_detail(body: str) -> str:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body
    if isinstance(parsed, dict):
        detail = parsed.get("detail") or parsed.get("error") or parsed.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return body


def _http_error_message(status_code: int, body: str) -> str:
    detail = _error_detail(body)
    if status_code == 401:
        return "Sonilo API Key 无效，请检查配置"
    if status_code == 402:
        return detail or "Sonilo 账户余额不足"
    if status_code == 413:
        return f"视频文件过大: {detail}"
    if status_code == 429:
        return f"触发 Sonilo 频率限制: {detail}"
    return f"Sonilo 接口错误 ({status_code}): {detail}"


def _get_timeout_seconds() -> float:
    try:
        return float(
            config.app.get("sonilo_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        )
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _request_video_to_music(video_path: str) -> bytes:
    base_url = str(config.app.get("sonilo_base_url", "") or DEFAULT_BASE_URL).rstrip(
        "/"
    )
    timeout_seconds = _get_timeout_seconds()

    prompt = str(config.app.get("sonilo_bgm_prompt", "") or "").strip()
    data: Optional[dict] = {"prompt": prompt} if prompt else None
    headers = {"Authorization": f"Bearer {get_api_key()}"}

    logger.info(
        f"正在使用 Sonilo 生成配乐, 视频: {video_path}, "
        f"读超时: {timeout_seconds:.0f}s"
    )

    try:
        with open(video_path, "rb") as video_file:
            files = {
                "video": (os.path.basename(video_path), video_file, "video/mp4"),
            }
            # 生成接口非幂等（生成即计费），失败不做自动重试，直接降级。
            with requests.post(
                f"{base_url}{VIDEO_TO_MUSIC_PATH}",
                headers=headers,
                data=data,
                files=files,
                stream=True,
                timeout=(_CONNECT_TIMEOUT_SECONDS, timeout_seconds),
            ) as response:
                if response.status_code >= 400:
                    body = response.content.decode("utf-8", errors="replace")
                    raise SoniloError(
                        _http_error_message(response.status_code, body)
                    )
                return _consume_ndjson_stream(
                    response.iter_lines(decode_unicode=True)
                )
    except requests.exceptions.Timeout as exc:
        raise SoniloError(
            f"Sonilo 请求超时 ({timeout_seconds:.0f}s)"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise SoniloError(f"Sonilo 请求失败: {str(exc)}") from exc


def _consume_ndjson_stream(lines: Iterable[str]) -> bytes:
    """
    消费 NDJSON 事件流，按 stream_index 分组 base64 音频分片，
    返回第一条音轨。
    """
    streams = {}
    completed = False
    for line in lines:
        if not line or not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "audio_chunk":
            chunk = event.get("data")
            if not isinstance(chunk, str):
                continue
            try:
                index = int(event.get("stream_index", 0))
            except (TypeError, ValueError):
                continue
            if index < 0:
                continue
            try:
                decoded = base64.b64decode(chunk, validate=True)
            except (binascii.Error, ValueError):
                continue
            streams.setdefault(index, bytearray()).extend(decoded)
        elif event_type == "complete":
            completed = True
        elif event_type == "error":
            message = event.get("message") or event.get("code") or "stream error"
            raise SoniloError(f"Sonilo 生成失败: {message}")
        # title / stage_start 等进度事件一律忽略。

    if not completed:
        raise SoniloError("Sonilo 事件流意外终止（未收到 complete 事件）")
    if not streams:
        raise SoniloError("Sonilo 事件流已完成但未返回音频数据")
    first_index = sorted(streams)[0]
    return bytes(streams[first_index])

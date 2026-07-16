"""
Sonilo (https://sonilo.com) AI 配乐（BGM）与 AI 音效（SFX）集成 ——
均为可选功能，默认关闭。

配乐（BGM）：将合成完成的视频（未加 BGM）上传到 Sonilo API
（`POST /v1/video-to-music`），根据画面内容与剪辑节奏生成一段背景音乐，
作为普通音频文件交还给现有的合成流程混音。生成的音乐已获授权、
可商用（以条款为准）。

音效（SFX）：将合成完成的视频上传到 Sonilo API
（`POST /v1/video-to-sfx`），根据画面内容生成贴合画面的音效。该接口是
异步任务：提交后返回 task_id，轮询 `GET /v1/tasks/{task_id}` 直到终态，
成功后从预签名 URL 下载音效音频，再用 ffmpeg 混在成片现有音轨之下
（解说配音在后续合成步骤中单独混入，音量策略不受影响）。生成的音效为
免版税素材。

设计约束（完全不影响现有合成逻辑）：
  * 默认关闭。配乐仅当用户在 WebUI 中把背景音乐来源切换为 Sonilo 时启用；
    音效仅当用户勾选 "AI 音效（Sonilo）" 时启用。两者都要求配置了
    Sonilo API Key（config.toml 的 `sonilo_api_key`，或环境变量
    `SONILO_API_KEY` 兜底）。
  * 配乐模块只负责生成音频文件；音量、淡出、循环与混音全部复用
    app/services/generate_video.py 中现有的音频处理逻辑，解说配音的
    音量压制策略保持不变。
  * 任何失败（超时、HTTP 错误、流中断、时长超限、混音失败）都只记录
    日志并返回空字符串，由调用方回退到现有逻辑，绝不中断成片任务。
  * 上传属于计费操作，上传前先用 ffprobe 在本地校验视频时长（配乐接口
    目前拒绝超过 6 分钟的视频，音效接口拒绝超过 3 分钟的视频），避免
    白传一次注定被拒绝的成片。

配乐接口返回 NDJSON 事件流：`audio_chunk`（base64 音频分片，按
stream_index 分组）、`title`、`complete`（成功终止事件）与 `error`
（失败终止事件）。进度事件与无法解析的行一律忽略。生成的音频为 AAC
编码的 .m4a 文件。

音效接口为异步任务管线：`POST /v1/video-to-sfx` 受理后即计费并返回
`{"task_id": ...}`；`GET /v1/tasks/{task_id}` 返回
`{"status": "succeeded"/"failed"/..., "audio": {"url": ...}, "error": ...,
"refunded": ...}`。结果地址是预签名 URL，下载时绝不能携带 API Key。

配置（config.toml 的 [app] 段）：
    sonilo_api_key = "..."             # 必填，启用开关（配乐与音效共用）
    # sonilo_base_url = "https://api.sonilo.com"
    # sonilo_timeout_seconds = 600
    # sonilo_bgm_prompt = ""           # 可选：配乐风格提示
    # sonilo_sfx_prompt = ""           # 可选：音效风格提示
    # sonilo_sfx_volume = 0.6          # 音效混入原声之下的音量（0-2]
"""

import base64
import binascii
import json
import os
import subprocess
import time
from typing import Iterable, Optional

import requests
from loguru import logger

from app.config import config

DEFAULT_BASE_URL = "https://api.sonilo.com"
VIDEO_TO_MUSIC_PATH = "/v1/video-to-music"
VIDEO_TO_SFX_PATH = "/v1/video-to-sfx"
TASKS_PATH = "/v1/tasks"
# 后端生成接口的读超时约为 600 秒。生成一旦开始就会计费，客户端过早超时
# 只会浪费一次已经付费的请求，所以默认读超时与后端保持一致，并允许覆盖。
DEFAULT_TIMEOUT_SECONDS = 600
_CONNECT_TIMEOUT_SECONDS = 15
# 轮询任务状态是免费且幂等的 GET，单次请求用短读超时即可。
_POLL_READ_TIMEOUT_SECONDS = 30
_SFX_POLL_INTERVAL_SECONDS = 5.0
# 测试接缝：单测里替换为 no-op，避免真实等待。
_sleep = time.sleep
# 配乐接口目前拒绝超过 6 分钟的视频；上传前先在本地校验时长。
MAX_VIDEO_DURATION_SECONDS = 360
# 音效接口目前拒绝超过 3 分钟的视频。
MAX_SFX_VIDEO_DURATION_SECONDS = 180
# 音效混入原声之下的默认音量（解说配音在后续合成步骤中以 1.0 混入，
# 音效保持在其之下）。可通过 sonilo_sfx_volume 配置覆盖。
DEFAULT_SFX_VOLUME = 0.6


class SoniloError(Exception):
    """Sonilo 配乐生成失败。"""


def get_api_key() -> str:
    """返回配置的 Sonilo API Key（优先 config.toml，其次环境变量）。"""
    api_key = config.app.get("sonilo_api_key", "") or os.getenv("SONILO_API_KEY", "")
    return str(api_key).strip()


def is_enabled() -> bool:
    """仅当配置了 Sonilo API Key 时返回 True。"""
    return bool(get_api_key())


def _get_base_url() -> str:
    return str(config.app.get("sonilo_base_url", "") or DEFAULT_BASE_URL).rstrip("/")


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
    base_url = _get_base_url()
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


# ---------- AI 音效（SFX，可选功能，默认关闭） ----------


def apply_sfx(video_path: str, output_path: str) -> str:
    """
    为合成完成的视频生成 Sonilo 音效，并用 ffmpeg 混在现有音轨之下，
    输出新视频到 `output_path`（视频流直接复制，不重编码画面）。

    成功时返回输出视频路径，任何失败都返回空字符串，由调用方沿用
    原视频。本函数绝不抛出异常 —— 音效问题绝不能中断成片任务。
    """
    sfx_audio_path = os.path.splitext(output_path)[0] + ".m4a"
    if not generate_sfx(video_path, sfx_audio_path):
        return ""
    return _mix_sfx_under_original(video_path, sfx_audio_path, output_path)


def generate_sfx(video_path: str, save_path: str) -> str:
    """
    上传合成完成的视频到 Sonilo，生成音效音频并保存到 `save_path`（.m4a）。

    成功时返回音频文件路径，任何失败都返回空字符串。与 generate_bgm
    的约定一致：本函数绝不抛出异常。
    """
    if not is_enabled():
        logger.warning("Sonilo 音效已跳过: 未配置 API Key")
        return ""

    if not video_path or not os.path.isfile(video_path):
        logger.warning(f"Sonilo 音效已跳过: 视频文件不存在: {video_path}")
        return ""

    # 任务受理即计费，先在本地校验时长，避免白传一次注定被拒绝的成片。
    duration = _probe_video_duration(video_path)
    if duration and duration > MAX_SFX_VIDEO_DURATION_SECONDS:
        logger.warning(
            f"Sonilo 音效已跳过: 视频时长 {duration:.1f}s 超过接口上限 "
            f"{MAX_SFX_VIDEO_DURATION_SECONDS}s"
        )
        return ""

    try:
        audio = _request_video_to_sfx(video_path)
    except Exception as e:
        logger.error(f"Sonilo 音效生成失败: {str(e)}")
        return ""

    try:
        with open(save_path, "wb") as f:
            f.write(audio)
    except OSError as e:
        logger.error(f"Sonilo 音效文件保存失败: {str(e)}")
        return ""

    logger.success(f"Sonilo 音效已生成: {save_path}")
    return save_path


def _request_video_to_sfx(video_path: str) -> bytes:
    """提交音效任务、轮询到终态、下载结果音频。失败抛出 SoniloError。"""
    task_id = _submit_sfx_task(video_path)
    body = _poll_sfx_task(task_id)
    return _download_sfx_audio(_extract_sfx_audio_url(body, task_id))


def _submit_sfx_task(video_path: str) -> str:
    """POST /v1/video-to-sfx，受理后返回 task_id（受理即计费，不做重试）。"""
    timeout_seconds = _get_timeout_seconds()
    prompt = str(config.app.get("sonilo_sfx_prompt", "") or "").strip()
    data: Optional[dict] = {"prompt": prompt} if prompt else None
    headers = {"Authorization": f"Bearer {get_api_key()}"}

    logger.info(f"正在提交 Sonilo 音效任务, 视频: {video_path}")

    try:
        with open(video_path, "rb") as video_file:
            files = {
                "video": (os.path.basename(video_path), video_file, "video/mp4"),
            }
            response = requests.post(
                f"{_get_base_url()}{VIDEO_TO_SFX_PATH}",
                headers=headers,
                data=data,
                files=files,
                timeout=(_CONNECT_TIMEOUT_SECONDS, timeout_seconds),
            )
    except requests.exceptions.Timeout as exc:
        raise SoniloError(
            f"Sonilo 音效任务提交超时 ({timeout_seconds:.0f}s)"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise SoniloError(f"Sonilo 音效任务提交失败: {str(exc)}") from exc

    if response.status_code >= 400:
        body = response.content.decode("utf-8", errors="replace")
        raise SoniloError(_http_error_message(response.status_code, body))

    try:
        task_id = response.json().get("task_id")
    except (ValueError, AttributeError):
        task_id = None
    if not task_id:
        raise SoniloError("Sonilo 音效任务已受理但未返回 task_id")
    task_id = str(task_id)
    # 受理即计费；先把 task_id 落进日志，后续轮询失败时仍有据可查。
    logger.info(f"Sonilo 音效任务已提交: {task_id}")
    return task_id


def _poll_sfx_task(task_id: str) -> dict:
    """
    轮询 GET /v1/tasks/{task_id} 直到任务终态（succeeded/failed）或超时。

    succeeded 时返回任务体；failed / 超时 / 不可恢复的 HTTP 错误抛出
    SoniloError。轮询是免费且幂等的 GET，网络抖动与 5xx 不该报废一次
    已计费的任务，在截止时间内继续重试。
    """
    headers = {"Authorization": f"Bearer {get_api_key()}"}
    timeout_seconds = _get_timeout_seconds()
    deadline = time.monotonic() + timeout_seconds

    while True:
        response = None
        try:
            response = requests.get(
                f"{_get_base_url()}{TASKS_PATH}/{task_id}",
                headers=headers,
                timeout=(_CONNECT_TIMEOUT_SECONDS, _POLL_READ_TIMEOUT_SECONDS),
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Sonilo 音效任务查询失败（将重试）: {str(exc)}")

        if response is not None:
            if response.status_code >= 500:
                logger.warning(
                    f"Sonilo 音效任务查询返回 {response.status_code}（将重试）"
                )
            elif response.status_code >= 400:
                body = response.content.decode("utf-8", errors="replace")
                raise SoniloError(
                    f"{_http_error_message(response.status_code, body)}"
                    f"（任务已提交, task_id: {task_id}）"
                )
            else:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if isinstance(body, dict):
                    status = body.get("status")
                    if status == "succeeded":
                        return body
                    if status == "failed":
                        raise SoniloError(_task_failure_message(body, task_id))
                # 非终态（pending / processing 等）继续等待。

        if time.monotonic() >= deadline:
            raise SoniloError(
                f"等待 Sonilo 音效任务超时 ({timeout_seconds:.0f}s), "
                f"task_id: {task_id}"
            )
        _sleep(_SFX_POLL_INTERVAL_SECONDS)


def _task_failure_message(body: dict, task_id: str) -> str:
    err = body.get("error")
    if isinstance(err, dict):
        message = err.get("message") or err.get("code") or "生成失败"
    elif isinstance(err, str) and err:
        message = err
    else:
        message = "生成失败"
    refund_note = "，费用已退还" if body.get("refunded") is True else ""
    return f"Sonilo 音效生成失败: {message}（task_id: {task_id}{refund_note}）"


def _extract_sfx_audio_url(body: dict, task_id: str) -> str:
    audio = body.get("audio")
    if isinstance(audio, dict):
        url = audio.get("url")
        if isinstance(url, str) and url:
            return url
    raise SoniloError(
        f"Sonilo 音效任务成功但未返回音频结果 (task_id: {task_id})"
    )


def _download_sfx_audio(url: str) -> bytes:
    """下载任务结果音频。结果地址是预签名 URL，自带鉴权 ——
    绝不能把 API Key 发给存储域名，因此这里不带任何鉴权头。"""
    try:
        response = requests.get(
            url, timeout=(_CONNECT_TIMEOUT_SECONDS, _get_timeout_seconds())
        )
    except requests.exceptions.RequestException as exc:
        raise SoniloError(f"Sonilo 音效结果下载失败: {str(exc)}") from exc
    if response.status_code >= 400:
        raise SoniloError(
            f"Sonilo 音效结果下载失败 (HTTP {response.status_code})"
        )
    if not response.content:
        raise SoniloError("Sonilo 音效结果为空")
    return response.content


def _get_sfx_volume() -> float:
    """音效混入原声之下的音量。非法值或 <=0 回退默认值，上限 2.0。"""
    try:
        volume = float(config.app.get("sonilo_sfx_volume", DEFAULT_SFX_VOLUME))
    except (TypeError, ValueError):
        return DEFAULT_SFX_VOLUME
    if volume <= 0:
        return DEFAULT_SFX_VOLUME
    return min(volume, 2.0)


def _get_ffmpeg_binary() -> str:
    """与 generate_video 保持一致的 ffmpeg 查找逻辑（环境变量优先）。"""
    for env_name in ("NARRATO_FFMPEG_EXE", "IMAGEIO_FFMPEG_EXE"):
        candidate = os.environ.get(env_name, "").strip()
        if candidate and os.path.isfile(candidate):
            return candidate
    try:
        import imageio_ffmpeg

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and os.path.isfile(candidate):
            return candidate
    except Exception:
        pass
    return "ffmpeg"


def _probe_has_audio_stream(video_path: str) -> bool:
    """尽力而为地探测视频是否带音轨。探测失败按无音轨处理。"""
    try:
        result = subprocess.run(
            [
                _get_ffprobe_binary(),
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-select_streams",
                "a",
                video_path,
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    try:
        return bool(json.loads(result.stdout).get("streams"))
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return False


def _mix_sfx_under_original(
    video_path: str, sfx_audio_path: str, output_path: str
) -> str:
    """
    用 ffmpeg 把音效混在成片现有音轨之下（音效音量默认 0.6，原声音量
    不变），视频流直接复制不重编码。成片没有音轨时，音效直接作为音轨
    写入。成功返回 output_path，任何失败返回空字符串。
    """
    volume = _get_sfx_volume()
    has_audio = _probe_has_audio_stream(video_path)
    if has_audio:
        filter_complex = (
            f"[1:a]volume={volume}[sfx];"
            "[0:a][sfx]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[aout]"
        )
    else:
        filter_complex = f"[1:a]volume={volume}[aout]"

    cmd = [
        _get_ffmpeg_binary(),
        "-y",
        "-i",
        video_path,
        "-i",
        sfx_audio_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
    ]
    if not has_audio:
        cmd.append("-shortest")
    cmd.append(output_path)

    logger.info(f"正在混入 Sonilo 音效 (音量 {volume}): {output_path}")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.error(f"Sonilo 音效混音失败: {str(e)}")
        return ""
    if result.returncode != 0:
        stderr_tail = (result.stderr or b"").decode("utf-8", errors="replace")[-500:]
        logger.error(f"Sonilo 音效混音失败 (ffmpeg 退出码 {result.returncode}): {stderr_tail}")
        return ""

    logger.success(f"Sonilo 音效已混入: {output_path}")
    return output_path

"""Fun-ASR subtitle transcription helpers.

The Bailian path intentionally uses the REST API because the official Fun-ASR
recorded-file API supports temporary `oss://` resources only through REST.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from loguru import logger

from app.utils import utils

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com"
UPLOAD_POLICY_URL = f"{DASHSCOPE_BASE_URL}/api/v1/uploads"
TRANSCRIPTION_URL = f"{DASHSCOPE_BASE_URL}/api/v1/services/audio/asr/transcription"
TASK_URL_TEMPLATE = f"{DASHSCOPE_BASE_URL}/api/v1/tasks/{{task_id}}"
MODEL_NAME = "fun-asr"
LOCAL_FUN_ASR_API_URL = "http://127.0.0.1:7860"
LOCAL_FIRERED_ASR_API_URL = "http://127.0.0.1:7867"
TERMINAL_FAILED_STATUSES = {"FAILED", "CANCELED", "UNKNOWN"}
PUNCTUATION_BREAKS = set("，。！？；,.!?;")


class FunAsrError(RuntimeError):
    """Raised for user-actionable Fun-ASR transcription failures."""


@dataclass
class UploadPolicy:
    upload_host: str
    upload_dir: str
    policy: str
    signature: str
    oss_access_key_id: str
    x_oss_object_acl: str = "private"
    x_oss_forbid_overwrite: str = "true"
    max_file_size_mb: Optional[float] = None


def _auth_headers(api_key: str, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _raise_for_http(response: requests.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except Exception as exc:  # requests may be mocked with generic exceptions
        raise FunAsrError(f"{action}失败，请检查阿里百炼 API Key、网络或服务状态") from exc


def _json(response: requests.Response, action: str) -> dict[str, Any]:
    _raise_for_http(response, action)
    try:
        data = response.json()
    except Exception as exc:
        raise FunAsrError(f"{action}返回了无效 JSON") from exc
    if not isinstance(data, dict):
        raise FunAsrError(f"{action}返回格式无效")
    return data


def _require_api_key(api_key: str) -> str:
    api_key = (api_key or "").strip()
    if not api_key:
        raise FunAsrError("请先输入阿里百炼 API Key")
    return api_key


def _safe_upload_name(local_file: str) -> str:
    name = os.path.basename(local_file).strip() or f"audio_{int(time.time())}.wav"
    return name.replace("/", "_").replace("\\", "_")


def _session_get(session, url: str, **kwargs):
    return session.get(url, **kwargs)


def _session_post(session, url: str, **kwargs):
    return session.post(url, **kwargs)


def _require_local_file(local_file: str) -> None:
    if not os.path.isfile(local_file):
        raise FunAsrError(f"待转写文件不存在: {local_file}")


def _normalize_local_api_url(api_url: str = "") -> str:
    api_url = (api_url or LOCAL_FUN_ASR_API_URL).strip().rstrip("/")
    if not api_url:
        raise FunAsrError("请先填写本地 FunASR-Pack API 地址")
    if "://" not in api_url:
        api_url = f"http://{api_url}"
    return api_url


def _local_base_url(api_url: str = "") -> str:
    api_url = _normalize_local_api_url(api_url)
    parsed = urlparse(api_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/asr"):
        path = path[:-4].rstrip("/")
    return urlunparse(parsed._replace(path=path, params="", query="", fragment="")).rstrip("/")


def _local_asr_url(api_url: str = "") -> str:
    api_url = _normalize_local_api_url(api_url)
    if urlparse(api_url).path.rstrip("/").endswith("/asr"):
        return api_url
    return f"{api_url}/asr"


def _absolute_local_download_url(api_url: str, download_url: str) -> str:
    download_url = (download_url or "").strip()
    if not download_url:
        return ""
    if urlparse(download_url).scheme:
        return download_url
    return urljoin(f"{_local_base_url(api_url)}/", download_url)


def _raise_for_local_http(
    response: requests.Response,
    action: str,
    service_name: str = "本地 FunASR-Pack 服务",
) -> None:
    status_code = getattr(response, "status_code", 200)
    if status_code and status_code >= 400:
        detail = ""
        try:
            data = response.json()
            if isinstance(data, dict):
                detail = str(data.get("detail") or "")
        except Exception:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise FunAsrError(f"{action}失败{suffix}，请确认{service_name}可用")

    try:
        response.raise_for_status()
    except Exception as exc:
        raise FunAsrError(f"{action}失败，请确认{service_name}可用") from exc


def _local_json(
    response: requests.Response,
    action: str,
    service_name: str = "本地 FunASR-Pack 服务",
) -> dict[str, Any]:
    _raise_for_local_http(response, action, service_name=service_name)
    try:
        data = response.json()
    except Exception as exc:
        raise FunAsrError(f"{action}返回了无效 JSON") from exc
    if not isinstance(data, dict):
        raise FunAsrError(f"{action}返回格式无效")
    return data


def _response_text(response: requests.Response) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return str(content)


def request_upload_policy(api_key: str, model: str = MODEL_NAME, session=requests) -> UploadPolicy:
    """Request Bailian temporary-storage upload policy for the target model."""
    api_key = _require_api_key(api_key)
    response = _session_get(
        session,
        UPLOAD_POLICY_URL,
        params={"action": "getPolicy", "model": model},
        headers=_auth_headers(api_key),
        timeout=30,
    )
    data = _json(response, "获取临时存储上传凭证")
    policy_data = data.get("data") or {}
    required = ["upload_host", "upload_dir", "policy", "signature", "oss_access_key_id"]
    missing = [field for field in required if not policy_data.get(field)]
    if missing:
        raise FunAsrError(f"临时存储上传凭证缺少字段: {', '.join(missing)}")

    return UploadPolicy(
        upload_host=str(policy_data["upload_host"]),
        upload_dir=str(policy_data["upload_dir"]).rstrip("/"),
        policy=str(policy_data["policy"]),
        signature=str(policy_data["signature"]),
        oss_access_key_id=str(policy_data["oss_access_key_id"]),
        x_oss_object_acl=str(policy_data.get("x_oss_object_acl") or "private"),
        x_oss_forbid_overwrite=str(policy_data.get("x_oss_forbid_overwrite") or "true"),
        max_file_size_mb=policy_data.get("max_file_size_mb"),
    )


def _validate_file_size(local_file: str, policy: UploadPolicy) -> None:
    if policy.max_file_size_mb is None:
        return
    max_bytes = float(policy.max_file_size_mb) * 1024 * 1024
    size = os.path.getsize(local_file)
    if size > max_bytes:
        raise FunAsrError(
            f"文件大小超过阿里百炼临时存储限制: {size / 1024 / 1024:.2f}MB > {float(policy.max_file_size_mb):.2f}MB"
        )


def upload_to_temporary_oss(local_file: str, policy: UploadPolicy, session=requests) -> str:
    """Upload local file to temporary OSS and return `oss://...` URL."""
    if not os.path.isfile(local_file):
        raise FunAsrError(f"待转写文件不存在: {local_file}")
    _validate_file_size(local_file, policy)

    key = f"{policy.upload_dir}/{_safe_upload_name(local_file)}"
    data = {
        "OSSAccessKeyId": policy.oss_access_key_id,
        "policy": policy.policy,
        "Signature": policy.signature,
        "key": key,
        "x-oss-object-acl": policy.x_oss_object_acl,
        "x-oss-forbid-overwrite": policy.x_oss_forbid_overwrite,
        "success_action_status": "200",
    }
    with open(local_file, "rb") as file_obj:
        files = {"file": (_safe_upload_name(local_file), file_obj)}
        response = _session_post(session, policy.upload_host, data=data, files=files, timeout=120)
    _raise_for_http(response, "上传文件到阿里百炼临时存储")
    return f"oss://{key}"


def submit_transcription_task(
    api_key: str,
    oss_url: str,
    speaker_count: Optional[int] = None,
    model: str = MODEL_NAME,
    session=requests,
) -> str:
    """Submit async Fun-ASR task and return task_id."""
    api_key = _require_api_key(api_key)
    parameters: dict[str, Any] = {"diarization_enabled": True}
    if speaker_count:
        parameters["speaker_count"] = int(speaker_count)

    payload = {
        "model": model,
        "input": {"file_urls": [oss_url]},
        "parameters": parameters,
    }
    response = _session_post(
        session,
        TRANSCRIPTION_URL,
        headers=_auth_headers(
            api_key,
            {
                "X-DashScope-Async": "enable",
                "X-DashScope-OssResourceResolve": "enable",
            },
        ),
        json=payload,
        timeout=30,
    )
    data = _json(response, "提交 Fun-ASR 转写任务")
    task_id = ((data.get("output") or {}).get("task_id") or "").strip()
    if not task_id:
        raise FunAsrError("提交 Fun-ASR 转写任务失败：未返回 task_id")
    return task_id


def poll_transcription_task(
    api_key: str,
    task_id: str,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
    session=requests,
) -> dict[str, Any]:
    """Poll task until terminal status and return successful result item."""
    api_key = _require_api_key(api_key)
    deadline = time.time() + timeout
    last_status = "PENDING"
    while time.time() < deadline:
        response = _session_post(
            session,
            TASK_URL_TEMPLATE.format(task_id=task_id),
            headers=_auth_headers(api_key),
            timeout=30,
        )
        data = _json(response, "查询 Fun-ASR 转写任务")
        output = data.get("output") or {}
        last_status = str(output.get("task_status") or "").upper()

        if last_status == "SUCCEEDED":
            results = output.get("results") or []
            for result in results:
                subtask_status = str(result.get("subtask_status") or "").upper()
                if subtask_status and subtask_status != "SUCCEEDED":
                    raise FunAsrError(f"Fun-ASR 子任务失败: {subtask_status}")
            if not results:
                raise FunAsrError("Fun-ASR 转写成功但未返回结果")
            return results[0]

        if last_status in TERMINAL_FAILED_STATUSES:
            raise FunAsrError(f"Fun-ASR 转写任务失败: {last_status}")

        time.sleep(poll_interval)

    raise FunAsrError(f"Fun-ASR 转写任务超时，最后状态: {last_status}")


def download_transcription_result(transcription_url: str, session=requests) -> dict[str, Any]:
    if not transcription_url:
        raise FunAsrError("Fun-ASR 结果缺少 transcription_url")
    response = _session_get(session, transcription_url, timeout=60)
    return _json(response, "下载 Fun-ASR 转写结果")


def _ms_to_srt_time(ms: float) -> str:
    total_ms = max(0, int(round(float(ms))))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    seconds = total_ms // 1_000
    milliseconds = total_ms % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _srt_block(index: int, start_ms: float, end_ms: float, text: str) -> str:
    if end_ms <= start_ms:
        end_ms = start_ms + 500
    return f"{index}\n{_ms_to_srt_time(start_ms)} --> {_ms_to_srt_time(end_ms)}\n{text.strip()}\n"


def _timestamp_ms(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FunAsrError(f"Fun-ASR 转写结果时间戳无效: {field_name}={value!r}") from exc


def _speaker_prefix(speaker_id: Any) -> str:
    if speaker_id is None or speaker_id == "":
        return ""
    try:
        label = int(speaker_id) + 1
    except (TypeError, ValueError):
        label = str(speaker_id)
    return f"说话人{label}: "


def _iter_sentences(result_json: dict[str, Any]):
    transcripts = result_json.get("transcripts")
    if transcripts is None and "sentences" in result_json:
        transcripts = [{"sentences": result_json.get("sentences") or []}]
    if not transcripts:
        raise FunAsrError("Fun-ASR 转写结果为空：未找到 transcripts")
    for transcript in transcripts:
        for sentence in transcript.get("sentences") or []:
            yield sentence


def _word_text(word: dict[str, Any]) -> str:
    text = str(word.get("text") or word.get("word") or "")
    punctuation = str(word.get("punctuation") or "")
    if punctuation and not text.endswith(punctuation):
        text += punctuation
    return text


def _flush_block(blocks: list[dict[str, Any]], current: dict[str, Any]) -> None:
    text = current.get("text", "").strip()
    if text:
        blocks.append(current.copy())


def _blocks_from_words(sentence: dict[str, Any], max_chars: int, max_duration: float) -> list[dict[str, Any]]:
    words = sentence.get("words") or []
    blocks: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    max_duration_ms = max_duration * 1000
    sentence_speaker = sentence.get("speaker_id")

    for word in words:
        text = _word_text(word)
        if not text:
            continue
        start = word.get("begin_time", word.get("start_time"))
        end = word.get("end_time")
        if start is None or end is None:
            continue
        speaker_id = word.get("speaker_id", sentence_speaker)
        start_ms = _timestamp_ms(start, "word.begin_time")
        end_ms = _timestamp_ms(end, "word.end_time")

        if current is None:
            current = {"start": start_ms, "end": end_ms, "text": text, "speaker_id": speaker_id}
        else:
            should_split_before = (
                speaker_id != current.get("speaker_id")
                or len(current["text"] + text) > max_chars
                or (end_ms - current["start"]) > max_duration_ms
            )
            if should_split_before:
                _flush_block(blocks, current)
                current = {"start": start_ms, "end": end_ms, "text": text, "speaker_id": speaker_id}
            else:
                current["text"] += text
                current["end"] = end_ms

        if current and text[-1:] in PUNCTUATION_BREAKS:
            _flush_block(blocks, current)
            current = None

    if current:
        _flush_block(blocks, current)
    return blocks


def _split_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in PUNCTUATION_BREAKS or len(current) >= max_chars:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def _blocks_from_sentence(sentence: dict[str, Any], max_chars: int) -> list[dict[str, Any]]:
    text = str(sentence.get("text") or "").strip()
    if not text:
        return []
    start = sentence.get("begin_time", 0)
    end = sentence.get("end_time")
    start_ms = _timestamp_ms(start, "sentence.begin_time")
    end_ms = _timestamp_ms(end, "sentence.end_time") if end is not None else start_ms + 500
    chunks = _split_text(text, max_chars)
    if not chunks:
        return []
    duration = max(500.0, end_ms - start_ms)
    total_chars = max(1, sum(len(chunk) for chunk in chunks))
    cursor = start_ms
    blocks: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            chunk_end = end_ms
        else:
            chunk_end = cursor + duration * (len(chunk) / total_chars)
        blocks.append(
            {
                "start": cursor,
                "end": max(cursor + 200, chunk_end),
                "text": chunk,
                "speaker_id": sentence.get("speaker_id"),
            }
        )
        cursor = chunk_end
    return blocks


def fun_asr_result_to_srt(result_json: dict[str, Any], max_chars: int = 20, max_duration: float = 3.5) -> str:
    """Convert downloaded Fun-ASR JSON into fine-grained SRT.

    Official downloaded schema is `transcripts[*].sentences[*].words[*]`.
    Fun-ASR timestamps are milliseconds.
    """
    blocks: list[dict[str, Any]] = []
    for sentence in _iter_sentences(result_json):
        sentence_blocks = _blocks_from_words(sentence, max_chars, max_duration)
        if not sentence_blocks:
            sentence_blocks = _blocks_from_sentence(sentence, max_chars)
        blocks.extend(sentence_blocks)

    if not blocks:
        raise FunAsrError("Fun-ASR 转写结果为空：未找到可用字幕内容")

    lines = []
    for index, block in enumerate(blocks, start=1):
        text = f"{_speaker_prefix(block.get('speaker_id'))}{block['text']}"
        lines.append(_srt_block(index, block["start"], block["end"], text))
    return "\n".join(lines).rstrip() + "\n"


def write_srt_file(srt_content: str, subtitle_file: str = "") -> str:
    if not subtitle_file:
        subtitle_file = os.path.join(utils.subtitle_dir(), f"fun_asr_{int(time.time())}.srt")
    parent = os.path.dirname(subtitle_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return subtitle_file


def copy_srt_file(source_file: str, subtitle_file: str = "") -> str:
    """Copy an existing SRT file into NarratoAI's subtitle directory."""
    if not os.path.isfile(source_file):
        raise FunAsrError(f"本地 FunASR-Pack 返回的字幕文件不存在: {source_file}")
    if not subtitle_file:
        subtitle_file = os.path.join(utils.subtitle_dir(), f"fun_asr_local_{int(time.time())}.srt")
    parent = os.path.dirname(subtitle_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.abspath(source_file) != os.path.abspath(subtitle_file):
        shutil.copyfile(source_file, subtitle_file)
    return subtitle_file


def request_local_fun_asr_health(api_url: str = LOCAL_FUN_ASR_API_URL, session=requests) -> dict[str, Any]:
    """Fetch FunASR-Pack health metadata from the local service."""
    response = _session_get(session, f"{_local_base_url(api_url)}/health", timeout=10)
    return _local_json(response, "检查本地 FunASR-Pack 服务")


def request_local_firered_asr_health(
    api_url: str = LOCAL_FIRERED_ASR_API_URL,
    session=requests,
) -> dict[str, Any]:
    """Fetch FireRedASR2-AED-Pack health metadata from the local service."""
    response = _session_get(session, f"{_local_base_url(api_url)}/health", timeout=10)
    return _local_json(
        response,
        "检查本地 FireRedASR2-AED-Pack 服务",
        service_name="本地 FireRedASR2-AED-Pack 服务",
    )


def request_local_fun_asr(
    local_file: str,
    api_url: str = LOCAL_FUN_ASR_API_URL,
    hotword: str = "",
    enable_spk: Optional[bool] = None,
    timeout: float = 600.0,
    session=requests,
) -> dict[str, Any]:
    """Call the local FunASR-Pack `/asr` API and return its JSON result."""
    _require_local_file(local_file)
    data: dict[str, str] = {}
    if hotword.strip():
        data["hotword"] = hotword.strip()
    if enable_spk is not None:
        data["enable_spk"] = "true" if enable_spk else "false"

    with open(local_file, "rb") as file_obj:
        files = {"file": (_safe_upload_name(local_file), file_obj)}
        response = _session_post(
            session,
            _local_asr_url(api_url),
            data=data,
            files=files,
            timeout=timeout,
        )
    return _local_json(response, "调用本地 FunASR-Pack ASR API")


def request_local_firered_asr(
    local_file: str,
    api_url: str = LOCAL_FIRERED_ASR_API_URL,
    enable_vad: Optional[bool] = True,
    enable_lid: Optional[bool] = True,
    enable_punc: Optional[bool] = True,
    return_timestamp: Optional[bool] = True,
    timeout: float = 600.0,
    session=requests,
) -> dict[str, Any]:
    """Call the local FireRedASR2-AED-Pack `/asr` API and return its JSON result."""
    _require_local_file(local_file)
    data: dict[str, str] = {}
    options = {
        "enable_vad": enable_vad,
        "enable_lid": enable_lid,
        "enable_punc": enable_punc,
        "return_timestamp": return_timestamp,
    }
    for key, value in options.items():
        if value is not None:
            data[key] = "true" if value else "false"

    with open(local_file, "rb") as file_obj:
        files = {"file": (_safe_upload_name(local_file), file_obj)}
        response = _session_post(
            session,
            _local_asr_url(api_url),
            data=data,
            files=files,
            timeout=timeout,
        )
    return _local_json(
        response,
        "调用本地 FireRedASR2-AED-Pack ASR API",
        service_name="本地 FireRedASR2-AED-Pack 服务",
    )


def download_local_srt(
    download_url: str,
    api_url: str = LOCAL_FUN_ASR_API_URL,
    subtitle_file: str = "",
    session=requests,
    service_name: str = "本地 FunASR-Pack 服务",
) -> str:
    """Download an SRT exposed by FunASR-Pack and save it as a NarratoAI subtitle."""
    absolute_url = _absolute_local_download_url(api_url, download_url)
    if not absolute_url:
        raise FunAsrError("本地 FunASR-Pack 结果缺少 SRT 下载地址")
    response = _session_get(session, absolute_url, timeout=60)
    _raise_for_local_http(response, "下载本地 SRT", service_name=service_name)
    srt_content = _response_text(response)
    if not srt_content.strip():
        raise FunAsrError(f"{service_name}返回了空 SRT")
    return write_srt_file(srt_content, subtitle_file)


def _local_result_items(result_json: dict[str, Any]):
    raw = result_json.get("raw")
    if isinstance(raw, dict):
        yield raw
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield item
    elif result_json.get("text"):
        yield result_json


def _blocks_from_local_timestamp(item: dict[str, Any], max_chars: int, max_duration: float) -> list[dict[str, Any]]:
    text = str(item.get("text") or "").strip()
    timestamps = item.get("timestamp") or []
    if not text or not isinstance(timestamps, list):
        return []

    non_space_chars = [char for char in text if char.strip()]
    consume_punctuation = len(timestamps) >= len(non_space_chars)
    blocks: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    timestamp_index = 0
    last_end = 0.0
    max_duration_ms = max_duration * 1000

    for char in text:
        if not char.strip():
            continue

        is_punctuation = char in PUNCTUATION_BREAKS
        consume_timestamp = consume_punctuation or not is_punctuation
        if consume_timestamp and timestamp_index < len(timestamps):
            pair = timestamps[timestamp_index]
            timestamp_index += 1
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            start_ms = _timestamp_ms(pair[0], "local.timestamp.start")
            end_ms = _timestamp_ms(pair[1], "local.timestamp.end")
            last_end = end_ms
        else:
            start_ms = last_end
            end_ms = last_end if is_punctuation else last_end + 200
            last_end = end_ms

        if current is None:
            current = {"start": start_ms, "end": end_ms, "text": char}
        else:
            should_split_before = (
                len(current["text"] + char) > max_chars
                or (end_ms - current["start"]) > max_duration_ms
            )
            if should_split_before:
                _flush_block(blocks, current)
                current = {"start": start_ms, "end": end_ms, "text": char}
            else:
                current["text"] += char
                current["end"] = end_ms

        if current and is_punctuation:
            _flush_block(blocks, current)
            current = None

    if current:
        _flush_block(blocks, current)
    return blocks


def local_fun_asr_result_to_srt(
    result_json: dict[str, Any],
    max_chars: int = 20,
    max_duration: float = 3.5,
) -> str:
    """Convert a FunASR-Pack JSON response into SRT when the API SRT is unavailable."""
    blocks: list[dict[str, Any]] = []
    for item in _local_result_items(result_json):
        item_blocks = _blocks_from_local_timestamp(item, max_chars, max_duration)
        if not item_blocks:
            text = str(item.get("text") or "").strip()
            if text:
                item_blocks = _blocks_from_sentence(
                    {
                        "begin_time": 0,
                        "end_time": max(1500, len(text) * 180),
                        "text": text,
                    },
                    max_chars=max_chars,
                )
        blocks.extend(item_blocks)

    if not blocks:
        raise FunAsrError("本地 FunASR-Pack 转写结果为空：未找到可用字幕内容")

    lines = []
    for index, block in enumerate(blocks, start=1):
        lines.append(_srt_block(index, block["start"], block["end"], block["text"]))
    return "\n".join(lines).rstrip() + "\n"


def firered_asr_result_to_srt(result_json: dict[str, Any]) -> str:
    """Convert a FireRedASR2-AED-Pack JSON response into SRT when no SRT URL is returned."""
    blocks: list[dict[str, Any]] = []
    sentences = result_json.get("sentences")
    if isinstance(sentences, list):
        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue
            text = str(sentence.get("text") or "").strip()
            if not text:
                continue
            start = sentence.get("start_ms", sentence.get("begin_time", sentence.get("start_time", 0)))
            end = sentence.get("end_ms", sentence.get("end_time"))
            start_ms = _timestamp_ms(start, "firered.sentence.start_ms")
            end_ms = _timestamp_ms(end, "firered.sentence.end_ms") if end is not None else start_ms + 500
            blocks.append({"start": start_ms, "end": end_ms, "text": text})

    if not blocks:
        return local_fun_asr_result_to_srt(result_json)

    lines = []
    for index, block in enumerate(blocks, start=1):
        lines.append(_srt_block(index, block["start"], block["end"], block["text"]))
    return "\n".join(lines).rstrip() + "\n"


def _get_local_srt_download_url(result_json: dict[str, Any]) -> str:
    downloads = result_json.get("downloads") or {}
    if isinstance(downloads, dict):
        download_url = downloads.get("srt")
        if download_url:
            return str(download_url)
    for key in ("srt_url", "srt_download_url", "download_url"):
        download_url = result_json.get(key)
        if download_url:
            return str(download_url)
    return ""


def create_with_local_fun_asr(
    local_file: str,
    subtitle_file: str = "",
    api_url: str = LOCAL_FUN_ASR_API_URL,
    hotword: str = "",
    enable_spk: Optional[bool] = None,
    timeout: float = 600.0,
    session=requests,
) -> Optional[str]:
    """Create an SRT file through a locally running FunASR-Pack API."""
    try:
        result_json = request_local_fun_asr(
            local_file=local_file,
            api_url=api_url,
            hotword=hotword,
            enable_spk=enable_spk,
            timeout=timeout,
            session=session,
        )

        srt_file = result_json.get("srt_file")
        if isinstance(srt_file, str) and srt_file and os.path.isfile(srt_file):
            output_file = copy_srt_file(srt_file, subtitle_file)
        else:
            download_url = _get_local_srt_download_url(result_json)
            if download_url:
                output_file = download_local_srt(
                    download_url,
                    api_url=api_url,
                    subtitle_file=subtitle_file,
                    session=session,
                )
            else:
                srt_content = local_fun_asr_result_to_srt(result_json)
                output_file = write_srt_file(srt_content, subtitle_file)

        logger.info(f"本地 FunASR-Pack 字幕文件已生成: {output_file}")
        return output_file
    except FunAsrError:
        raise
    except Exception as exc:
        raise FunAsrError("本地 FunASR-Pack 字幕转写失败，请检查服务地址、文件或模型状态") from exc


def create_with_local_firered_asr(
    local_file: str,
    subtitle_file: str = "",
    api_url: str = LOCAL_FIRERED_ASR_API_URL,
    enable_vad: Optional[bool] = True,
    enable_lid: Optional[bool] = True,
    enable_punc: Optional[bool] = True,
    return_timestamp: Optional[bool] = True,
    timeout: float = 600.0,
    session=requests,
) -> Optional[str]:
    """Create an SRT file through a locally running FireRedASR2-AED-Pack API."""
    service_name = "本地 FireRedASR2-AED-Pack 服务"
    try:
        result_json = request_local_firered_asr(
            local_file=local_file,
            api_url=api_url,
            enable_vad=enable_vad,
            enable_lid=enable_lid,
            enable_punc=enable_punc,
            return_timestamp=return_timestamp,
            timeout=timeout,
            session=session,
        )

        srt_file = result_json.get("srt_file")
        if isinstance(srt_file, str) and srt_file and os.path.isfile(srt_file):
            output_file = copy_srt_file(srt_file, subtitle_file)
        else:
            download_url = _get_local_srt_download_url(result_json)
            if download_url:
                output_file = download_local_srt(
                    download_url,
                    api_url=api_url,
                    subtitle_file=subtitle_file,
                    session=session,
                    service_name=service_name,
                )
            else:
                srt_content = firered_asr_result_to_srt(result_json)
                output_file = write_srt_file(srt_content, subtitle_file)

        logger.info(f"本地 FireRedASR2-AED-Pack 字幕文件已生成: {output_file}")
        return output_file
    except FunAsrError:
        raise
    except Exception as exc:
        raise FunAsrError("本地ASR字幕转写失败，请检查 FireRedASR2-AED-Pack 服务地址、文件或模型状态") from exc


def create_with_fun_asr(
    local_file: str,
    subtitle_file: str = "",
    api_key: str = "",
    speaker_count: Optional[int] = None,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
    session=requests,
) -> Optional[str]:
    """Upload local media to Bailian temporary storage and create a Fun-ASR SRT file."""
    api_key = _require_api_key(api_key)
    try:
        policy = request_upload_policy(api_key, session=session)
        oss_url = upload_to_temporary_oss(local_file, policy, session=session)
        task_id = submit_transcription_task(api_key, oss_url, speaker_count=speaker_count, session=session)
        task_result = poll_transcription_task(
            api_key,
            task_id,
            poll_interval=poll_interval,
            timeout=timeout,
            session=session,
        )
        transcription_url = task_result.get("transcription_url")
        result_json = download_transcription_result(transcription_url, session=session)
        srt_content = fun_asr_result_to_srt(result_json)
        output_file = write_srt_file(srt_content, subtitle_file)
        logger.info(f"Fun-ASR 字幕文件已生成: {output_file}")
        return output_file
    except FunAsrError:
        raise
    except Exception as exc:
        raise FunAsrError("Fun-ASR 字幕转写失败，请检查文件、网络或阿里百炼服务状态") from exc

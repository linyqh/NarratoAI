import os
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from app.services.short_drama_narration_validation import build_subtitle_index
from app.services.subtitle_text import read_subtitle_text
from app.utils import utils


DEFAULT_SUBTITLE_OST_TYPES = (0, 2)
DEFAULT_ORIGINAL_SUBTITLE_OST_TYPES = (1,)
DEFAULT_MAX_CHARS_PER_SUBTITLE = 12
SENTENCE_PART_RE = re.compile(r"[^。！？!?；;，,、\n]+[。！？!?；;，,、]?")
SubtitleEntry = Tuple[float, float, str]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _remove_punctuation(text: str) -> str:
    return "".join(
        char for char in str(text or "")
        if not unicodedata.category(char).startswith("P")
    )


def clean_subtitle_text(text: str) -> str:
    """Normalize subtitle text for burn-in display."""
    return _normalize_text(_remove_punctuation(text))


def split_narration(text: str, max_chars: int = DEFAULT_MAX_CHARS_PER_SUBTITLE) -> List[str]:
    """Split narration into readable subtitle chunks."""
    text = _normalize_text(text)
    if not text:
        return []

    max_chars = max(1, int(max_chars or DEFAULT_MAX_CHARS_PER_SUBTITLE))
    parts = [match.group(0).strip() for match in SENTENCE_PART_RE.finditer(text)]
    if not parts:
        parts = [text]

    chunks = []
    current = ""

    def flush_long_part(part: str) -> str:
        while len(part) > max_chars:
            chunks.append(part[:max_chars].strip())
            part = part[max_chars:].strip()
        return part

    for part in parts:
        if not part:
            continue

        if len(part) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            current = flush_long_part(part)
            continue

        candidate = f"{current}{part}" if current else part
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = part

    if current:
        chunks.append(current.strip())

    return [cleaned for chunk in chunks if (cleaned := clean_subtitle_text(chunk))]


def parse_srt_like_time(time_text: str) -> float:
    time_text = str(time_text or "").strip().replace(",", ".")
    parts = time_text.split(":")
    if len(parts) != 3:
        raise ValueError(f"不支持的时间格式: {time_text}")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def parse_time_range(time_range: str) -> Tuple[float, float]:
    if not time_range or "-" not in str(time_range):
        raise ValueError(f"不支持的时间范围: {time_range}")

    start_text, end_text = str(time_range).split("-", 1)
    start = parse_srt_like_time(start_text)
    end = parse_srt_like_time(end_text)
    if end <= start:
        raise ValueError(f"结束时间必须晚于开始时间: {time_range}")

    return start, end


def format_srt_time(seconds: float) -> str:
    milliseconds_total = max(0, int(round(float(seconds) * 1000)))
    milliseconds = milliseconds_total % 1000
    total_seconds = milliseconds_total // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def _safe_ost_value(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_positive_int(value) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalize_paths(paths) -> List[str]:
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return []

    normalized_paths = []
    seen = set()
    for item in paths:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item or item in seen:
            continue
        normalized_paths.append(item)
        seen.add(item)
    return normalized_paths


def _resolve_script_video_id(item: dict, video_origin_paths: Sequence[str]) -> int:
    video_id = _coerce_positive_int(item.get("video_id") or item.get("video_index"))
    if video_id is not None:
        return video_id

    video_name = os.path.basename(
        str(item.get("video_name") or item.get("source_video") or "").strip()
    )
    if video_name:
        for index, video_path in enumerate(video_origin_paths, start=1):
            if os.path.basename(video_path) == video_name:
                return index

    return 1


def _read_subtitle_file(subtitle_path: str) -> str:
    try:
        return read_subtitle_text(subtitle_path).text
    except Exception as e:
        logger.warning(f"读取原片字幕失败: {subtitle_path}, {e}")
        return ""


def _build_combined_original_subtitle_content(
    original_subtitle_paths,
    video_origin_paths=None,
) -> str:
    subtitle_paths = _normalize_paths(original_subtitle_paths)
    video_paths = _normalize_paths(video_origin_paths)
    sections = []

    for index, subtitle_path in enumerate(subtitle_paths, start=1):
        if not os.path.exists(subtitle_path):
            logger.warning(f"原片字幕文件不存在，跳过: {subtitle_path}")
            continue

        content = _read_subtitle_file(subtitle_path)
        if not content:
            logger.warning(f"原片字幕文件为空，跳过: {subtitle_path}")
            continue

        video_path = video_paths[index - 1] if index <= len(video_paths) else ""
        if video_path:
            header = (
                f"# 视频 {index}: {os.path.basename(video_path)}\n"
                f"字幕文件: {os.path.basename(subtitle_path)}"
            )
        else:
            header = f"# 视频 {index}\n字幕文件: {os.path.basename(subtitle_path)}"
        sections.append(f"{header}\n{content}".strip())

    return "\n\n".join(sections)


def _resolve_item_time_range(item: dict, current_time: float) -> Tuple[Optional[Tuple[float, float]], float]:
    duration = float(item.get("duration", 0.0) or 0.0)
    if duration > 0:
        start = current_time
        end = current_time + duration
        return (start, end), end

    edited_time_range = item.get("editedTimeRange")
    if edited_time_range:
        try:
            start, end = parse_time_range(edited_time_range)
            return (start, end), end
        except ValueError as e:
            logger.warning(f"解析 editedTimeRange 失败，将尝试使用 duration: {e}")

    return None, current_time


def _build_narration_subtitle_entries(
    list_script: Sequence[dict],
    include_ost: Iterable[int],
    max_chars: int,
) -> List[SubtitleEntry]:
    include_ost_set = {int(item) for item in include_ost}
    entries: List[SubtitleEntry] = []
    current_time = 0.0

    for item in list_script:
        time_range, current_time = _resolve_item_time_range(item, current_time)
        if not time_range:
            continue

        ost = _safe_ost_value(item.get("OST"))
        if ost not in include_ost_set:
            continue

        chunks = split_narration(item.get("narration", ""), max_chars=max_chars)
        if not chunks:
            continue

        start, end = time_range
        segment_duration = end - start
        if segment_duration <= 0:
            continue

        chunk_duration = segment_duration / len(chunks)
        for chunk_index, chunk in enumerate(chunks):
            chunk_start = start + chunk_duration * chunk_index
            chunk_end = end if chunk_index == len(chunks) - 1 else start + chunk_duration * (chunk_index + 1)
            entries.append((chunk_start, chunk_end, chunk))

    return entries


def _build_original_subtitle_entries(
    list_script: Sequence[dict],
    original_subtitle_paths=None,
    video_origin_paths=None,
    include_ost: Iterable[int] = DEFAULT_ORIGINAL_SUBTITLE_OST_TYPES,
) -> List[SubtitleEntry]:
    original_subtitle_content = _build_combined_original_subtitle_content(
        original_subtitle_paths,
        video_origin_paths,
    )
    if not original_subtitle_content:
        return []

    video_paths = _normalize_paths(video_origin_paths)
    subtitle_index = build_subtitle_index(original_subtitle_content, video_paths)
    if not subtitle_index:
        logger.warning("原片字幕索引为空，无法为原声片段生成字幕")
        return []

    cues_by_video = {}
    for cue in subtitle_index:
        cues_by_video.setdefault(cue.video_id, []).append(cue)

    include_ost_set = {int(item) for item in include_ost}
    entries: List[SubtitleEntry] = []
    current_time = 0.0

    for item in list_script:
        time_range, current_time = _resolve_item_time_range(item, current_time)
        if not time_range:
            continue

        ost = _safe_ost_value(item.get("OST"))
        if ost not in include_ost_set:
            continue

        source_time_range = item.get("sourceTimeRange") or item.get("timestamp")
        try:
            source_start, source_end = parse_time_range(source_time_range)
        except ValueError as e:
            logger.warning(f"解析原声片段源时间失败，跳过原片字幕: {e}")
            continue

        target_start, target_end = time_range
        source_duration = source_end - source_start
        target_duration = target_end - target_start
        if source_duration <= 0 or target_duration <= 0:
            continue

        video_id = _resolve_script_video_id(item, video_paths)
        video_cues = cues_by_video.get(video_id, [])
        if not video_cues:
            logger.warning(f"视频 {video_id} 未找到可用原片字幕，片段 {item.get('_id')} 跳过")
            continue

        for cue in video_cues:
            cue_start = cue.start_ms / 1000
            cue_end = cue.end_ms / 1000
            overlap_start = max(source_start, cue_start)
            overlap_end = min(source_end, cue_end)
            if overlap_end <= overlap_start:
                continue

            text = clean_subtitle_text(cue.text)
            if not text:
                continue

            mapped_start = target_start + (overlap_start - source_start)
            mapped_end = target_start + (overlap_end - source_start)
            mapped_start = max(target_start, min(mapped_start, target_end))
            mapped_end = max(target_start, min(mapped_end, target_end))
            if mapped_end <= mapped_start:
                continue

            entries.append((mapped_start, mapped_end, text))

    return entries


def _subtitle_entries_to_blocks(entries: Sequence[SubtitleEntry]) -> List[str]:
    blocks = []
    sorted_entries = sorted(
        entries,
        key=lambda entry: (entry[0], entry[1], entry[2]),
    )

    for subtitle_index, (start, end, text) in enumerate(sorted_entries, start=1):
        blocks.append(
            "\n".join(
                [
                    str(subtitle_index),
                    f"{format_srt_time(start)} --> {format_srt_time(end)}",
                    text,
                ]
            )
        )

    return blocks


def _build_srt_blocks(
    list_script: Sequence[dict],
    include_ost: Iterable[int],
    max_chars: int,
) -> List[str]:
    entries = _build_narration_subtitle_entries(
        list_script,
        include_ost=include_ost,
        max_chars=max_chars,
    )
    return _subtitle_entries_to_blocks(entries)


def create_script_subtitle_file(
    task_id: str,
    list_script: Sequence[dict],
    output_file: Optional[str] = None,
    include_ost: Optional[Iterable[int]] = None,
    max_chars: int = DEFAULT_MAX_CHARS_PER_SUBTITLE,
    original_subtitle_paths=None,
    video_origin_paths=None,
    include_original_ost: Optional[Iterable[int]] = None,
) -> str:
    """Create a full SRT file from script narration plus original-audio subtitles."""
    if not list_script:
        return ""

    if include_ost is None:
        include_ost = DEFAULT_SUBTITLE_OST_TYPES
    if include_original_ost is None:
        include_original_ost = DEFAULT_ORIGINAL_SUBTITLE_OST_TYPES

    entries = _build_narration_subtitle_entries(
        list_script,
        include_ost=include_ost,
        max_chars=max_chars,
    )
    entries.extend(
        _build_original_subtitle_entries(
            list_script,
            original_subtitle_paths=original_subtitle_paths,
            video_origin_paths=video_origin_paths,
            include_ost=include_original_ost,
        )
    )

    blocks = _subtitle_entries_to_blocks(entries)
    if not blocks:
        logger.warning("程序化字幕未生成内容")
        return ""

    if output_file is None:
        output_file = os.path.join(utils.task_dir(task_id), "script_subtitles.srt")

    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks))
        f.write("\n")

    logger.info(f"程序化字幕生成成功: {output_file}, 共 {len(blocks)} 条")
    return output_file

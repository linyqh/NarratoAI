import os
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple

from loguru import logger

from app.utils import utils


DEFAULT_SUBTITLE_OST_TYPES = (0, 2)
DEFAULT_MAX_CHARS_PER_SUBTITLE = 12
SENTENCE_PART_RE = re.compile(r"[^。！？!?；;，,、\n]+[。！？!?；;，,、]?")


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


def _resolve_item_time_range(item: dict, current_time: float) -> Tuple[Optional[Tuple[float, float]], float]:
    edited_time_range = item.get("editedTimeRange")
    if edited_time_range:
        try:
            start, end = parse_time_range(edited_time_range)
            return (start, end), end
        except ValueError as e:
            logger.warning(f"解析 editedTimeRange 失败，将尝试使用 duration: {e}")

    duration = float(item.get("duration", 0.0) or 0.0)
    if duration <= 0:
        return None, current_time

    start = current_time
    end = current_time + duration
    return (start, end), end


def _build_srt_blocks(
    list_script: Sequence[dict],
    include_ost: Iterable[int],
    max_chars: int,
) -> List[str]:
    include_ost_set = {int(item) for item in include_ost}
    blocks = []
    subtitle_index = 1
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
            blocks.append(
                "\n".join(
                    [
                        str(subtitle_index),
                        f"{format_srt_time(chunk_start)} --> {format_srt_time(chunk_end)}",
                        chunk,
                    ]
                )
            )
            subtitle_index += 1

    return blocks


def create_script_subtitle_file(
    task_id: str,
    list_script: Sequence[dict],
    output_file: Optional[str] = None,
    include_ost: Optional[Iterable[int]] = None,
    max_chars: int = DEFAULT_MAX_CHARS_PER_SUBTITLE,
) -> str:
    """Create a full SRT file from script narration and edited timeline ranges."""
    if not list_script:
        return ""

    if include_ost is None:
        include_ost = DEFAULT_SUBTITLE_OST_TYPES

    blocks = _build_srt_blocks(list_script, include_ost=include_ost, max_chars=max_chars)
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

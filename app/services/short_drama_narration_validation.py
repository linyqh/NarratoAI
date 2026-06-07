#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""Validation helpers for short drama narration scripts."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}$")
SCRIPT_RANGE_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})-(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})$"
)
SRT_RANGE_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)
VIDEO_HEADER_RE = re.compile(r"^#\s*视频\s*(?P<video_id>\d+)(?:\s*[:：]\s*(?P<video_name>.+?))?\s*$")
NARRATION_CHARS_PER_SECOND = 5.0
NARRATION_DURATION_TOLERANCE_SECONDS = 0.5


@dataclass(frozen=True)
class SubtitleCue:
    video_id: int
    video_name: str
    start_ms: int
    end_ms: int
    text: str
    timestamp: str


@dataclass(frozen=True)
class ScriptValidationResult:
    valid: bool
    errors: List[str]
    items: List[Dict[str, Any]]


class NarrationScriptValidationError(ValueError):
    """Raised when a narration script cannot be made safe for clipping."""


def timestamp_to_ms(timestamp: str) -> int:
    value = str(timestamp or "").strip().replace(".", ",")
    if not TIMESTAMP_RE.match(value):
        raise ValueError(f"时间戳格式错误: {timestamp}")

    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int(ms)


def ms_to_timestamp(ms: int) -> str:
    if ms < 0:
        raise ValueError("毫秒时间不能为负数")

    hours, remainder = divmod(ms, 60 * 60 * 1000)
    minutes, remainder = divmod(remainder, 60 * 1000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_script_timestamp_range(timestamp_range: str) -> Tuple[int, int, str]:
    value = str(timestamp_range or "").strip().replace(".", ",")
    match = SCRIPT_RANGE_RE.match(value)
    if not match:
        raise ValueError("时间戳格式应为 'HH:MM:SS,mmm-HH:MM:SS,mmm'")

    start = timestamp_to_ms(match.group("start"))
    end = timestamp_to_ms(match.group("end"))
    return start, end, f"{ms_to_timestamp(start)}-{ms_to_timestamp(end)}"


def _normalize_paths(paths: Optional[Iterable[str]]) -> List[str]:
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return []

    normalized = []
    for path in paths:
        if not isinstance(path, str):
            continue
        path = path.strip()
        if path:
            normalized.append(path)
    return normalized


def _default_video_name(video_id: int, video_paths: Sequence[str]) -> str:
    if 1 <= video_id <= len(video_paths):
        return os.path.basename(video_paths[video_id - 1])
    return ""


def _split_subtitle_sections(
    subtitle_content: str,
    video_paths: Sequence[str],
) -> List[Tuple[int, str, str]]:
    sections: List[Tuple[int, str, str]] = []
    current_video_id = 1
    current_video_name = _default_video_name(1, video_paths)
    current_lines: List[str] = []
    saw_header = False

    for line in str(subtitle_content or "").splitlines():
        header_match = VIDEO_HEADER_RE.match(line.strip())
        if header_match:
            if current_lines or saw_header:
                sections.append((current_video_id, current_video_name, "\n".join(current_lines)))
                current_lines = []

            saw_header = True
            current_video_id = int(header_match.group("video_id"))
            header_video_name = str(header_match.group("video_name") or "").strip()
            current_video_name = header_video_name or _default_video_name(current_video_id, video_paths)
            continue

        current_lines.append(line)

    if current_lines or not sections:
        sections.append((current_video_id, current_video_name, "\n".join(current_lines)))

    return sections


def _extract_cues_from_section(video_id: int, video_name: str, section_text: str) -> List[SubtitleCue]:
    lines = str(section_text or "").splitlines()
    cues: List[SubtitleCue] = []
    index = 0

    while index < len(lines):
        match = SRT_RANGE_RE.search(lines[index])
        if not match:
            index += 1
            continue

        start_ms = timestamp_to_ms(match.group("start"))
        end_ms = timestamp_to_ms(match.group("end"))
        timestamp = f"{ms_to_timestamp(start_ms)}-{ms_to_timestamp(end_ms)}"
        index += 1

        text_lines: List[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1

        cues.append(
            SubtitleCue(
                video_id=video_id,
                video_name=video_name,
                start_ms=start_ms,
                end_ms=end_ms,
                text=" ".join(text_lines).strip(),
                timestamp=timestamp,
            )
        )
        index += 1

    return cues


def build_subtitle_index(subtitle_content: str, video_paths: Optional[Iterable[str]] = None) -> List[SubtitleCue]:
    """Build a per-video subtitle index from combined SRT text."""
    normalized_video_paths = _normalize_paths(video_paths)
    cues: List[SubtitleCue] = []

    for video_id, video_name, section_text in _split_subtitle_sections(subtitle_content, normalized_video_paths):
        cues.extend(_extract_cues_from_section(video_id, video_name, section_text))

    return cues


def _coerce_positive_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _video_id_by_name(video_name: Any, video_paths: Sequence[str]) -> Optional[int]:
    normalized_name = os.path.basename(str(video_name or "").strip())
    if not normalized_name:
        return None

    for index, path in enumerate(video_paths, start=1):
        if os.path.basename(path) == normalized_name:
            return index
    return None


def normalize_script_video_sources(
    items: Sequence[Dict[str, Any]],
    video_paths: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Normalize video_name from a valid source without inventing video_id."""
    normalized_video_paths = _normalize_paths(video_paths)
    normalized_items: List[Dict[str, Any]] = []

    for raw_item in items:
        item = dict(raw_item)
        video_id = _coerce_positive_int(item.get("video_id") or item.get("video_index"))
        matched_video_id = _video_id_by_name(item.get("video_name") or item.get("source_video"), normalized_video_paths)
        if matched_video_id is not None:
            video_id = matched_video_id

        if video_id is not None:
            item["video_id"] = video_id
            if 1 <= video_id <= len(normalized_video_paths):
                item["video_name"] = os.path.basename(normalized_video_paths[video_id - 1])

        normalized_items.append(item)

    return normalized_items


def _cues_for_video(cues: Sequence[SubtitleCue], video_id: int) -> List[SubtitleCue]:
    return [cue for cue in cues if cue.video_id == video_id]


def _range_overlaps_subtitle(cues: Sequence[SubtitleCue], start_ms: int, end_ms: int) -> bool:
    return any(start_ms < cue.end_ms and end_ms > cue.start_ms for cue in cues)


def _range_within_subtitle_bounds(cues: Sequence[SubtitleCue], start_ms: int, end_ms: int) -> bool:
    if not cues:
        return False
    return min(cue.start_ms for cue in cues) <= start_ms and end_ms <= max(cue.end_ms for cue in cues)


def _item_ost(item: Dict[str, Any]) -> Optional[int]:
    try:
        return int(item.get("OST"))
    except (TypeError, ValueError):
        return None


def _item_video_id(item: Dict[str, Any]) -> Optional[int]:
    return _coerce_positive_int(item.get("video_id"))


def count_narration_chars(text: str) -> int:
    """Count visible narration characters for rough TTS/video-duration matching."""
    return len(re.sub(r"\s+", "", str(text or "")))


def max_narration_chars_for_duration(start_ms: int, end_ms: int) -> int:
    duration_seconds = max(0.0, (end_ms - start_ms) / 1000)
    return max(8, int((duration_seconds + NARRATION_DURATION_TOLERANCE_SECONDS) * NARRATION_CHARS_PER_SECOND))


def _validate_story_continuity(items: Sequence[Dict[str, Any]]) -> List[str]:
    """Validate structural continuity rules that affect viewer comprehension."""
    errors: List[str] = []
    consecutive_ost = 0
    previous_item: Optional[Dict[str, Any]] = None

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            consecutive_ost = 0
            previous_item = None
            continue

        item_id = item.get("_id", index + 1)
        ost = _item_ost(item)
        if index == 0 and ost != 0:
            errors.append(f"片段 {item_id} 必须是 OST=0 解说开场钩子，不能直接播放原片")

        if ost == 1:
            consecutive_ost += 1
            if consecutive_ost > 2:
                errors.append(f"片段 {item_id} 连续原声过多，必须插入 OST=0 解说承接剧情")
        else:
            consecutive_ost = 0

        if previous_item is not None:
            previous_video_id = _item_video_id(previous_item)
            current_video_id = _item_video_id(item)
            if (
                previous_video_id is not None
                and current_video_id is not None
                and previous_video_id != current_video_id
                and _item_ost(previous_item) == 1
                and ost == 1
            ):
                errors.append(
                    f"片段 {previous_item.get('_id')} 到片段 {item_id} 跨视频切换缺少 OST=0 解说桥段"
                )

        previous_item = item

    return errors


def validate_narration_script_items(
    items: Any,
    subtitle_index: Sequence[SubtitleCue],
    video_paths: Optional[Iterable[str]] = None,
) -> ScriptValidationResult:
    """Validate final narration items against subtitle/video source constraints."""
    errors: List[str] = []
    if not isinstance(items, list) or not items:
        return ScriptValidationResult(False, ["解说脚本 items 必须是非空数组"], [])

    normalized_video_paths = _normalize_paths(video_paths)
    normalized_items = normalize_script_video_sources(items, normalized_video_paths)
    available_video_ids = {cue.video_id for cue in subtitle_index}
    if normalized_video_paths:
        available_video_ids.update(range(1, len(normalized_video_paths) + 1))

    ranges_by_video: Dict[int, List[Tuple[int, int, int]]] = {}
    seen_ids = set()
    required_fields = ["_id", "video_id", "video_name", "timestamp", "picture", "narration", "OST"]

    for index, item in enumerate(normalized_items):
        if not isinstance(item, dict):
            errors.append(f"第 {index + 1} 个片段必须是对象")
            continue

        item_id = item.get("_id", index + 1)
        coerced_item_id = _coerce_positive_int(item_id)
        if coerced_item_id is None:
            errors.append(f"第 {index + 1} 个片段缺少有效 _id")
            coerced_item_id = index + 1
        elif coerced_item_id in seen_ids:
            errors.append(f"片段 _id={coerced_item_id} 重复")
        seen_ids.add(coerced_item_id)

        for field in required_fields:
            if field not in item:
                errors.append(f"片段 {item_id} 缺少字段 {field}")

        video_id = _coerce_positive_int(item.get("video_id"))
        if video_id is None:
            errors.append(f"片段 {item_id} 缺少有效 video_id")
            continue

        if available_video_ids and video_id not in available_video_ids:
            errors.append(f"片段 {item_id} 的 video_id={video_id} 不在已选视频范围内")

        expected_video_name = _default_video_name(video_id, normalized_video_paths)
        if expected_video_name and os.path.basename(str(item.get("video_name") or "")) != expected_video_name:
            errors.append(f"片段 {item_id} 的 video_name 必须是 {expected_video_name}")

        try:
            start_ms, end_ms, normalized_timestamp = parse_script_timestamp_range(item.get("timestamp", ""))
            item["timestamp"] = normalized_timestamp
        except ValueError as exc:
            errors.append(f"片段 {item_id}: {exc}")
            continue

        if start_ms >= end_ms:
            errors.append(f"片段 {item_id} 的开始时间必须早于结束时间")
            continue

        video_cues = _cues_for_video(subtitle_index, video_id)
        if not _range_within_subtitle_bounds(video_cues, start_ms, end_ms):
            errors.append(f"片段 {item_id} 的时间戳不在视频 {video_id} 的字幕范围内")
        elif not _range_overlaps_subtitle(video_cues, start_ms, end_ms):
            errors.append(f"片段 {item_id} 的时间戳没有命中视频 {video_id} 的字幕内容")

        for text_field in ["picture", "narration"]:
            if not isinstance(item.get(text_field), str) or not item[text_field].strip():
                errors.append(f"片段 {item_id} 的 {text_field} 不能为空")

        ost = _item_ost(item)
        if item.get("OST") not in [0, 1, 2]:
            errors.append(f"片段 {item_id} 的 OST 必须是 0、1 或 2")
        if ost == 1 and not str(item.get("narration", "")).startswith("播放原片"):
            errors.append(f"片段 {item_id} 是原声片段，narration 必须使用“播放原片+序号”")
        if ost == 0:
            narration_chars = count_narration_chars(item.get("narration", ""))
            max_chars = max_narration_chars_for_duration(start_ms, end_ms)
            if narration_chars > max_chars:
                duration_seconds = (end_ms - start_ms) / 1000
                errors.append(
                    f"片段 {item_id} 解说过密：{narration_chars} 字需要约 {narration_chars / NARRATION_CHARS_PER_SECOND:.1f} 秒，"
                    f"但画面只有 {duration_seconds:.1f} 秒，建议不超过 {max_chars} 字或延长画面"
                )

        ranges_by_video.setdefault(video_id, []).append((start_ms, end_ms, coerced_item_id))

    for video_id, ranges in ranges_by_video.items():
        sorted_ranges = sorted(ranges, key=lambda item: (item[0], item[1], item[2]))
        previous_start, previous_end, previous_id = sorted_ranges[0]
        for start_ms, end_ms, item_id in sorted_ranges[1:]:
            if start_ms < previous_end:
                errors.append(f"视频 {video_id} 的片段 {item_id} 与片段 {previous_id} 时间戳重叠")
            if end_ms > previous_end:
                previous_start, previous_end, previous_id = start_ms, end_ms, item_id

    errors.extend(_validate_story_continuity(normalized_items))

    return ScriptValidationResult(not errors, errors, normalized_items)


def require_valid_narration_script_items(
    items: Any,
    subtitle_index: Sequence[SubtitleCue],
    video_paths: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    result = validate_narration_script_items(items, subtitle_index, video_paths)
    if not result.valid:
        raise NarrationScriptValidationError("\n".join(result.errors))
    return result.items


def summarize_subtitle_window(
    subtitle_index: Sequence[SubtitleCue],
    max_cues_per_video: int = 80,
) -> str:
    """Return compact subtitle context for a repair prompt."""
    lines: List[str] = []
    by_video: Dict[int, List[SubtitleCue]] = {}
    for cue in subtitle_index:
        by_video.setdefault(cue.video_id, []).append(cue)

    for video_id in sorted(by_video):
        cues = by_video[video_id][:max_cues_per_video]
        video_name = cues[0].video_name if cues else ""
        header = f"# 视频 {video_id}: {video_name}" if video_name else f"# 视频 {video_id}"
        lines.append(header)
        for cue in cues:
            text = cue.text.replace("\n", " ").strip()
            lines.append(f"{cue.timestamp} {text}")
        if len(by_video[video_id]) > max_cues_per_video:
            lines.append(f"... 已省略 {len(by_video[video_id]) - max_cues_per_video} 条字幕")

    return "\n".join(lines)

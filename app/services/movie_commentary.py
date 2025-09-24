"""Service utilities for producing movie commentary cuts."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from uuid import uuid4

from loguru import logger

from app.config import config
from app.models.schema import VideoClipParams
from app.services import task
from app.services.script_service import ScriptGenerator
from app.utils import utils

ProgressCallback = Optional[Callable[[float, str], None]]
ScriptInput = Optional[Union[str, os.PathLike, Sequence[Dict[str, Any]]]]


class MovieCommentaryService:
    """High level orchestration for movie commentary generation."""

    def __init__(self, script_generator: Optional[ScriptGenerator] = None) -> None:
        self.script_generator = script_generator or ScriptGenerator()

    async def generate_commentary_script(
        self,
        video_path: str,
        *,
        script: ScriptInput = None,
        auto_generate: bool = False,
        video_theme: str = "",
        custom_prompt: str = "",
        frame_interval: int = 5,
        skip_seconds: int = 0,
        threshold: int = 30,
        vision_batch_size: int = 5,
        vision_provider: str = "gemini",
        script_output_path: Optional[Union[str, os.PathLike]] = None,
        progress_callback: ProgressCallback = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Prepare a normalized commentary script for the given movie."""

        progress = progress_callback or (lambda *_: None)

        if auto_generate or script is None:
            if not video_path or not os.path.exists(video_path):
                raise FileNotFoundError(f"视频文件不存在: {video_path}")

            progress(5, "正在自动生成电影解说脚本")
            script_progress = self._wrap_progress(progress, start=5, span=55)
            raw_segments = await self.script_generator.generate_script(
                video_path=video_path,
                video_theme=video_theme,
                custom_prompt=custom_prompt,
                frame_interval_input=frame_interval,
                skip_seconds=skip_seconds,
                threshold=threshold,
                vision_batch_size=vision_batch_size,
                vision_llm_provider=vision_provider,
                progress_callback=script_progress,
            )
        else:
            progress(5, "正在加载用户提供的解说脚本")
            raw_segments = self._load_user_script(script)

        normalized_segments = self._normalize_segments(raw_segments)
        progress(60, "解说脚本规范化完成")

        script_path = self._save_script(normalized_segments, script_output_path)
        progress(65, f"脚本已保存: {script_path}")

        return normalized_segments, script_path

    async def generate_commentary_video(
        self,
        video_path: str,
        *,
        script: ScriptInput = None,
        auto_generate: bool = False,
        video_theme: str = "",
        custom_prompt: str = "",
        frame_interval: int = 5,
        skip_seconds: int = 0,
        threshold: int = 30,
        vision_batch_size: int = 5,
        vision_provider: str = "gemini",
        voice_options: Optional[Dict[str, Any]] = None,
        subtitle_options: Optional[Dict[str, Any]] = None,
        mix_options: Optional[Dict[str, Any]] = None,
        script_output_path: Optional[Union[str, os.PathLike]] = None,
        task_id: Optional[str] = None,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        """Generate a movie commentary cut and return metadata about the outputs."""

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        progress = progress_callback or (lambda *_: None)

        segments, script_path = await self.generate_commentary_script(
            video_path,
            script=script,
            auto_generate=auto_generate,
            video_theme=video_theme,
            custom_prompt=custom_prompt,
            frame_interval=frame_interval,
            skip_seconds=skip_seconds,
            threshold=threshold,
            vision_batch_size=vision_batch_size,
            vision_provider=vision_provider,
            script_output_path=script_output_path,
            progress_callback=progress,
        )

        params = self._build_video_params(
            video_path=video_path,
            script_path=script_path,
            script_segments=segments,
            voice_options=voice_options or {},
            subtitle_options=subtitle_options or {},
            mix_options=mix_options or {},
        )

        task_identifier = task_id or str(uuid4())
        progress(75, "正在裁剪电影片段并匹配解说")
        result = task.start_subclip_unified(task_identifier, params)
        progress(100, "电影解说生成完成")

        payload = {
            "task_id": task_identifier,
            "script_path": script_path,
            "script": segments,
        }
        if isinstance(result, dict):
            payload.update(result)
        return payload

    def _load_user_script(self, script: ScriptInput) -> Sequence[Dict[str, Any]]:
        if script is None:
            raise ValueError("未提供解说脚本内容")

        if isinstance(script, (list, tuple)):
            return list(script)

        if isinstance(script, (str, os.PathLike)):
            path = Path(script)
            if path.exists():
                logger.info(f"加载解说脚本文件: {path}")
                content = path.read_text(encoding="utf-8")
            else:
                content = str(script)
            cleaned = utils.clean_model_output(content)
            return json.loads(cleaned)

        raise TypeError("解说脚本必须是JSON文本、文件路径或脚本列表")

    def _normalize_segments(self, segments: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        indexed_segments = list(segments or [])
        if not indexed_segments:
            raise ValueError("解说脚本不能为空")

        for index, raw_segment in enumerate(indexed_segments):
            if not isinstance(raw_segment, dict):
                raise TypeError("解说脚本片段必须是对象类型")

            start, end, duration, start_seconds = self._normalize_timestamp(raw_segment.get("timestamp"))
            ost_value = self._coerce_ost(raw_segment.get("OST", 2))
            narration = (raw_segment.get("narration") or "").strip()
            if ost_value != 1 and not narration:
                raise ValueError("非纯原声片段必须包含解说内容")

            picture = raw_segment.get("picture", "")
            if picture is None:
                picture = ""

            normalized_segment = dict(raw_segment)
            normalized_segment["timestamp"] = f"{start}-{end}"
            normalized_segment["OST"] = ost_value
            normalized_segment["narration"] = narration
            normalized_segment.setdefault("picture", picture)
            normalized_segment["duration"] = round(duration, 3)
            normalized_segment["_sort_index"] = (start_seconds, index)
            normalized.append(normalized_segment)

        normalized.sort(key=lambda item: item.pop("_sort_index"))
        for idx, segment in enumerate(normalized, start=1):
            segment["_id"] = idx
        return normalized

    def _normalize_timestamp(self, timestamp: Any) -> Tuple[str, str, float, float]:
        if not isinstance(timestamp, str) or "-" not in timestamp:
            raise ValueError("时间戳格式错误，应为 '开始-结束'")

        start_raw, end_raw = timestamp.split("-", 1)
        start_value = self._normalize_single_timestamp(start_raw)
        end_value = self._normalize_single_timestamp(end_raw)

        start_seconds = utils.time_to_seconds(start_value)
        end_seconds = utils.time_to_seconds(end_value)
        duration = end_seconds - start_seconds

        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("时间戳范围必须大于0")

        return start_value, end_value, duration, start_seconds

    def _normalize_single_timestamp(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("时间戳不能为空")

        cleaned = value.strip()
        sanitized = cleaned.replace("，", ",")
        components = sanitized.replace(",", ".").split(":")

        try:
            if len(components) == 3:
                hours = int(components[0])
                minutes = int(components[1])
                seconds = float(components[2])
            elif len(components) == 2:
                hours = 0
                minutes = int(components[0])
                seconds = float(components[1])
            elif len(components) == 1:
                hours = 0
                minutes = 0
                seconds = float(components[0])
            else:
                raise ValueError
        except ValueError as exc:
            raise ValueError("时间戳格式错误") from exc

        if hours < 0 or minutes < 0 or seconds < 0:
            raise ValueError("时间戳不能为负数")

        total_seconds = hours * 3600 + minutes * 60 + seconds
        return self._format_seconds(total_seconds)

    def _format_seconds(self, seconds: float) -> str:
        if seconds < 0:
            raise ValueError("时间戳不能为负数")

        whole_seconds = int(seconds)
        milliseconds = int(round((seconds - whole_seconds) * 1000))
        if milliseconds == 1000:
            milliseconds = 0
            whole_seconds += 1

        hours = whole_seconds // 3600
        minutes = (whole_seconds % 3600) // 60
        secs = whole_seconds % 60

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def _coerce_ost(self, value: Any) -> int:
        if isinstance(value, bool):
            value = int(value)
        if isinstance(value, (int, float)):
            ost = int(value)
        elif isinstance(value, str):
            ost = int(value.strip())
        else:
            ost = 2

        if ost not in {0, 1, 2}:
            raise ValueError("OST 字段必须是 0、1 或 2")
        return ost

    def _build_video_params(
        self,
        *,
        video_path: str,
        script_path: str,
        script_segments: List[Dict[str, Any]],
        voice_options: Dict[str, Any],
        subtitle_options: Dict[str, Any],
        mix_options: Dict[str, Any],
    ) -> VideoClipParams:
        defaults = VideoClipParams()

        def pick(options: Dict[str, Any], keys: Sequence[str], fallback: Any) -> Any:
            for key in keys:
                if key in options and options[key] is not None:
                    return options[key]
            return fallback

        subtitle_enabled = pick(subtitle_options, ["enabled", "subtitle_enabled"], defaults.subtitle_enabled)
        font_name = pick(subtitle_options, ["font_name"], defaults.font_name)
        font_size = pick(subtitle_options, ["font_size"], defaults.font_size)
        text_color = pick(subtitle_options, ["color", "text_fore_color"], defaults.text_fore_color)
        text_background = pick(subtitle_options, ["background", "text_back_color"], defaults.text_back_color)
        stroke_color = pick(subtitle_options, ["stroke_color"], defaults.stroke_color)
        stroke_width = pick(subtitle_options, ["stroke_width"], defaults.stroke_width)
        subtitle_position = pick(subtitle_options, ["position", "subtitle_position"], defaults.subtitle_position)
        custom_position = pick(subtitle_options, ["custom_position"], defaults.custom_position)
        threads = pick(subtitle_options, ["threads", "n_threads"], defaults.n_threads)

        voice_name = pick(voice_options, ["voice_name"], defaults.voice_name)
        voice_volume = pick(voice_options, ["voice_volume"], defaults.voice_volume)
        voice_rate = pick(voice_options, ["voice_rate"], defaults.voice_rate)
        voice_pitch = pick(voice_options, ["voice_pitch"], defaults.voice_pitch)
        tts_engine = pick(voice_options, ["tts_engine"], config.app.get("tts_engine", "edge_tts"))

        tts_volume = pick(mix_options, ["tts_volume"], defaults.tts_volume)
        original_volume = pick(mix_options, ["original_volume"], defaults.original_volume)
        bgm_volume = pick(mix_options, ["bgm_volume"], defaults.bgm_volume)

        params = VideoClipParams(
            video_clip_json=script_segments,
            video_clip_json_path=str(script_path),
            video_origin_path=video_path,
            voice_name=voice_name,
            voice_volume=voice_volume,
            voice_rate=voice_rate,
            voice_pitch=voice_pitch,
            tts_engine=tts_engine,
            subtitle_enabled=subtitle_enabled,
            font_name=font_name,
            font_size=font_size,
            text_fore_color=text_color,
            text_back_color=text_background,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            subtitle_position=subtitle_position,
            custom_position=custom_position,
            n_threads=threads,
            tts_volume=tts_volume,
            original_volume=original_volume,
            bgm_volume=bgm_volume,
        )
        return params

    def _save_script(
        self,
        segments: List[Dict[str, Any]],
        script_output_path: Optional[Union[str, os.PathLike]],
    ) -> str:
        if script_output_path:
            target_path = Path(script_output_path)
        else:
            base_dir = Path(utils.script_dir("movie_commentary"))
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_path = base_dir / f"movie_commentary_{timestamp}_{uuid4().hex[:8]}.json"

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"电影解说脚本已保存: {target_path}")
        return str(target_path)

    def _wrap_progress(
        self,
        callback: Callable[[float, str], None],
        *,
        start: float,
        span: float,
    ) -> Callable[[float, str], None]:
        def wrapper(progress: float, message: str) -> None:
            scaled = start + (span * (progress / 100.0))
            callback(min(99.0, scaled), message)

        return wrapper

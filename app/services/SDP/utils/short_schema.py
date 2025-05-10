"""
定义项目中使用的数据类型
"""
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PlotPoint:
    timestamp: str
    title: str
    picture: str


@dataclass
class Commentary:
    timestamp: str
    title: str
    copywriter: str


@dataclass
class SubtitleSegment:
    start_time: float
    end_time: float
    text: str


@dataclass
class ScriptItem:
    timestamp: str
    title: str
    picture: str
    copywriter: str


@dataclass
class PipelineResult:
    output_video_path: str
    plot_points: List[PlotPoint]
    subtitle_segments: List[SubtitleSegment]
    commentaries: List[Commentary]
    final_script: List[ScriptItem]
    error: Optional[str] = None


class VideoProcessingError(Exception):
    pass


class SubtitleProcessingError(Exception):
    pass


class PlotAnalysisError(Exception):
    pass


class CopywritingError(Exception):
    pass

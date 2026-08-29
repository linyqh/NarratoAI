from dataclasses import dataclass, field
from typing import Any

from app.config.defaults import DEFAULT_VISION_MAX_CONCURRENCY


@dataclass(frozen=True, slots=True)
class TimeRange:
    text: str
    start_seconds: float
    end_seconds: float

    @classmethod
    def parse(cls, value: str) -> "TimeRange":
        text = str(value or "").strip()
        parts = text.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"invalid time range: {value}")
        start_seconds = cls._parse_timestamp(parts[0])
        end_seconds = cls._parse_timestamp(parts[1])
        if end_seconds <= start_seconds:
            raise ValueError(f"invalid time range: {value}")
        return cls(text=text, start_seconds=start_seconds, end_seconds=end_seconds)

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        time_part, separator, milliseconds_part = value.strip().partition(",")
        fields = time_part.split(":")
        if len(fields) != 3 or not all(field.isdigit() for field in fields):
            raise ValueError(value)
        hours, minutes, seconds = (int(field) for field in fields)
        if minutes > 59 or seconds > 59:
            raise ValueError(value)
        if separator:
            if not milliseconds_part.isdigit() or len(milliseconds_part) > 3:
                raise ValueError(value)
            milliseconds = int(milliseconds_part.ljust(3, "0"))
        else:
            milliseconds = 0
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

    def __str__(self) -> str:
        return self.text


@dataclass(slots=True)
class DocumentaryAnalysisConfig:
    video_path: str
    frame_interval_seconds: float
    vision_batch_size: int
    vision_llm_provider: str
    vision_model_name: str
    custom_prompt: str = ""
    max_concurrency: int = DEFAULT_VISION_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        if self.frame_interval_seconds <= 0:
            raise ValueError("frame_interval_seconds must be > 0")
        if self.vision_batch_size <= 0:
            raise ValueError("vision_batch_size must be > 0")
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be > 0")


@dataclass(frozen=True, slots=True)
class HighlightCandidate:
    """A visually grounded OST recommendation inside one analyzed batch."""

    time_range: TimeRange
    category: str
    reason: str
    score: int
    story_importance: int = 3
    visual_impact: int = 3
    performance_value: int = 3
    video_id: int | None = None
    video_name: str = ""
    source_video_identity: dict[str, Any] | None = None
    source_identity_status: str = "unavailable"
    defaulted_signals: tuple[str, ...] = ()
    candidate_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "time_range": str(self.time_range),
            "category": self.category,
            "reason": self.reason,
            "score": self.score,
            "story_importance": self.story_importance,
            "visual_impact": self.visual_impact,
            "performance_value": self.performance_value,
        }
        if self.video_id is not None:
            payload["video_id"] = self.video_id
        if self.video_name:
            payload["video_name"] = self.video_name
        if self.source_video_identity is not None:
            payload["source_video_identity"] = self.source_video_identity
        if self.source_identity_status != "unavailable":
            payload["source_identity_status"] = self.source_identity_status
        if self.defaulted_signals:
            payload["defaulted_signals"] = list(self.defaulted_signals)
        if self.candidate_id:
            payload["candidate_id"] = self.candidate_id
        return payload


@dataclass(slots=True)
class FrameBatchResult:
    batch_index: int
    status: str
    time_range: str
    raw_response: str
    frame_paths: list[str] = field(default_factory=list)
    frame_observations: list[dict] = field(default_factory=list)
    overall_activity_summary: str = ""
    highlight_candidates: list[HighlightCandidate] = field(default_factory=list)
    fallback_summary: str = ""
    error_message: str = ""

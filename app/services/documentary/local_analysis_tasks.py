"""Durable planning primitives for local full-film visual analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
from typing import Any, Callable
from uuid import uuid4

from app.services.documentary.frame_analysis_models import FrameBatchResult, HighlightCandidate, TimeRange


@dataclass(frozen=True, slots=True)
class FullFilmAnalysisEstimate:
    duration_seconds: float
    keyframe_count: int
    request_count: int
    estimated_minutes: int


class LocalAnalysisTaskStore:
    """Persist task state so a returning UI can resume a local analysis safely."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def create(self, request: dict, source_identity: dict) -> dict:
        task_id = uuid4().hex
        task = {
            "task_id": task_id,
            "status": "queued",
            "request": request,
            "source_video_identity": source_identity,
            "completed_batches": [],
            "cancel_requested": False,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._write(task)
        return task

    def read(self, task_id: str) -> dict:
        with self._path(task_id).open(encoding="utf-8") as handle:
            return json.load(handle)

    def update(self, task_id: str, **changes) -> dict:
        task = self.read(task_id)
        task.update(changes)
        task["updated_at"] = self._now()
        self._write(task)
        return task

    def request_cancel(self, task_id: str) -> dict:
        return self.update(task_id, cancel_requested=True)

    def find_latest_for_source(self, source_identity: dict) -> dict | None:
        """Return the most recent non-completed task for exactly this source content."""
        matches = []
        for path in self._directory.glob("*.json"):
            try:
                with path.open(encoding="utf-8") as handle:
                    task = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            if task.get("source_video_identity") == source_identity and task.get("status") != "completed":
                matches.append(task)
        return max(matches, key=lambda task: str(task.get("updated_at") or ""), default=None)

    def _path(self, task_id: str) -> Path:
        if not task_id.isalnum():
            raise ValueError("invalid local analysis task id")
        return self._directory / f"{task_id}.json"

    def _write(self, task: dict) -> None:
        path = self._path(str(task["task_id"]))
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(task, handle, ensure_ascii=False, indent=2)
        temporary.replace(path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


class LocalAnalysisTaskRunner:
    """Run one local task outside Streamlit's request lifecycle."""

    def __init__(self, store: LocalAnalysisTaskStore) -> None:
        self._store = store

    def start(
        self,
        task_id: str,
        work: Callable[[Callable[[float, str], None], Callable[[dict], None], Callable[[], bool]], dict[str, Any]],
    ) -> threading.Thread:
        def run() -> None:
            self._store.update(task_id, status="running")

            def cancelled() -> bool:
                return bool(self._store.read(task_id).get("cancel_requested"))

            def progress(value: float, message: str = "") -> None:
                self._store.update(task_id, progress=max(0, min(100, float(value))), message=message)

            def checkpoint(batch: dict) -> None:
                task = self._store.read(task_id)
                completed = [item for item in task.get("completed_batches", []) if item.get("batch_index") != batch.get("batch_index")]
                completed.append(batch)
                self._store.update(task_id, completed_batches=completed)

            try:
                result = work(progress, checkpoint, cancelled)
                self._store.update(task_id, status="cancelled" if cancelled() else "completed", **result)
            except Exception as exc:
                self._store.update(task_id, status="cancelled" if cancelled() else "failed", error_message=str(exc))

        thread = threading.Thread(target=run, name=f"local-analysis-{task_id}", daemon=True)
        thread.start()
        return thread


def estimate_full_film_analysis(
    duration_seconds: float,
    frame_interval_seconds: float,
    vision_batch_size: int,
    max_concurrency: int,
) -> FullFilmAnalysisEstimate:
    """Estimate the full local-video work without sampling or submitting requests."""
    if duration_seconds < 0 or frame_interval_seconds <= 0 or vision_batch_size <= 0 or max_concurrency <= 0:
        raise ValueError("full-film analysis settings must be positive")
    keyframe_count = max(1, math.ceil(duration_seconds / frame_interval_seconds))
    request_count = math.ceil(keyframe_count / vision_batch_size)
    # A conservative one-minute estimate per request lane; it is deliberately
    # an estimate, not provider-specific billing or an execution guarantee.
    estimated_minutes = max(1, math.ceil(request_count / max_concurrency))
    return FullFilmAnalysisEstimate(
        duration_seconds=duration_seconds,
        keyframe_count=keyframe_count,
        request_count=request_count,
        estimated_minutes=estimated_minutes,
    )


def batch_checkpoint_from_result(batch: FrameBatchResult) -> dict[str, Any]:
    return {
        "batch_index": batch.batch_index, "status": batch.status, "time_range": batch.time_range,
        "raw_response": batch.raw_response, "frame_paths": batch.frame_paths,
        "frame_observations": batch.frame_observations, "overall_activity_summary": batch.overall_activity_summary,
        "highlight_candidates": [candidate.to_dict() for candidate in batch.highlight_candidates],
        "fallback_summary": batch.fallback_summary, "error_message": batch.error_message,
    }


def batch_result_from_checkpoint(payload: dict[str, Any]) -> FrameBatchResult:
    candidates = [
        HighlightCandidate(
            time_range=TimeRange.parse(str(candidate["time_range"])), category=str(candidate["category"]),
            reason=str(candidate["reason"]), score=int(candidate["score"]),
            story_importance=int(candidate.get("story_importance", 3)), visual_impact=int(candidate.get("visual_impact", 3)),
            performance_value=int(candidate.get("performance_value", 3)), video_id=candidate.get("video_id"),
            video_name=str(candidate.get("video_name") or ""), candidate_id=str(candidate.get("candidate_id") or ""),
        ) for candidate in payload.get("highlight_candidates", []) if isinstance(candidate, dict)
    ]
    return FrameBatchResult(
        batch_index=int(payload["batch_index"]), status=str(payload["status"]), time_range=str(payload["time_range"]),
        raw_response=str(payload.get("raw_response") or ""), frame_paths=list(payload.get("frame_paths") or []),
        frame_observations=list(payload.get("frame_observations") or []), overall_activity_summary=str(payload.get("overall_activity_summary") or ""),
        highlight_candidates=candidates, fallback_summary=str(payload.get("fallback_summary") or ""), error_message=str(payload.get("error_message") or ""),
    )

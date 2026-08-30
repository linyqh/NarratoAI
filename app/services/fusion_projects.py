"""Durable ownership and projection for Film Vision Fusion projects."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
from typing import Any
from uuid import uuid4


PROJECT_SCHEMA_VERSION = 1
STAGES = ("setup", "evidence", "narration", "matching", "review", "output")
ACTIVE_TASK_STATUSES = {"queued", "running", "rendering"}
CONTENT_MUTATING_TASK_KINDS = {
    "narration_generation", "fusion_plan", "fusion_matching", "segment_repair", "render"
}
RUNTIME_ID = uuid4().hex
_STORE_LOCKS: dict[str, threading.RLock] = {}
_STORE_LOCKS_GUARD = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialized(method):
    """Serialize a complete read-modify-write operation within the local app process."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class FusionProjectStore:
    """Atomic local repository for project records and managed project data."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        lock_key = str(self._directory.resolve())
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(lock_key, threading.RLock())

    @_serialized
    def create(self, name: str = "Untitled Fusion Project") -> dict[str, Any]:
        project_id = uuid4().hex
        now = _now()
        project = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "revision": 1,
            "project_id": project_id,
            "name": str(name or "Untitled Fusion Project").strip(),
            "mode": "film_vision_fusion",
            "status": "draft",
            "active_stage": "setup",
            "created_at": now,
            "updated_at": now,
            "source_video_sequence": [],
            "project_settings": {
                "output_language": "简体中文（中国）",
                "commentary_style": "剧情解说",
                "voice_profile": "",
                "target_narration_length": 1200,
                "subtitle_policy": "source_or_asr",
                "original_sound_ratio": 30,
                "background_music": "",
            },
            "artifact_refs": {},
            "task_refs": [],
            "active_version_id": "",
            "review_decisions": [],
            "review_findings": [],
            "render_outcomes": [],
            "render_authorizations": [],
            "content_drafts": [],
            "versions": [],
            "stale_task_results": [],
            "trash_state": None,
            "archive_state": None,
            "last_runtime_id": RUNTIME_ID,
            "migration_state": None,
        }
        self._project_directory(project_id).mkdir(parents=True, exist_ok=False)
        self._write(project)
        return project

    def read(self, project_id: str) -> dict[str, Any]:
        path = self._record_path(project_id)
        with path.open(encoding="utf-8") as handle:
            project = json.load(handle)
        if int(project.get("schema_version") or 0) != PROJECT_SCHEMA_VERSION:
            raise ValueError("unsupported Fusion Project schema version")
        return project

    @_serialized
    def update(self, project_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            project = self.read(project_id)
            if "project_id" in changes or "schema_version" in changes:
                raise ValueError("Fusion Project identity fields are immutable")
            project.update(changes)
            project["revision"] = int(project.get("revision") or 0) + 1
            project["updated_at"] = _now()
            self._write(project)
            return project

    def list_projects(self, *, include_trashed: bool = False) -> list[dict[str, Any]]:
        projects = []
        for path in self._directory.glob("*/project.json"):
            try:
                project = self.read(path.parent.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if include_trashed or not project.get("trash_state"):
                projects.append(project)
        return sorted(
            projects, key=lambda item: str(item.get("updated_at") or ""), reverse=True
        )

    def trash(self, project_id: str) -> dict[str, Any]:
        return self.update(project_id, trash_state={"trashed_at": _now()})

    def restore(self, project_id: str) -> dict[str, Any]:
        return self.update(project_id, trash_state=None)

    def rename(self, project_id: str, name: str) -> dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            raise ValueError("Fusion Project name cannot be empty")
        return self.update(project_id, name=name)

    def archive(self, project_id: str) -> dict[str, Any]:
        return self.update(project_id, archive_state={"archived_at": _now()})

    def unarchive(self, project_id: str) -> dict[str, Any]:
        return self.update(project_id, archive_state=None)

    def add_local_reference(
        self,
        project_id: str,
        *,
        path: str,
        subtitle_path: str = "",
    ) -> dict[str, Any]:
        source_path = Path(str(path)).expanduser()
        source = self._source_record(
            kind="local_reference",
            path=source_path,
            subtitle_path=subtitle_path,
        )
        self._append_source(project_id, source)
        return source

    def add_managed_asset(
        self,
        project_id: str,
        *,
        filename: str,
        content: bytes,
        subtitle_path: str = "",
    ) -> dict[str, Any]:
        safe_name = Path(str(filename or "source-video")).name.strip() or "source-video"
        assets = self._project_directory(project_id) / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        target = assets / safe_name
        if target.exists():
            target = assets / f"{target.stem}-{uuid4().hex[:8]}{target.suffix}"
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(bytes(content))
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        source = self._source_record(
            kind="managed_asset",
            path=target,
            subtitle_path=subtitle_path,
        )
        self._append_source(project_id, source)
        return source

    @_serialized
    def refresh_source_availability(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            project = self.read(project_id)
            sources = list(project.get("source_video_sequence") or [])
            artifacts = dict(project.get("artifact_refs") or {})
            findings = list(project.get("review_findings") or [])
            changed_source_ids: list[str] = []
            for source in sources:
                path = Path(str(source.get("path") or ""))
                source["available"] = path.is_file()
                observed = self._source_identity(path) if path.is_file() else {}
                accepted = dict(source.get("identity") or {})
                source["observed_identity"] = observed
                if not observed:
                    source["identity_status"] = "offline"
                elif accepted and observed.get("fingerprint") != accepted.get("fingerprint"):
                    source["identity_status"] = "changed"
                    source["visual_evidence_status"] = "stale"
                    changed_source_ids.append(str(source.get("source_id") or ""))
                else:
                    source["identity_status"] = "verified"
                    if not accepted:
                        source["identity"] = observed

            if changed_source_ids:
                by_source = dict(artifacts.get("visual_evidence_by_source") or {})
                for source_id in changed_source_ids:
                    by_source.pop(source_id, None)
                artifacts["visual_evidence_by_source"] = by_source
                artifacts["visual_evidence"] = "\n\n".join(
                    f"[Source: {item.get('title') or key}]\n{item.get('evidence') or ''}"
                    for key, item in by_source.items()
                )
                for key in (
                    "narrative_map", "fusion_segment_plan", "fusion_segment_plan_draft",
                    "fusion_plan_approval", "segment_matches", "finalization", "fusion_script",
                ):
                    artifacts.pop(key, None)
                findings = [
                    item for item in findings
                    if item.get("code") != "source_identity_changed"
                ]
                findings.extend(
                    {
                        "finding_id": f"source-identity-changed-{source_id}",
                        "code": "source_identity_changed",
                        "source_id": source_id,
                        "severity": "blocker",
                        "status": "open",
                        "message": "源视频内容已变化，必须重新运行视觉分析后才能继续。",
                    }
                    for source_id in changed_source_ids
                )
            return self.update(
                project_id,
                source_video_sequence=sources,
                artifact_refs=artifacts,
                review_findings=findings,
                active_version_id="" if changed_source_ids else project.get("active_version_id", ""),
            )

    def stage_readiness(self, project_id: str) -> dict[str, dict[str, Any]]:
        project = self.read(project_id)
        sources = list(project.get("source_video_sequence") or [])
        artifacts = dict(project.get("artifact_refs") or {})
        available_sources = [source for source in sources if source.get("available")]
        identity_changed = [
            source for source in sources if source.get("identity_status") == "changed"
        ]

        def state(*blockers: str) -> dict[str, Any]:
            remaining = [blocker for blocker in blockers if blocker]
            return {"ready": not remaining, "blockers": remaining}

        evidence = state(
            "可用源视频" if not available_sources else "",
            "源视频身份变化，需重新视觉分析" if identity_changed else "",
        )
        narration = state(
            "可用源视频" if not available_sources else "",
            "源视频身份变化，需重新视觉分析" if identity_changed else "",
            "字幕或 ASR" if not any(source.get("subtitle_path") for source in sources) else "",
        )
        matching = state(
            "源视频身份变化，需重新视觉分析" if identity_changed else "",
            "解说词" if not artifacts.get("narration") else "",
            "Fusion Segment Plan" if not artifacts.get("fusion_segment_plan") else "",
            "Plan Approval" if not artifacts.get("fusion_plan_approval") else "",
        )
        review = state("画面匹配结果" if not artifacts.get("finalization") else "")
        output = state(
            "源视频身份变化，需重新视觉分析" if identity_changed else "",
            "活动版本" if not project.get("active_version_id") else "",
            "审核阻断项" if any(
                item.get("severity") == "blocker" and item.get("status", "open") == "open"
                for item in project.get("review_findings") or []
            ) else "",
        )
        return {
            "setup": state(),
            "evidence": evidence,
            "narration": narration,
            "matching": matching,
            "review": review,
            "output": output,
        }

    @_serialized
    def attach_source_visual_evidence(
        self,
        project_id: str,
        *,
        source_id: str,
        evidence: str,
        artifact_path: str,
    ) -> dict[str, Any]:
        with self._lock:
            project = self.read(project_id)
            sources = list(project.get("source_video_sequence") or [])
            source = next(
                (item for item in sources if str(item.get("source_id") or "") == str(source_id)),
                None,
            )
            if source is None:
                raise ValueError("Fusion source video not found")
            path = Path(str(source.get("path") or ""))
            if not path.is_file():
                raise ValueError("Fusion source video is offline")
            observed = self._source_identity(path)
            source["identity"] = observed
            source["observed_identity"] = observed
            source["identity_status"] = "verified"
            source["visual_evidence_status"] = "completed"
            source["visual_evidence_artifact"] = str(artifact_path or "")
            artifacts = dict(project.get("artifact_refs") or {})
            by_source = dict(artifacts.get("visual_evidence_by_source") or {})
            by_source[str(source_id)] = {
                "source_id": str(source_id),
                "title": str(source.get("title") or ""),
                "path": str(artifact_path or ""),
                "source_identity": observed,
                "evidence": str(evidence or ""),
            }
            artifacts["visual_evidence_by_source"] = by_source
            artifacts["visual_evidence"] = "\n\n".join(
                f"[Source: {item.get('title') or key}]\n{item.get('evidence') or ''}"
                for key, item in by_source.items()
            )
            findings = [
                item for item in project.get("review_findings") or []
                if not (
                    item.get("code") == "source_identity_changed"
                    and str(item.get("source_id") or "") == str(source_id)
                )
            ]
            return self.update(
                project_id,
                source_video_sequence=sources,
                artifact_refs=artifacts,
                review_findings=findings,
            )

    @_serialized
    def admit_matching_completion(
        self, project_id: str, *, task_id: str, finalization: dict[str, Any]
    ) -> dict[str, Any]:
        project = self.read(project_id)
        task = next(
            (item for item in project.get("task_refs") or [] if item.get("task_id") == task_id),
            None,
        )
        if task is None or task.get("kind") != "fusion_matching":
            raise ValueError("Fusion Matching Task is not owned by this project")
        input_version_id = str(task.get("input_version_id") or "")
        active_version_id = str(project.get("active_version_id") or "")
        self.update_task_summary(project_id, task_id, status="completed", progress=100)
        if input_version_id != active_version_id:
            project = self.read(project_id)
            stale = list(project.get("stale_task_results") or [])
            stale.append(
                {
                    "task_id": task_id,
                    "kind": "fusion_matching",
                    "input_version_id": input_version_id,
                    "active_version_id": active_version_id,
                    "admission": "stale",
                    "completed_at": _now(),
                }
            )
            project = self.update(project_id, stale_task_results=stale)
            return {"admission": "stale", "project": project}

        artifacts = dict(project.get("artifact_refs") or {})
        artifacts["finalization"] = finalization
        artifacts["fusion_matching_task_id"] = str(task_id)
        if finalization.get("narrative_map"):
            artifacts["narrative_map"] = finalization["narrative_map"]
        if finalization.get("finalized_script"):
            artifacts["fusion_script"] = finalization["finalized_script"]
        findings = self._review_findings(finalization)
        project = self.update(
            project_id,
            artifact_refs=artifacts,
            review_findings=findings,
            active_version_id=str(finalization.get("active_version_id") or active_version_id),
            active_stage="review",
        )
        return {"admission": "active", "project": project}

    @_serialized
    def sync_admitted_matching_state(
        self, project_id: str, *, task_id: str, finalization: dict[str, Any]
    ) -> dict[str, Any]:
        project = self.read(project_id)
        artifacts = dict(project.get("artifact_refs") or {})
        if str(artifacts.get("fusion_matching_task_id") or "") != str(task_id):
            raise ValueError("Fusion Matching Task is not the admitted active result")
        artifacts["finalization"] = finalization
        if finalization.get("narrative_map"):
            artifacts["narrative_map"] = finalization["narrative_map"]
        if finalization.get("finalized_script"):
            artifacts["fusion_script"] = finalization["finalized_script"]
        return self.update(
            project_id,
            artifact_refs=artifacts,
            review_findings=self._review_findings(finalization),
            active_version_id=str(
                finalization.get("active_version_id") or project.get("active_version_id") or ""
            ),
        )

    @staticmethod
    def _review_findings(finalization: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        preflight = finalization.get("preflight") or {}
        for severity, entries in (
            ("blocker", preflight.get("blockers") or []),
            ("warning", preflight.get("warnings") or []),
            ("warning", finalization.get("evidence_conflicts") or []),
            ("suggestion", finalization.get("narrative_quality_findings") or []),
        ):
            for index, finding in enumerate(entries):
                if not isinstance(finding, dict):
                    continue
                projected = dict(finding)
                projected.setdefault(
                    "finding_id",
                    f"{projected.get('code') or 'finding'}-{projected.get('segment_id') or index}",
                )
                projected.setdefault("severity", severity)
                projected.setdefault("status", "open")
                findings.append(projected)
        return findings

    def permanent_delete_plan(self, project_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        managed = [
            source.get("path")
            for source in project.get("source_video_sequence") or []
            if source.get("kind") == "managed_asset"
        ]
        referenced = [
            source.get("path")
            for source in project.get("source_video_sequence") or []
            if source.get("kind") == "local_reference"
        ]
        return {
            "project_id": project_id,
            "managed_assets_to_remove": managed,
            "referenced_local_sources_preserved": referenced,
            "render_outcomes_to_remove": list(project.get("render_outcomes") or []),
        }

    @_serialized
    def permanent_delete(self, project_id: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ValueError("permanent Fusion Project deletion requires confirmation")
        project = self.read(project_id)
        if not project.get("trash_state"):
            raise ValueError("Fusion Project must be trashed before permanent deletion")
        shutil.rmtree(self._project_directory(project_id))

    @_serialized
    def admit_task_result(
        self,
        project_id: str,
        *,
        task_id: str,
        input_version_id: str,
        artifact_ref: str,
    ) -> dict[str, Any]:
        project = self.read(project_id)
        result = {
            "task_id": task_id,
            "input_version_id": input_version_id,
            "artifact_ref": artifact_ref,
            "completed_at": _now(),
        }
        if str(project.get("active_version_id") or "") != str(input_version_id or ""):
            result["admission"] = "stale"
            stale = list(project.get("stale_task_results") or [])
            stale.append(result)
            self.update(project_id, stale_task_results=stale)
        else:
            result["admission"] = "active"
            artifacts = dict(project.get("artifact_refs") or {})
            artifacts[task_id] = artifact_ref
            self.update(project_id, artifact_refs=artifacts)
        return result

    @_serialized
    def attach_task(
        self,
        project_id: str,
        *,
        task_id: str,
        kind: str,
        source_id: str = "",
        input_version_id: str = "",
        status: str = "queued",
    ) -> dict[str, Any]:
        project = self.read(project_id)
        tasks = [item for item in project.get("task_refs") or [] if item.get("task_id") != task_id]
        tasks.append(
            {
                "task_id": str(task_id),
                "kind": str(kind),
                "source_id": str(source_id),
                "input_version_id": str(input_version_id),
                "status": str(status),
                "updated_at": _now(),
            }
        )
        return self.update(project_id, task_refs=tasks)

    @_serialized
    def reserve_task(
        self,
        project_id: str,
        *,
        task_id: str,
        kind: str,
        source_id: str = "",
        input_version_id: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        """Atomically enforce concurrency policy and reserve a task slot."""
        projection = self.task_start_projection(
            project_id, kind=kind, source_id=source_id
        )
        if not projection["allowed"]:
            raise ValueError(str(projection.get("reason") or "Task start is blocked"))
        project = self.attach_task(
            project_id, task_id=task_id, kind=kind, source_id=source_id,
            input_version_id=input_version_id, status="queued",
        )
        return self.update_task_summary(
            project_id, task_id, run_id=str(run_id or uuid4().hex),
            message="任务已预留", revision_at_start=project.get("revision"),
        )

    @_serialized
    def bind_reserved_task(
        self, project_id: str, *, reservation_id: str, task_id: str
    ) -> dict[str, Any]:
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        reserved = next(
            (item for item in tasks if item.get("task_id") == reservation_id), None
        )
        if reserved is None or reserved.get("status") != "queued":
            raise ValueError("Fusion Task reservation is unavailable")
        if any(item.get("task_id") == task_id for item in tasks):
            raise ValueError("Fusion Task id is already attached")
        reserved["task_id"] = str(task_id)
        reserved["message"] = "任务已启动"
        reserved["updated_at"] = _now()
        return self.update(project_id, task_refs=tasks)

    @_serialized
    def update_task_summary(self, project_id: str, task_id: str, **changes: Any) -> dict[str, Any]:
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        matched = False
        for task in tasks:
            if task.get("task_id") == task_id:
                task.update(changes)
                task["updated_at"] = _now()
                matched = True
        if not matched:
            raise ValueError("Fusion Project task not found")
        return self.update(project_id, task_refs=tasks)

    @_serialized
    def commit_task_artifacts(
        self,
        project_id: str,
        *,
        task_id: str,
        run_id: str,
        artifact_changes: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        """Atomically admit a run's artifacts and mark that same run complete."""
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        task = next((item for item in tasks if item.get("task_id") == task_id), None)
        if (
            task is None
            or str(task.get("run_id") or "") != str(run_id)
            or task.get("status") not in ACTIVE_TASK_STATUSES
        ):
            raise ValueError("Fusion Task run is no longer current")
        artifacts = dict(project.get("artifact_refs") or {})
        artifacts.update(json.loads(json.dumps(artifact_changes, ensure_ascii=False)))
        task.update(
            status="completed", progress=100, message=str(message or "任务已完成"),
            updated_at=_now(),
        )
        return self.update(project_id, artifact_refs=artifacts, task_refs=tasks)

    @_serialized
    def finish_task_run(
        self,
        project_id: str,
        *,
        task_id: str,
        run_id: str,
        status: str,
        message: str,
        artifact_changes: dict[str, Any] | None = None,
        **task_changes: Any,
    ) -> dict[str, Any]:
        """Atomically finish only the still-current run, including diagnostics."""
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        task = next((item for item in tasks if item.get("task_id") == task_id), None)
        if (
            task is None
            or str(task.get("run_id") or "") != str(run_id)
            or task.get("status") not in ACTIVE_TASK_STATUSES
        ):
            raise ValueError("Fusion Task run is no longer current")
        task.update(task_changes)
        task.update(status=str(status), message=str(message), updated_at=_now())
        changes: dict[str, Any] = {"task_refs": tasks}
        if artifact_changes:
            artifacts = dict(project.get("artifact_refs") or {})
            artifacts.update(json.loads(json.dumps(artifact_changes, ensure_ascii=False)))
            changes["artifact_refs"] = artifacts
        return self.update(project_id, **changes)

    @_serialized
    def commit_stale_task_artifact(
        self,
        project_id: str,
        *,
        task_id: str,
        run_id: str,
        artifact_ref: str,
        message: str,
    ) -> dict[str, Any]:
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        task = next((item for item in tasks if item.get("task_id") == task_id), None)
        if (
            task is None
            or str(task.get("run_id") or "") != str(run_id)
            or task.get("status") not in ACTIVE_TASK_STATUSES
        ):
            raise ValueError("Fusion Task run is no longer current")
        input_version = str(task.get("input_version_id") or "")
        active_version = str(project.get("active_version_id") or "")
        if input_version == active_version:
            raise ValueError("Fusion Task result is not stale")
        stale = list(project.get("stale_task_results") or [])
        stale.append(
            {
                "task_id": task_id, "kind": str(task.get("kind") or ""),
                "input_version_id": input_version, "active_version_id": active_version,
                "artifact_ref": str(artifact_ref), "admission": "stale",
                "completed_at": _now(),
            }
        )
        task.update(status="completed", progress=100, message=str(message), updated_at=_now())
        return self.update(project_id, task_refs=tasks, stale_task_results=stale)

    @_serialized
    def cancel_task_run(
        self, project_id: str, *, task_id: str, run_id: str
    ) -> dict[str, Any]:
        """Atomically cancel only an active run; completed output remains completed."""
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        task = next((item for item in tasks if item.get("task_id") == task_id), None)
        if (
            task is None
            or str(task.get("run_id") or "") != str(run_id)
            or task.get("status") not in ACTIVE_TASK_STATUSES
        ):
            raise ValueError("Fusion Task run is no longer cancellable")
        task.update(
            status="cancelled", message="已取消接收该模型任务的结果",
            recoverable=True, updated_at=_now(),
        )
        return self.update(project_id, task_refs=tasks)

    def task_start_projection(
        self, project_id: str, *, kind: str, source_id: str = ""
    ) -> dict[str, Any]:
        project = self.read(project_id)
        active = [
            task for task in project.get("task_refs") or []
            if task.get("status") in ACTIVE_TASK_STATUSES
        ]
        if kind == "visual_analysis":
            conflict = next(
                (
                    task for task in active
                    if task.get("kind") == "visual_analysis"
                    and str(task.get("source_id") or "") == str(source_id or "")
                ),
                None,
            )
            reason = "该素材已有视觉分析任务正在运行" if conflict else ""
        elif kind in CONTENT_MUTATING_TASK_KINDS:
            conflict = next(
                (task for task in active if task.get("kind") in CONTENT_MUTATING_TASK_KINDS),
                None,
            )
            reason = "项目已有内容变更任务正在运行" if conflict else ""
        else:
            conflict = None
            reason = ""
        return {"allowed": conflict is None, "reason": reason}

    @_serialized
    def reconcile_unfinished_tasks(self, project_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        tasks = list(project.get("task_refs") or [])
        changed = False
        for task in tasks:
            if task.get("status") in ACTIVE_TASK_STATUSES:
                task["status"] = "interrupted"
                task["recoverable"] = True
                task["message"] = "应用重启后任务已暂停，可继续或查看诊断"
                task["updated_at"] = _now()
                changed = True
        return self.update(project_id, task_refs=tasks) if changed else project

    @_serialized
    def reconcile_for_runtime(self, project_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        if project.get("last_runtime_id") == RUNTIME_ID:
            return project
        project = self.reconcile_unfinished_tasks(project_id)
        return self.update(project_id, last_runtime_id=RUNTIME_ID)

    def task_diagnostic_projection(self, project_id: str, task_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        task = next(
            (item for item in project.get("task_refs") or [] if item.get("task_id") == task_id),
            None,
        )
        if task is None:
            raise ValueError("Fusion Project task not found")
        return {
            "kind": str(task.get("kind") or ""),
            "status": str(task.get("status") or ""),
            "progress": task.get("progress"),
            "message": str(task.get("message") or "")[:1000],
            "error_message": str(task.get("error_message") or "")[:1000],
            "failure_category": str(task.get("failure_category") or ""),
            "recoverable": bool(task.get("recoverable"))
            or task.get("status") in {"failed", "interrupted", "cancelled"},
        }

    @_serialized
    def save_content_draft(
        self, project_id: str, *, kind: str, content: Any
    ) -> dict[str, Any]:
        project = self.read(project_id)
        drafts = [
            item
            for item in project.get("content_drafts") or []
            if not (item.get("kind") == kind and item.get("status") == "draft")
        ]
        draft = {
            "draft_id": uuid4().hex,
            "kind": str(kind),
            "content": content,
            "base_version_id": str(project.get("active_version_id") or ""),
            "status": "draft",
            "updated_at": _now(),
        }
        drafts.append(draft)
        self.update(project_id, content_drafts=drafts)
        return draft

    def preview_draft_impact(self, project_id: str, draft_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        draft = next(
            (item for item in project.get("content_drafts") or [] if item.get("draft_id") == draft_id),
            None,
        )
        if draft is None:
            raise ValueError("Fusion Content Draft not found")
        dependencies = {
            "narration": ["narrative_map", "fusion_segment_plan", "segment_matches", "finalization", "preflight"],
            "narrative_map": ["fusion_segment_plan", "segment_matches", "finalization", "preflight"],
            "fusion_script": ["finalization", "preflight"],
        }
        artifacts = project.get("artifact_refs") or {}
        invalidated = [
            key for key in dependencies.get(str(draft.get("kind")), []) if key in artifacts
        ]
        return {
            "draft_id": draft_id,
            "kind": draft.get("kind"),
            "invalidated_artifacts": invalidated,
        }

    @_serialized
    def apply_content_draft(
        self, project_id: str, draft_id: str, *, impact_confirmed: bool
    ) -> dict[str, Any]:
        if not impact_confirmed:
            raise ValueError("Content Draft impact confirmation is required")
        project = self.read(project_id)
        drafts = list(project.get("content_drafts") or [])
        draft = next((item for item in drafts if item.get("draft_id") == draft_id), None)
        if draft is None or draft.get("status") != "draft":
            raise ValueError("active Fusion Content Draft not found")
        impact = self.preview_draft_impact(project_id, draft_id)
        artifacts = dict(project.get("artifact_refs") or {})
        for key in impact["invalidated_artifacts"]:
            artifacts.pop(key, None)
        artifacts[str(draft["kind"])] = draft.get("content")
        version_id = uuid4().hex
        versions = list(project.get("versions") or [])
        versions.append(
            {
                "version_id": version_id,
                "kind": f"applied_{draft['kind']}_draft",
                "created_at": _now(),
                "artifact_refs": artifacts,
                "invalidated_artifacts": impact["invalidated_artifacts"],
            }
        )
        for item in drafts:
            if item.get("draft_id") == draft_id:
                item["status"] = "applied"
                item["applied_version_id"] = version_id
        return self.update(
            project_id,
            artifact_refs=artifacts,
            content_drafts=drafts,
            versions=versions,
            active_version_id=version_id,
        )

    @_serialized
    def record_review_decision(
        self, project_id: str, *, finding_id: str, action: str, reason: str = ""
    ) -> dict[str, Any]:
        project = self.read(project_id)
        decision = {
            "decision_id": uuid4().hex,
            "finding_id": str(finding_id),
            "action": str(action),
            "reason": str(reason),
            "status": "active",
            "created_at": _now(),
        }
        decisions = list(project.get("review_decisions") or [])
        decisions.append(decision)
        self.update(project_id, review_decisions=decisions)
        return decision

    @_serialized
    def undo_review_decision(self, project_id: str, decision_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        decisions = list(project.get("review_decisions") or [])
        matched = False
        for decision in decisions:
            if decision.get("decision_id") == decision_id:
                decision["status"] = "undone"
                decision["undone_at"] = _now()
                matched = True
        if not matched:
            raise ValueError("Fusion review decision not found")
        return self.update(project_id, review_decisions=decisions)

    @_serialized
    def add_render_outcome(
        self,
        project_id: str,
        *,
        media_path: str,
        render_authorization: dict[str, Any],
        render_task_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            project = self.read(project_id)
            authorization_id = str(
                (render_authorization or {}).get("authorization_id") or ""
            )
            authorization = next(
                (
                    json.loads(json.dumps(item, ensure_ascii=False))
                    for item in project.get("render_authorizations") or []
                    if str(item.get("authorization_id") or "") == authorization_id
                ),
                None,
            )
            if authorization is None:
                raise ValueError("Render Outcome requires a frozen authorization")
            task = next(
                (
                    item for item in project.get("task_refs") or []
                    if item.get("task_id") == render_task_id
                ),
                None,
            )
            if render_task_id and task is None:
                raise ValueError("Render Task is not owned by this project")
            authorized_version = str(authorization.get("version_id") or "")
            if task and str(task.get("input_version_id") or "") != authorized_version:
                raise ValueError("Render Task input version does not match authorization")
            artifacts = dict(project.get("artifact_refs") or {})
            current_preflight = dict(
                (artifacts.get("finalization") or {}).get("preflight") or {}
            )
            current_source_fingerprints = {
                str(source.get("source_id") or ""): str(
                    (self._source_identity(Path(str(source.get("path") or "")))
                     if Path(str(source.get("path") or "")).is_file() else {}).get(
                        "fingerprint"
                    ) or ""
                )
                for source in project.get("source_video_sequence") or []
            }
            authorized_source_fingerprints = {
                str(item.get("source_id") or ""): str(item.get("fingerprint") or "")
                for item in authorization.get("source_identities") or []
            }
            admission = "active" if (
                authorized_version == str(project.get("active_version_id") or "")
                and authorization.get("preflight_sha256")
                == self._json_fingerprint(current_preflight)
                and current_source_fingerprints == authorized_source_fingerprints
            ) else "stale"
            outcome = {
                "outcome_id": uuid4().hex,
                "media_path": str(media_path),
                "version_id": authorized_version,
                "admission": admission,
                "render_authorization": authorization,
                "configuration_snapshot": authorization.get("configuration_snapshot") or {},
                "render_task_id": str(render_task_id or ""),
                "created_at": _now(),
            }
            outcomes = list(project.get("render_outcomes") or [])
            outcomes.append(outcome)
            changes: dict[str, Any] = {"render_outcomes": outcomes}
            if admission == "stale":
                stale = list(project.get("stale_task_results") or [])
                stale.append(
                    {
                        "task_id": str(render_task_id or ""),
                        "kind": "render",
                        "input_version_id": authorized_version,
                        "active_version_id": str(project.get("active_version_id") or ""),
                        "admission": "stale",
                        "completed_at": _now(),
                    }
                )
                changes["stale_task_results"] = stale
            updated = self.update(project_id, **changes)
            return {**outcome, "project": updated}

    @_serialized
    def create_render_authorization(
        self,
        project_id: str,
        *,
        configuration_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Freeze the exact approved inputs which a render is allowed to consume."""
        with self._lock:
            project = self.read(project_id)
            active_version = str(project.get("active_version_id") or "")
            artifacts = dict(project.get("artifact_refs") or {})
            finalization = dict(artifacts.get("finalization") or {})
            preflight = dict(finalization.get("preflight") or {})
            if not active_version or str(finalization.get("active_version_id") or "") != active_version:
                raise ValueError("Render requires the active finalized version")
            if preflight.get("blockers"):
                raise ValueError("Render Preflight blockers must be resolved")
            if preflight.get("warnings") and not str(
                preflight.get("warning_override_reason") or ""
            ).strip():
                raise ValueError("Render Preflight warnings require an override reason")
            if not preflight.get("renderable") or not finalization.get("renderable"):
                raise ValueError("Render Preflight is not renderable")
            sources = list(project.get("source_video_sequence") or [])
            if not sources or any(
                not source.get("available")
                or source.get("identity_status") == "changed"
                or not (source.get("identity") or {}).get("fingerprint")
                for source in sources
            ):
                raise ValueError("Render source identity is offline or unverified")
            observed_identities: list[dict[str, str]] = []
            for source in sources:
                path = Path(str(source.get("path") or ""))
                observed = self._source_identity(path)
                accepted = dict(source.get("identity") or {})
                if observed.get("content_sha256") != accepted.get("content_sha256"):
                    raise ValueError(
                        "Render source content changed after evidence approval"
                    )
                observed_identities.append(
                    {
                        "source_id": str(source.get("source_id") or ""),
                        "fingerprint": str(observed.get("fingerprint") or ""),
                    }
                )
            frozen_preflight = json.loads(json.dumps(preflight, ensure_ascii=False))
            authorization = {
                "authorization_id": uuid4().hex,
                "version_id": active_version,
                "preflight": frozen_preflight,
                "preflight_sha256": self._json_fingerprint(frozen_preflight),
                "configuration_snapshot": json.loads(
                    json.dumps(configuration_snapshot or {}, ensure_ascii=False)
                ),
                "source_identities": observed_identities,
                "created_at": _now(),
            }
            authorizations = list(project.get("render_authorizations") or [])
            authorizations.append(authorization)
            self.update(project_id, render_authorizations=authorizations)
            return authorization

    @_serialized
    def override_render_warnings(self, project_id: str, *, reason: str) -> dict[str, Any]:
        reason = str(reason or "").strip()
        if not reason:
            raise ValueError("Render Preflight warning override requires a reason")
        project = self.read(project_id)
        artifacts = dict(project.get("artifact_refs") or {})
        finalization = dict(artifacts.get("finalization") or {})
        preflight = dict(finalization.get("preflight") or {})
        if preflight.get("blockers"):
            raise ValueError("Render Preflight blockers cannot be overridden")
        if not preflight.get("warnings"):
            raise ValueError("Render Preflight has no warnings to override")
        preflight["warning_override_reason"] = reason
        preflight["renderable"] = True
        finalization["preflight"] = preflight
        finalization["renderable"] = True
        versions = list(finalization.get("version_history") or [])
        version_id = f"preflight-override-{len(versions) + 1}"
        finalization["active_version_id"] = version_id
        versions.append(
            {
                "version_id": version_id,
                "kind": "preflight_warning_override",
                "created_at": _now(),
                "snapshot": json.loads(json.dumps(finalization, ensure_ascii=False)),
            }
        )
        finalization["version_history"] = versions
        artifacts["finalization"] = finalization
        decisions = list(project.get("review_decisions") or [])
        decisions.append(
            {
                "decision_id": uuid4().hex,
                "kind": "preflight",
                "action": "warning_overridden",
                "reason": reason,
                "status": "active",
                "created_at": _now(),
            }
        )
        return self.update(
            project_id,
            artifact_refs=artifacts,
            active_version_id=version_id,
            review_decisions=decisions,
        )

    def save_json_artifact(
        self, project_id: str, *, name: str, payload: Any
    ) -> str:
        safe_name = Path(str(name or "artifact.json")).name
        if not safe_name.endswith(".json"):
            safe_name += ".json"
        directory = self._project_directory(project_id) / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_name
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return str(target)

    @_serialized
    def migrate_legacy_project(
        self,
        *,
        name: str,
        source_paths: list[str],
        finalized_script: list[dict[str, Any]],
        preflight: dict[str, Any],
        project_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self.create(name or "Migrated Fusion Project")
        for source_path in source_paths:
            if str(source_path or "").strip():
                self.add_local_reference(project["project_id"], path=str(source_path).strip())
        version_id = f"migrated-{uuid4().hex}"
        imported_preflight = dict(preflight or {})
        migration_preflight = {
            "blockers": [
                {
                    "code": "legacy_import_requires_revalidation",
                    "message": "旧项目脚本必须重新绑定来源并运行当前版本 Preflight。",
                    "severity": "blocker",
                }
            ],
            "warnings": [],
            "renderable": False,
        }
        finalization = {
            "finalized_script": list(finalized_script or []),
            "preflight": migration_preflight,
            "imported_preflight": imported_preflight,
            "renderable": False,
            "active_version_id": version_id,
            "version_history": [
                {
                    "version_id": version_id,
                    "kind": "legacy_fusion_import",
                    "created_at": _now(),
                    "snapshot": {
                        "finalized_script": list(finalized_script or []),
                        "preflight": migration_preflight,
                        "imported_preflight": imported_preflight,
                        "renderable": False,
                        "active_version_id": version_id,
                    },
                }
            ],
        }
        current = self.read(project["project_id"])
        settings = dict(current.get("project_settings") or {})
        settings.update(project_settings or {})
        return self.update(
            project["project_id"],
            project_settings=settings,
            artifact_refs={"finalization": finalization, "fusion_script": list(finalized_script or [])},
            active_version_id=version_id,
            active_stage="review",
            migration_state={
                "kind": "legacy_fusion_import",
                "status": "requires_revalidation",
                "migrated_at": _now(),
            },
            review_findings=self._review_findings(finalization),
        )

    @_serialized
    def revalidate_legacy_project(
        self, project_id: str, *, source_durations: dict[str, float]
    ) -> dict[str, Any]:
        """Bind an imported script to current sources and run current safety checks."""
        project = self.read(project_id)
        migration = dict(project.get("migration_state") or {})
        if migration.get("kind") != "legacy_fusion_import":
            raise ValueError("Fusion Project is not a legacy import")
        sources = list(project.get("source_video_sequence") or [])
        if not sources or any(not source.get("available") for source in sources):
            raise ValueError("Legacy migration requires every source video to be online")
        for source in sources:
            path = Path(str(source.get("path") or ""))
            observed = self._source_identity(path)
            accepted = dict(source.get("identity") or {})
            if accepted and observed.get("content_sha256") != accepted.get("content_sha256"):
                raise ValueError("Legacy migration source content changed; reconnect and reanalyze")
            source["observed_identity"] = observed
            source["identity_status"] = "verified"
        source_names = {Path(str(source.get("path") or "")).name for source in sources}
        finalization = dict((project.get("artifact_refs") or {}).get("finalization") or {})
        script = [dict(item) for item in finalization.get("finalized_script") or []]
        if not script:
            raise ValueError("Legacy migration has no script to validate")
        for item in script:
            source_name = str(item.get("video_name") or "")
            if not source_name and len(source_names) == 1:
                item["video_name"] = next(iter(source_names))
                source_name = str(item["video_name"])
            if source_name not in source_names:
                raise ValueError(
                    f"Legacy script source is not bound to this project: {source_name or '<missing>'}"
                )
        from app.services.fusion_preflight import build_render_preflight
        from app.services.fusion_script_finalizer import FusionScriptFinalizer

        FusionScriptFinalizer().validate_authored_timeline(script, source_durations)
        preflight = build_render_preflight(
            continuity_report={"is_renderable": True},
            evidence_conflicts=list(finalization.get("evidence_conflicts") or []),
            segment_matches=[
                {"segment_id": str(item.get("segment_id") or item.get("_id") or index), "status": "completed"}
                for index, item in enumerate(script, start=1)
            ],
        ).to_dict()
        version_id = f"migration-revalidated-{uuid4().hex}"
        finalization.update(
            finalized_script=script,
            preflight=preflight,
            renderable=bool(preflight.get("renderable")),
            active_version_id=version_id,
        )
        versions = list(finalization.get("version_history") or [])
        versions.append(
            {
                "version_id": version_id,
                "kind": "legacy_import_revalidated",
                "created_at": _now(),
                "snapshot": json.loads(json.dumps(finalization, ensure_ascii=False)),
            }
        )
        finalization["version_history"] = versions
        artifacts = dict(project.get("artifact_refs") or {})
        artifacts["finalization"] = finalization
        artifacts["fusion_script"] = script
        migration.update(status="revalidated", revalidated_at=_now())
        return self.update(
            project_id, source_video_sequence=sources, artifact_refs=artifacts,
            active_version_id=version_id,
            migration_state=migration,
            review_findings=self._review_findings(finalization),
        )

    @_serialized
    def _append_source(self, project_id: str, source: dict[str, Any]) -> None:
        project = self.read(project_id)
        sources = list(project.get("source_video_sequence") or [])
        source["sequence"] = len(sources) + 1
        sources.append(source)
        self.update(project_id, source_video_sequence=sources)

    def _source_record(
        self, *, kind: str, path: Path, subtitle_path: str
    ) -> dict[str, Any]:
        available = path.is_file()
        identity = self._source_identity(path) if available else {}
        return {
            "source_id": uuid4().hex,
            "kind": kind,
            "path": str(path),
            "title": path.name,
            "available": available,
            "identity": identity,
            "observed_identity": identity,
            "identity_status": "verified" if available else "offline",
            "subtitle_status": "available" if subtitle_path and Path(subtitle_path).is_file() else "missing",
            "subtitle_path": str(subtitle_path or ""),
            "visual_evidence_status": "not_started",
        }

    @staticmethod
    def _source_identity(path: Path) -> dict[str, Any]:
        stat = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        content_sha256 = digest.hexdigest()
        payload = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{content_sha256}"
        return {
            "path": str(path.resolve()),
            "size": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
            "content_sha256": content_sha256,
            "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def _json_fingerprint(payload: Any) -> str:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _project_directory(self, project_id: str) -> Path:
        if not str(project_id).isalnum():
            raise ValueError("invalid Fusion Project id")
        return self._directory / str(project_id)

    def _record_path(self, project_id: str) -> Path:
        return self._project_directory(project_id) / "project.json"

    def _write(self, project: dict[str, Any]) -> None:
        path = self._record_path(str(project["project_id"]))
        temporary = path.with_name(f"project.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(project, handle, ensure_ascii=False, indent=2)
            for retry in range(5):
                try:
                    temporary.replace(path)
                    return
                except PermissionError:
                    if retry == 4:
                        raise
                    time.sleep(0.01)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def project_projection(project: dict[str, Any]) -> dict[str, Any]:
    """Create the one creator-facing status and next-action projection."""
    tasks = list(project.get("task_refs") or [])
    findings = list(project.get("review_findings") or [])
    open_blockers = [
        item
        for item in findings
        if item.get("severity") == "blocker" and item.get("status", "open") == "open"
    ]
    open_reviews = [item for item in findings if item.get("status", "open") == "open"]
    active_version_id = str(project.get("active_version_id") or "")
    active_outcomes = [
        outcome for outcome in project.get("render_outcomes") or []
        if outcome.get("admission", "active") == "active"
        and str(outcome.get("version_id") or "") == active_version_id
    ]
    finalization = dict((project.get("artifact_refs") or {}).get("finalization") or {})
    preflight = dict(finalization.get("preflight") or {})
    render_ready = bool(
        active_version_id
        and str(finalization.get("active_version_id") or "") == active_version_id
        and finalization.get("renderable")
        and preflight.get("renderable")
        and not preflight.get("blockers")
        and (
            not preflight.get("warnings")
            or str(preflight.get("warning_override_reason") or "").strip()
        )
    )
    if project.get("trash_state"):
        status, next_action = "trashed", "恢复项目"
    elif project.get("archive_state"):
        status, next_action = "archived", "取消归档"
    elif open_blockers:
        status, next_action = "blocked", "解决审核阻断项"
    elif any(task.get("status") in {"queued", "running", "rendering"} for task in tasks):
        status, next_action = "running", "查看运行任务"
    elif any(task.get("status") == "interrupted" for task in tasks):
        status, next_action = "interrupted", "继续中断任务"
    elif any(task.get("status") == "waiting_for_review" for task in tasks):
        status, next_action = "waiting_for_review", "检查可恢复的模型输出"
    elif (
        project.get("source_video_sequence")
        and not any(source.get("available") for source in project.get("source_video_sequence") or [])
    ):
        status, next_action = "source_offline", "重新连接源视频"
    elif project.get("stale_task_results"):
        status, next_action = "stale_result", "检查过期任务结果"
    elif open_reviews:
        status, next_action = "waiting_for_review", "继续审核"
    elif active_outcomes:
        status, next_action = "completed", "打开最新成片"
    elif render_ready:
        status, next_action = "ready_to_render", "运行渲染前检查"
    elif active_version_id:
        status, next_action = "waiting_for_review", "完成渲染前审核"
    else:
        status, next_action = "draft", "继续项目设置"
    return {
        "project_id": project.get("project_id"),
        "name": project.get("name"),
        "status": status,
        "active_stage": project.get("active_stage") or "setup",
        "updated_at": project.get("updated_at"),
        "blocker_count": len(open_blockers),
        "review_count": len(open_reviews),
        "running_task_count": sum(
            task.get("status") in {"queued", "running", "rendering"} for task in tasks
        ),
        "next_action": next_action,
    }

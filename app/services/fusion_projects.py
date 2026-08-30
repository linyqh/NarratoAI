"""Durable ownership and projection for Film Vision Fusion projects."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FusionProjectStore:
    """Atomic local repository for project records and managed project data."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def create(self, name: str = "Untitled Fusion Project") -> dict[str, Any]:
        project_id = uuid4().hex
        now = _now()
        project = {
            "schema_version": PROJECT_SCHEMA_VERSION,
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
            "content_drafts": [],
            "versions": [],
            "stale_task_results": [],
            "trash_state": None,
            "archive_state": None,
            "last_runtime_id": RUNTIME_ID,
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

    def update(self, project_id: str, **changes: Any) -> dict[str, Any]:
        project = self.read(project_id)
        if "project_id" in changes or "schema_version" in changes:
            raise ValueError("Fusion Project identity fields are immutable")
        project.update(changes)
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

    def refresh_source_availability(self, project_id: str) -> dict[str, Any]:
        project = self.read(project_id)
        sources = list(project.get("source_video_sequence") or [])
        for source in sources:
            path = Path(str(source.get("path") or ""))
            source["available"] = path.is_file()
            source["identity"] = self._source_identity(path) if path.is_file() else {}
        return self.update(project_id, source_video_sequence=sources)

    def stage_readiness(self, project_id: str) -> dict[str, dict[str, Any]]:
        project = self.read(project_id)
        sources = list(project.get("source_video_sequence") or [])
        artifacts = dict(project.get("artifact_refs") or {})
        available_sources = [source for source in sources if source.get("available")]

        def state(*blockers: str) -> dict[str, Any]:
            remaining = [blocker for blocker in blockers if blocker]
            return {"ready": not remaining, "blockers": remaining}

        evidence = state("可用源视频" if not available_sources else "")
        narration = state(
            "可用源视频" if not available_sources else "",
            "字幕或 ASR" if not any(source.get("subtitle_path") for source in sources) else "",
        )
        matching = state(
            "解说词" if not artifacts.get("narration") else "",
            "Fusion Segment Plan" if not artifacts.get("fusion_segment_plan") else "",
            "Plan Approval" if not artifacts.get("fusion_plan_approval") else "",
        )
        review = state("画面匹配结果" if not artifacts.get("finalization") else "")
        output = state(
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

    def attach_source_visual_evidence(
        self,
        project_id: str,
        *,
        source_id: str,
        evidence: str,
        artifact_path: str,
    ) -> dict[str, Any]:
        project = self.read(project_id)
        sources = list(project.get("source_video_sequence") or [])
        source = next(
            (item for item in sources if str(item.get("source_id") or "") == str(source_id)),
            None,
        )
        if source is None:
            raise ValueError("Fusion source video not found")
        source["visual_evidence_status"] = "completed"
        source["visual_evidence_artifact"] = str(artifact_path or "")
        artifacts = dict(project.get("artifact_refs") or {})
        by_source = dict(artifacts.get("visual_evidence_by_source") or {})
        by_source[str(source_id)] = {
            "source_id": str(source_id),
            "title": str(source.get("title") or ""),
            "path": str(artifact_path or ""),
            "evidence": str(evidence or ""),
        }
        artifacts["visual_evidence_by_source"] = by_source
        artifacts["visual_evidence"] = "\n\n".join(
            f"[Source: {item.get('title') or key}]\n{item.get('evidence') or ''}"
            for key, item in by_source.items()
        )
        return self.update(
            project_id, source_video_sequence=sources, artifact_refs=artifacts
        )

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

    def permanent_delete(self, project_id: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise ValueError("permanent Fusion Project deletion requires confirmation")
        project = self.read(project_id)
        if not project.get("trash_state"):
            raise ValueError("Fusion Project must be trashed before permanent deletion")
        shutil.rmtree(self._project_directory(project_id))

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

    def add_render_outcome(
        self, project_id: str, *, media_path: str, preflight: dict[str, Any]
    ) -> dict[str, Any]:
        project = self.read(project_id)
        blockers = list(preflight.get("blockers") or [])
        if blockers:
            raise ValueError("Render Preflight blockers must be resolved")
        if not project.get("active_version_id"):
            raise ValueError("Render Outcome requires an active version")
        outcome = {
            "outcome_id": uuid4().hex,
            "media_path": str(media_path),
            "version_id": project["active_version_id"],
            "preflight": preflight,
            "created_at": _now(),
        }
        outcomes = list(project.get("render_outcomes") or [])
        outcomes.append(outcome)
        updated = self.update(project_id, render_outcomes=outcomes)
        return {**outcome, "project": updated}

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
        return {
            "source_id": uuid4().hex,
            "kind": kind,
            "path": str(path),
            "title": path.name,
            "available": available,
            "identity": self._source_identity(path) if available else {},
            "subtitle_status": "available" if subtitle_path and Path(subtitle_path).is_file() else "missing",
            "subtitle_path": str(subtitle_path or ""),
            "visual_evidence_status": "not_started",
        }

    @staticmethod
    def _source_identity(path: Path) -> dict[str, Any]:
        stat = path.stat()
        payload = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        return {
            "path": str(path.resolve()),
            "size": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
            "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }

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
    if project.get("trash_state"):
        status, next_action = "trashed", "Restore project"
    elif project.get("archive_state"):
        status, next_action = "archived", "Unarchive project"
    elif open_blockers:
        status, next_action = "blocked", "Resolve review blocker"
    elif any(task.get("status") in {"queued", "running", "rendering"} for task in tasks):
        status, next_action = "running", "View running task"
    elif open_reviews:
        status, next_action = "waiting_for_review", "Continue review"
    elif project.get("render_outcomes"):
        status, next_action = "completed", "Open latest render"
    elif project.get("active_version_id"):
        status, next_action = "ready_to_render", "Run Render Preflight"
    else:
        status, next_action = "draft", "Continue setup"
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

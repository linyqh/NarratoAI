#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : 短剧解说脚本生成
@Author : 小林同学
@Date   : 2025/5/10 下午10:26 
'''
import os
import json
import hashlib
import time
import traceback
import html
from threading import RLock
from dataclasses import asdict
from pathlib import Path
import streamlit as st
from loguru import logger

from app.config import config
from app.services.SDE.short_drama_explanation import (
    analyze_subtitle,
    generate_narration_copy as generate_narration_copy_legacy,
    match_narration_copy_to_script as match_narration_copy_to_script_legacy,
)
from app.services.subtitle_text import read_subtitle_text
from app.services.fusion_script_finalizer import FusionScriptFinalizer
from app.services.fusion_preflight import build_render_preflight
from app.services.fusion_plan_attempts import (
    FusionPlanAttemptStore,
    FusionPlanRecoveryRequired,
)
from app.services.narrative_map import (
    build_narrative_map,
    evaluate_narrative_quality,
    review_narrative_map,
)
from app.services.fusion_script_pipeline import (
    FusionScriptPipeline,
    call_fusion_request_with_retry,
)
from app.services.fusion_matching_workflow import (
    FusionMatchingInput,
    FusionMatchingSnapshot,
    FusionMatchingWorkflow,
)
from app.services.documentary.local_analysis_tasks import LocalAnalysisTaskRunner, LocalAnalysisTaskStore
from app.services.fusion_models import (
    CandidateRejection,
    EvidenceConflict,
    FinalizationRequest,
    HighlightCandidateIntake,
)
from app.services.documentary.frame_analysis_models import HighlightCandidate, TimeRange
from app.utils.video_processor import VideoProcessor
from app.utils import utils
from app.services.short_drama_narration_validation import (
    normalize_script_video_sources,
)
from app.services.tavily_search import TavilySearchError, format_search_context, search_story_context
# 导入新的LLM服务模块 - 确保提供商被注册
import app.services.llm  # 这会触发提供商注册
from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
import re


PUBLIC_SCRIPT_FIELDS = ["_id", "video_id", "video_name", "timestamp", "picture", "narration", "OST"]
FUSION_STREAM_PREVIEW_LIMIT = 1800
FUSION_STREAM_WRITE_INTERVAL_SECONDS = 0.2


def _append_fusion_stream_preview(existing: str, chunk: str) -> str:
    """Keep task progress responsive without persisting an unbounded model transcript."""
    return (str(existing or "") + str(chunk or ""))[-FUSION_STREAM_PREVIEW_LIMIT:]


def _fusion_stream_failure_snapshot(current: dict | None, error: Exception, now: float) -> dict:
    """Persist actionable stream failure context without promoting partial JSON to output."""
    details = dict(getattr(error, "details", {}) or {})
    category = str(details.get("failure_category") or "provider_error")
    state = {
        "waiting_first_chunk": "waiting_first_chunk_timeout",
        "timed_out_after_progress": "timed_out_after_progress",
        "total_budget_expired": "total_budget_expired",
    }.get(category, "failed")
    snapshot = dict(current or {})
    snapshot.update(
        {
            "state": state,
            "failure_category": category,
            "failure_diagnostics": details,
            "error_message": str(error),
            "updated_at": now,
        }
    )
    return snapshot
SHORT_DRAMA_PROMPT_CATEGORY = "short_drama_narration"
FILM_TV_PROMPT_CATEGORY = "film_tv_narration"
SHORT_DRAMA_SEARCH_KEYWORDS = "短剧 剧情 介绍 人物 结局"
FILM_TV_SEARCH_KEYWORDS = "影视 剧情 介绍 人物 结局 电影 电视剧"


def _persist_fusion_generation_result(payload: dict) -> str:
    audit_dir = utils.task_dir("fusion_audits")
    audit_path = os.path.join(audit_dir, f"fusion_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()}.json")
    with open(audit_path, "w", encoding="utf-8") as audit_file:
        json.dump(payload, audit_file, ensure_ascii=False, indent=2)
    return audit_path


def acknowledge_fusion_audit(audit_path: str, conflicts: list[dict]) -> None:
    if not audit_path or not os.path.isfile(audit_path):
        return
    with open(audit_path, "r", encoding="utf-8") as audit_file:
        payload = json.load(audit_file)
    payload["evidence_conflicts"] = conflicts
    report = payload.get("finalization_report")
    if isinstance(report, dict):
        report["unresolved_conflict_count"] = sum(
            1 for conflict in conflicts if isinstance(conflict, dict) and conflict.get("status") == "unresolved"
        )
        report["acknowledged_conflict_count"] = sum(
            1 for conflict in conflicts if isinstance(conflict, dict) and conflict.get("status") == "acknowledged"
        )
    with open(audit_path, "w", encoding="utf-8") as audit_file:
        json.dump(payload, audit_file, ensure_ascii=False, indent=2)


def _store_fusion_finalization_result(
    finalization,
    *,
    regression_only: bool = False,
    source_verified: bool = True,
) -> str:
    """Place one complete finalization result into review state and its audit file."""
    report = asdict(finalization.report)
    payload = {
        "status": "regression_only" if regression_only else "finalized",
        "regression_only": bool(regression_only),
        "source_verified": bool(source_verified),
        "source_identity_waiver": bool(regression_only),
        "original_script": finalization.original_script,
        "finalized_script": finalization.script,
        "finalization_report": report,
        "evidence_conflicts": finalization.evidence_conflicts,
    }
    audit_path = _persist_fusion_generation_result(payload)
    st.session_state["fusion_original_matched_script"] = finalization.original_script
    st.session_state["fusion_evidence_conflicts"] = finalization.evidence_conflicts
    st.session_state["fusion_finalization_report"] = report
    st.session_state["fusion_generation_audit_path"] = audit_path
    return audit_path


def _normalize_fusion_evidence_conflicts(
    conflicts,
    *,
    default_video_name: str,
    identity_by_video: dict,
    default_source_identity=None,
) -> list[EvidenceConflict]:
    """Normalize model conflict records before they cross into finalization."""
    normalized = []
    for conflict in conflicts or []:
        if not isinstance(conflict, dict):
            continue
        conflict_video_name = str(conflict.get("video_name") or default_video_name)
        normalized.append(
            EvidenceConflict.from_mapping(
                {
                **conflict,
                "video_name": conflict_video_name,
                "source_video_identity": identity_by_video.get(conflict_video_name)
                or default_source_identity,
                }
            )
        )
    return normalized


def _normalize_paths(paths):
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        return []

    normalized_paths = []
    seen = set()
    for path in paths:
        if not isinstance(path, str):
            continue
        path = path.strip()
        if not path or path in seen:
            continue
        normalized_paths.append(path)
        seen.add(path)
    return normalized_paths


def _build_combined_subtitle_content(subtitle_paths, video_paths=None):
    sections = []
    video_paths = _normalize_paths(video_paths)
    for index, subtitle_path in enumerate(_normalize_paths(subtitle_paths), start=1):
        if not os.path.exists(subtitle_path):
            continue

        video_path = video_paths[index - 1] if index <= len(video_paths) else ""
        if video_path:
            header = (
                f"# 视频 {index}: {os.path.basename(video_path)}\n"
                f"字幕文件: {os.path.basename(subtitle_path)}"
            )
        else:
            header = f"# 视频 {index}\n字幕文件: {os.path.basename(subtitle_path)}"
        sections.append(f"{header}\n{read_subtitle_text(subtitle_path).text}".strip())

    return "\n\n".join(sections)


def _normalize_narration_items_video_sources(items, video_paths):
    return normalize_script_video_sources(items, _normalize_paths(video_paths))


def _strip_planner_only_fields(items):
    return [
        {field: item[field] for field in PUBLIC_SCRIPT_FIELDS if field in item}
        for item in items
        if isinstance(item, dict)
    ]


def _format_progress_status(progress, message: str = "", tr=lambda key: key):
    message = str(message or "").strip()
    if message:
        return message
    return f"{tr('Progress')}: {progress}%"


def _call_fusion_request_with_retry(call, on_retry=None):
    return call_fusion_request_with_retry(call, on_retry=on_retry)


def create_fusion_segment_plan(
    *,
    analyzer: SubtitleAnalyzerAdapter,
    short_name: str,
    plot_analysis: str,
    subtitle_content: str,
    narration_copy: str,
    narration_language: str,
    drama_genre: str,
    visual_evidence: str,
    highlight_candidates: str,
    temperature: float,
    stream_callback=None,
    on_retry=None,
    attempt_store: FusionPlanAttemptStore | None = None,
    attempt_context: dict | None = None,
) -> dict:
    """Generate and validate a creator-approvable Fusion Segment Plan."""
    plan_raw = _call_fusion_request_with_retry(
        lambda: analyzer.plan_narration_segments(
            short_name=short_name,
            plot_analysis=plot_analysis,
            subtitle_content=subtitle_content,
            narration_copy=narration_copy,
            narration_language=narration_language,
            drama_genre=drama_genre,
            visual_evidence=visual_evidence,
            highlight_candidates=highlight_candidates,
            temperature=temperature,
            stream_callback=stream_callback,
        ),
        on_retry=on_retry,
    )
    context = dict(attempt_context or {})
    input_fingerprint = str(context.get("input_fingerprint") or hashlib.sha256(
        json.dumps(
            {
                "short_name": short_name,
                "narration_copy": narration_copy,
                "subtitle_content": subtitle_content,
                "visual_evidence": visual_evidence,
                "highlight_candidates": highlight_candidates,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest())

    def record(raw_response: str, *, kind: str, parent_attempt_id: str = ""):
        if attempt_store is None:
            return None
        return attempt_store.create(
            raw_response=raw_response,
            input_fingerprint=input_fingerprint,
            provider=str(context.get("provider") or ""),
            model=str(context.get("model") or ""),
            kind=kind,
            parent_attempt_id=parent_attempt_id,
            project_id=str(context.get("project_id") or ""),
            version_id=str(context.get("version_id") or ""),
        )

    def update_attempt(attempt, **changes):
        if attempt_store is not None and attempt is not None:
            return attempt_store.update(str(attempt["attempt_id"]), **changes)
        return attempt

    original_attempt = record(plan_raw, kind="generation")
    plan = parse_and_fix_json(plan_raw)
    if attempt_store is not None and original_attempt is not None and isinstance(plan, dict):
        original_attempt = attempt_store.save_recovery_payload(
            str(original_attempt["attempt_id"]), plan
        )
    pipeline = FusionScriptPipeline()
    if isinstance(plan, dict):
        validation_report = pipeline.validate_plan_findings(narration_copy, plan)
    else:
        validation_report = None
    continuity_report = (
        pipeline.validate_continuity(narration_copy, plan)
        if validation_report is not None and validation_report.is_valid
        else None
    )
    needs_repair = (
        validation_report is None
        or not validation_report.is_valid
        or not continuity_report.is_renderable
    )
    if needs_repair:
        repair_findings = (
            {
                "is_valid": False,
                "findings": [
                    {
                        "code": "plan_json_invalid",
                        "message": "Fusion Segment Plan is not valid JSON",
                        "recovery_class": "auto_repairable",
                    }
                ],
            }
            if validation_report is None
            else (
                validation_report.to_dict()
                if not validation_report.is_valid
                else continuity_report.to_dict()
            )
        )
        update_attempt(
            original_attempt,
            status="validation_failed",
            findings=repair_findings["findings"],
        )
        try:
            repaired_raw = analyzer.repair_fusion_segment_plan(
                plan_payload=(
                    json.dumps(plan, ensure_ascii=False)
                    if isinstance(plan, dict)
                    else str(plan_raw)
                ),
                continuity_findings=json.dumps(repair_findings, ensure_ascii=False),
                subtitle_content=subtitle_content,
                visual_evidence=visual_evidence,
                highlight_candidates=highlight_candidates,
                temperature=temperature,
            )
        except Exception as error:
            attempt = update_attempt(original_attempt, status="waiting_for_review")
            if attempt is not None:
                raise FusionPlanRecoveryRequired(
                    "分段计划已保存，但自动修复未完成。请检查计划或重新生成。",
                    attempt_id=str(attempt["attempt_id"]),
                    findings=repair_findings["findings"],
                ) from error
            raise
        repaired_attempt = record(
            repaired_raw,
            kind="format_repair" if validation_report is None else "targeted_repair",
            parent_attempt_id=(
                str(original_attempt["attempt_id"]) if original_attempt is not None else ""
            ),
        )
        repaired_plan = parse_and_fix_json(repaired_raw)
        if (
            attempt_store is not None
            and repaired_attempt is not None
            and isinstance(repaired_plan, dict)
        ):
            repaired_attempt = attempt_store.save_recovery_payload(
                str(repaired_attempt["attempt_id"]), repaired_plan
            )
        if not isinstance(repaired_plan, dict):
            findings = [{
                "code": "plan_json_invalid_after_repair",
                "message": "Fusion Segment Plan repair is not valid JSON",
                "recovery_class": "creator_edit_required",
            }]
            attempt = update_attempt(
                repaired_attempt, status="waiting_for_review", findings=findings
            )
            if attempt is not None:
                raise FusionPlanRecoveryRequired(
                    "分段计划修复结果仍无法解析。原始输出已保存，请检查或重新生成。",
                    attempt_id=str(attempt["attempt_id"]),
                    findings=findings,
                )
            raise ValueError(findings[0]["message"])
        repaired_validation = pipeline.validate_plan_findings(narration_copy, repaired_plan)
        if not repaired_validation.is_valid:
            findings = [finding.to_dict() for finding in repaired_validation.findings]
            attempt = update_attempt(
                repaired_attempt, status="waiting_for_review", findings=findings
            )
            if attempt is not None:
                raise FusionPlanRecoveryRequired(
                    "分段计划修复后仍未通过结构校验。请检查标记的问题。",
                    attempt_id=str(attempt["attempt_id"]),
                    findings=findings,
                )
            messages = "; ".join(finding["message"] for finding in findings)
            raise ValueError(f"Fusion Segment Plan remains structurally invalid after repair: {messages}")
        continuity_report = pipeline.validate_continuity(narration_copy, repaired_plan)
        if not continuity_report.is_renderable:
            findings = [finding.to_dict() for finding in continuity_report.findings]
            attempt = update_attempt(
                repaired_attempt, status="waiting_for_review", findings=findings
            )
            if attempt is not None:
                raise FusionPlanRecoveryRequired(
                    "分段计划修复后仍需连续性审核。请检查标记的问题。",
                    attempt_id=str(attempt["attempt_id"]),
                    findings=findings,
                )
            messages = "; ".join(finding["message"] for finding in findings)
            raise ValueError(f"Fusion Segment Plan lacks narrative continuity after repair: {messages}")
        update_attempt(repaired_attempt, status="validated", findings=[])
        update_attempt(original_attempt, status="repaired")
        plan = repaired_plan
    else:
        update_attempt(original_attempt, status="validated", findings=[])
    return plan


def approve_fusion_segment_plan(
    *, plan_payload: dict, narration_copy: str, source_identity: dict | None
) -> dict:
    """Create the durable approval proof required before matching can start."""
    return {
        "approval_signature": _fusion_plan_approval_signature(
            plan_payload, narration_copy, source_identity
        ),
        "approved_at": time.time(),
        "source_video_identity": source_identity or {},
    }


def match_approved_fusion_segment_plan(
    *,
    analyzer: SubtitleAnalyzerAdapter,
    short_name: str,
    narration_copy: str,
    narration_language: str,
    drama_genre: str,
    original_sound_ratio: int,
    subtitle_content: str,
    visual_evidence: str,
    highlight_candidates: str,
    plan_payload: dict,
    temperature: float,
    plan_approval: dict,
    completed_segment_results: dict | None = None,
    resume_snapshot: dict | None = None,
    on_segment_started=None,
    on_segment_complete=None,
    on_segment_failed=None,
    on_segment_attempt=None,
    on_repair_attempt=None,
    on_stream_chunk=None,
    is_cancelled=None,
    narrative_map_override: dict | None = None,
) -> dict:
    """Match each approved plan entry against a bounded Evidence Window."""
    approval_source_identity = (
        plan_approval.get("source_video_identity") if isinstance(plan_approval, dict) else None
    )
    if not _has_valid_fusion_plan_approval(
        plan_approval, plan_payload, narration_copy, approval_source_identity
    ):
        raise ValueError("Fusion Segment Plan requires creator approval before matching")
    narrative_map = (
        dict(narrative_map_override)
        if isinstance(narrative_map_override, dict)
        else build_narrative_map(
            approved_narration=narration_copy,
            plan_payload=plan_payload,
            subtitle_evidence=subtitle_content,
            visual_evidence=visual_evidence,
        )
    )
    class TextAdapter:
        def match_segment(self, segment_request):
            response = analyzer.match_narration_copy_to_script(
                short_name=short_name,
                plot_analysis=segment_request.intent,
                subtitle_content=segment_request.subtitle_evidence,
                narration_copy=segment_request.narration,
                temperature=temperature,
                narration_language=narration_language,
                drama_genre=drama_genre,
                original_sound_ratio=original_sound_ratio,
                visual_evidence=segment_request.visual_evidence,
                highlight_candidates=segment_request.highlight_candidates,
                core_window=segment_request.core_window,
                context_window=segment_request.context_window,
                segment_role=segment_request.story_role,
                fusion_request=True,
                stream_callback=(
                    (lambda event: on_stream_chunk(segment_request, event))
                    if on_stream_chunk
                    else None
                ),
            )
            if response.get("status") != "success":
                error = RuntimeError(str(response.get("message") or "segment matching failed"))
                error.details = dict(response.get("error_details") or {})
                raise error
            parsed = parse_and_fix_json(str(response.get("narration_script") or ""))
            if not isinstance(parsed, dict):
                raise ValueError("segment matching returned invalid JSON")
            return parsed

        def repair_transition(self, repair_request):
            repair_segment = type(
                "RepairSegment", (), {"segment_id": repair_request.affected_segment_id}
            )()
            segment = next(
                (
                    item
                    for item in plan_payload.get("segments", [])
                    if isinstance(item, dict)
                    and item.get("segment_id") == repair_request.affected_segment_id
                ),
                {},
            )
            repaired = analyzer.repair_fusion_segment_match(
                short_name=short_name,
                plot_analysis=str(segment.get("intent") or ""),
                continuity_finding=(
                    f"{repair_request.previous_segment_id} -> {repair_request.next_segment_id}: "
                    f"{repair_request.core_window}"
                ),
                narration_copy=repair_request.narration,
                subtitle_content=repair_request.subtitle_evidence,
                visual_evidence=repair_request.visual_evidence,
                highlight_candidates=repair_request.highlight_candidates,
                core_window=str(repair_request.core_window),
                temperature=temperature,
                narration_language=narration_language,
                drama_genre=drama_genre,
                stream_callback=(
                    (lambda event: on_stream_chunk(repair_segment, event))
                    if on_stream_chunk
                    else None
                ),
            )
            parsed = parse_and_fix_json(repaired)
            if not isinstance(parsed, dict):
                raise ValueError("targeted continuity repair returned invalid JSON")
            return parsed

    workflow = FusionMatchingWorkflow()
    snapshot_payload = resume_snapshot if isinstance(resume_snapshot, dict) else {}
    result = workflow.execute(
        FusionMatchingInput(
            narration_copy=narration_copy,
            plan_payload=plan_payload,
            subtitle_evidence=subtitle_content,
            visual_evidence=visual_evidence,
            highlight_candidates=highlight_candidates,
        ),
        TextAdapter(),
        resume_from=FusionMatchingSnapshot(
            plan_payload=snapshot_payload.get("plan_payload") or plan_payload,
            completed_segment_results=(
                snapshot_payload.get("completed_segment_results")
                if isinstance(snapshot_payload.get("completed_segment_results"), dict)
                else completed_segment_results or {}
            ),
            attempts_by_segment=(
                snapshot_payload.get("attempts_by_segment")
                if isinstance(snapshot_payload.get("attempts_by_segment"), dict)
                else {}
            ),
            repair_attempts_by_segment=(
                snapshot_payload.get("repair_attempts_by_segment")
                if isinstance(snapshot_payload.get("repair_attempts_by_segment"), dict)
                else {}
            ),
        ),
        retry_count=1,
        max_concurrency=2,
        on_segment_started=on_segment_started,
        on_segment_complete=on_segment_complete,
        on_segment_failed=on_segment_failed,
        on_segment_attempt=on_segment_attempt,
        on_repair_attempt=on_repair_attempt,
        is_cancelled=is_cancelled,
    )
    return {
        # This internal link is needed by the review workspace to keep a rendered
        # timeline item attached to its Narrative Map beat and evidence window.
        "items": result.items,
        "evidence_conflicts": result.evidence_conflicts,
        "continuity_report": result.continuity_report.to_dict(),
        "narrative_map": narrative_map,
        "narrative_quality_findings": evaluate_narrative_quality(
            narrative_map, result.items
        ),
        "matching_snapshot": {
            "plan_payload": result.snapshot.plan_payload,
            "completed_segment_results": result.snapshot.completed_segment_results,
            "attempts_by_segment": result.attempts_by_segment,
            "repair_attempts_by_segment": result.repair_attempts_by_segment,
            "repaired_segment_ids": list(result.repaired_segment_ids),
        },
    }


def finalize_fusion_matching_result(
    *, matched_plan: dict, finalization_context: dict
) -> dict:
    """Finalize a completed background match without depending on Streamlit state."""
    continuity_report = matched_plan.get("continuity_report") or {}
    if not bool(continuity_report.get("is_renderable")):
        preflight = build_render_preflight(
            continuity_report=continuity_report,
            evidence_conflicts=list(matched_plan.get("evidence_conflicts") or []),
            segment_matches=matched_plan.get("segment_matches"),
        ).to_dict(str(finalization_context.get("warning_override_reason") or ""))
        return {
            "status": "blocked_for_continuity_review",
            "original_script": list(matched_plan.get("items") or []),
            "finalized_script": [],
            "finalization_report": {},
            "evidence_conflicts": matched_plan.get("evidence_conflicts", []),
            "continuity_report": continuity_report,
            "preflight": preflight,
            "renderable": False,
        }
    candidate_payloads = list(finalization_context.get("candidate_payloads") or [])
    candidates = tuple(
        HighlightCandidate(
            time_range=TimeRange.parse(str(payload.get("time_range") or "")),
            category=str(payload.get("category") or ""),
            reason=str(payload.get("reason") or ""),
            score=int(payload.get("score") or 0),
            story_importance=int(payload.get("story_importance") or 3),
            visual_impact=int(payload.get("visual_impact") or 3),
            performance_value=int(payload.get("performance_value") or 3),
            video_id=payload.get("video_id"),
            video_name=str(payload.get("video_name") or ""),
            source_video_identity=payload.get("source_video_identity"),
            source_identity_status=str(payload.get("source_identity_status") or "unavailable"),
            defaulted_signals=tuple(payload.get("defaulted_signals") or ()),
            candidate_id=str(payload.get("candidate_id") or ""),
        )
        for payload in candidate_payloads
        if isinstance(payload, dict)
    )
    rejections = tuple(
        CandidateRejection(
            candidate_id=str(payload.get("candidate_id") or ""),
            time_range=str(payload.get("time_range") or ""),
            reason=str(payload.get("reason") or "malformed_candidate"),
        )
        for payload in (finalization_context.get("candidate_rejections") or [])
        if isinstance(payload, dict)
    )
    intake = HighlightCandidateIntake(
        candidates=candidates,
        rejections=rejections,
        submitted_count=len(candidates) + len(rejections),
    )
    default_video_name = str(
        next(iter(matched_plan.get("items") or []), {}).get("video_name") or ""
    )
    conflicts = _normalize_fusion_evidence_conflicts(
        matched_plan.get("evidence_conflicts", []),
        default_video_name=default_video_name,
        identity_by_video={},
        default_source_identity=finalization_context.get("source_identity"),
    )
    finalization = FusionScriptFinalizer().finalize(
        FinalizationRequest(
            script=tuple(matched_plan.get("items") or []),
            requested_original_sound_ratio=float(finalization_context.get("original_sound_ratio") or 0),
            candidate_intake=intake,
            evidence_conflicts=tuple(conflicts),
            source_durations=dict(finalization_context.get("source_durations") or {}),
        )
    )
    warning_override_reason = str(finalization_context.get("warning_override_reason") or "")
    preflight = build_render_preflight(
        continuity_report=continuity_report,
        evidence_conflicts=finalization.evidence_conflicts,
        segment_matches=matched_plan.get("segment_matches"),
    ).to_dict(warning_override_reason)
    narrative_map = matched_plan.get("narrative_map", {})
    if isinstance(narrative_map, dict) and narrative_map.get("approval_status") == "pending":
        preflight["warnings"].append(
            {
                "code": "narrative_map_review_required",
                "message": "Narrative Map must be approved or explicitly skipped before rendering.",
                "segment_id": "",
            }
        )
        preflight["renderable"] = False
    result = {
        "original_script": finalization.original_script,
        "finalized_script": finalization.script,
        "finalization_report": asdict(finalization.report),
        "evidence_conflicts": finalization.evidence_conflicts,
        "continuity_report": continuity_report,
        "narrative_map": narrative_map,
        "narrative_quality_findings": list(
            matched_plan.get("narrative_quality_findings") or []
        ),
        "preflight": preflight,
        "renderable": preflight["renderable"],
    }
    result["active_version_id"] = "original-match"
    original_version = _fusion_version_entry(
        version_id="original-match",
        kind="original_match",
        item_count=len(finalization.original_script),
        snapshot={
            **_fusion_version_snapshot(result),
            "finalized_script": list(finalization.original_script),
        },
    )
    result["active_version_id"] = "finalized-script"
    result["version_history"] = [
        original_version,
        _fusion_version_entry(
            version_id="finalized-script",
            kind="finalized_script",
            item_count=len(finalization.script),
            snapshot=_fusion_version_snapshot(result),
        ),
    ]
    return result


def _fusion_version_snapshot(finalization: dict) -> dict:
    """Keep a JSON-safe, credential-free review context for explicit version restore."""
    fields = (
        "original_script",
        "finalized_script",
        "finalization_report",
        "evidence_conflicts",
        "continuity_report",
        "narrative_map",
        "narrative_quality_findings",
        "review_decisions",
        "preflight",
        "renderable",
        "active_version_id",
    )
    payload = {
        field: finalization.get(field, [] if field == "review_decisions" else None)
        for field in fields
        if field in finalization or field == "review_decisions"
    }
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _fusion_version_entry(
    *, version_id: str, kind: str, item_count: int, snapshot: dict, **extra
) -> dict:
    return {
        "version_id": version_id,
        "kind": kind,
        "created_at": time.time(),
        "item_count": item_count,
        "snapshot": snapshot,
        **extra,
    }


def _fusion_matching_task_store() -> LocalAnalysisTaskStore:
    return LocalAnalysisTaskStore(Path(utils.task_dir("fusion_matching")))


def _fusion_plan_attempt_store() -> FusionPlanAttemptStore:
    return FusionPlanAttemptStore(Path(utils.task_dir("fusion_plan_attempts")))


def start_fusion_matching_task(
    *,
    short_name: str,
    narration_copy: str,
    narration_language: str,
    drama_genre: str,
    original_sound_ratio: int,
    subtitle_content: str,
    visual_evidence: str,
    highlight_candidates: str,
    plan_payload: dict,
    plan_approval: dict,
    temperature: float,
    source_identity: dict | None,
    finalization_context: dict,
    resume_snapshot: dict | None = None,
) -> str:
    """Persist and start the approved segment matches without storing credentials."""
    if not _has_valid_fusion_plan_approval(
        plan_approval, plan_payload, narration_copy, source_identity
    ):
        raise ValueError("Fusion Segment Plan requires creator approval before matching")
    request = {
        "short_name": short_name,
        "narration_copy": narration_copy,
        "narration_language": narration_language,
        "drama_genre": drama_genre,
        "original_sound_ratio": int(original_sound_ratio),
        "subtitle_content": subtitle_content,
        "visual_evidence": visual_evidence,
        "highlight_candidates": highlight_candidates,
        "plan_payload": plan_payload,
        "plan_approval": plan_approval,
        "temperature": float(temperature),
        "finalization_context": finalization_context,
        "resume_snapshot": resume_snapshot or {},
    }
    request["analysis_signature"] = _fusion_matching_signature(request)
    store = _fusion_matching_task_store()
    task = store.create(request, source_identity or {})
    store.update(
        str(task["task_id"]),
        segment_matches=[
            {"segment_id": str(segment.get("segment_id") or f"segment-{index}"), "status": "pending"}
            for index, segment in enumerate(plan_payload.get("segments") or [], start=1)
            if isinstance(segment, dict)
        ],
    )
    _start_fusion_matching_runner(store, task["task_id"], request, [])
    return str(task["task_id"])


def resume_fusion_matching_task(task_id: str) -> None:
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    request = dict(task["request"])
    request["resume_snapshot"] = task.get("matching_snapshot") or request.get(
        "resume_snapshot", {}
    )
    completed = list(task.get("completed_batches") or [])
    store.update(task_id, status="queued", cancel_requested=False, error_message="")
    _start_fusion_matching_runner(store, task_id, request, completed)


def fusion_matching_task_status(task_id: str) -> dict:
    return _fusion_matching_task_store().read(task_id)


def list_fusion_matching_tasks(limit: int = 20) -> list[dict]:
    return _fusion_matching_task_store().list_tasks(limit=limit)


def override_fusion_matching_render_warning(task_id: str, reason: str) -> dict:
    """Persist a creator's explicit warning override; blockers can never be overridden."""
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("Render Preflight warning override requires a reason")
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    preflight = dict(finalization.get("preflight") or {})
    if preflight.get("blockers"):
        raise ValueError("Render Preflight blockers cannot be overridden")
    if not preflight.get("warnings"):
        raise ValueError("Render Preflight has no warnings to override")
    preflight["warning_override_reason"] = reason
    preflight["renderable"] = True
    decisions = list(finalization.get("review_decisions") or [])
    decisions.append(
        {
            "decision_id": f"preflight-warning-overridden-{len(decisions) + 1}",
            "kind": "preflight",
            "action": "warning_overridden",
            "reason": reason,
            "warning_codes": [
                str(item.get("code") or "")
                for item in preflight.get("warnings") or []
                if isinstance(item, dict)
            ],
            "created_at": time.time(),
        }
    )
    finalization["preflight"] = preflight
    finalization["renderable"] = True
    finalization["review_decisions"] = decisions
    return store.update(task_id, finalization=finalization, renderable=True)


def undo_fusion_render_warning_override(task_id: str, *, decision_id: str) -> dict:
    """Withdraw one warning override and return the task to its normal preflight state."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    decisions = list(finalization.get("review_decisions") or [])
    index = next(
        (
            current_index
            for current_index, item in enumerate(decisions)
            if isinstance(item, dict)
            and str(item.get("decision_id") or "") == str(decision_id)
            and item.get("kind") == "preflight"
            and item.get("action") == "warning_overridden"
        ),
        None,
    )
    if index is None:
        raise ValueError("The selected Render Preflight warning override cannot be undone")
    decisions.pop(index)
    preflight = dict(finalization.get("preflight") or {})
    preflight.pop("warning_override_reason", None)
    preflight["renderable"] = not preflight.get("blockers") and not preflight.get("warnings")
    finalization.update(
        {
            "preflight": preflight,
            "renderable": preflight["renderable"],
            "review_decisions": decisions,
        }
    )
    return store.update(
        task_id,
        finalization=finalization,
        renderable=finalization["renderable"],
    )


def preview_fusion_narrative_map_review(
    task_id: str, *, action: str, edited_beats: list[dict] | None = None
) -> dict:
    """Calculate a Narrative Map review impact without changing the durable task."""
    task = _fusion_matching_task_store().read(task_id)
    artifact = dict((task.get("finalization") or {}).get("narrative_map") or {})
    _reviewed, impact = review_narrative_map(
        artifact, action=action, edited_beats=edited_beats
    )
    return {
        "task_id": str(task_id),
        "action": action,
        "edited_beats": json.loads(json.dumps(edited_beats or [], ensure_ascii=False)),
        "impact": impact,
        "narrative_map_fingerprint": _fusion_narrative_map_fingerprint(artifact),
    }


def _fusion_narrative_map_fingerprint(artifact: dict) -> str:
    """Identify the current creator-reviewable Narrative Map state."""
    payload = {
        "approval_status": artifact.get("approval_status"),
        "beats": artifact.get("beats") or [],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def review_fusion_narrative_map(
    task_id: str,
    *,
    action: str,
    edited_beats: list[dict] | None = None,
    expected_narrative_map_fingerprint: str | None = None,
) -> dict:
    """Persist an approve/skip/draft action and invalidate only changed Segment Matches."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    artifact = dict(finalization.get("narrative_map") or {})
    if (
        expected_narrative_map_fingerprint is not None
        and expected_narrative_map_fingerprint != _fusion_narrative_map_fingerprint(artifact)
    ):
        raise ValueError("Narrative Map changed after this preview; review the impact again before applying")
    reviewed, impact = review_narrative_map(
        artifact, action=action, edited_beats=edited_beats
    )
    finalization["narrative_map"] = reviewed
    versions = list(finalization.get("version_history") or [])
    changes = {"finalization": finalization}
    invalidated = set(impact["invalidates_segment_matches"])
    if invalidated:
        snapshot = dict(task.get("matching_snapshot") or {})
        completed = dict(snapshot.get("completed_segment_results") or {})
        snapshot["completed_segment_results"] = {
            segment_id: response
            for segment_id, response in completed.items()
            if segment_id not in invalidated
        }
        matches = []
        for match in task.get("segment_matches") or []:
            entry = dict(match)
            if str(entry.get("segment_id") or "") in invalidated:
                entry["status"] = "invalidated"
                entry["error_message"] = "Narrative Map draft changed this Story Beat"
            matches.append(entry)
        preflight = dict(finalization.get("preflight") or {})
        blockers = list(preflight.get("blockers") or [])
        blockers.append(
            {
                "code": "narrative_map_change_requires_rematch",
                "message": "Changed Story Beats must be rematched before rendering.",
                "segment_id": ",".join(sorted(invalidated)),
            }
        )
        preflight.update({"blockers": blockers, "renderable": False})
        finalization.update({"preflight": preflight, "renderable": False})
        remaining_batches = [
            batch for batch in task.get("completed_batches") or []
            if str(batch.get("segment_id") or batch.get("batch_index") or "") not in invalidated
        ]
        changes.update(
            {
                "matching_snapshot": snapshot,
                "segment_matches": matches,
                "completed_batches": remaining_batches,
                "status": "interrupted",
                "error_message": "Narrative Map changes require targeted Segment Match recovery.",
                "renderable": False,
                "request": {**task.get("request", {}), "narrative_map_override": reviewed},
            }
        )
    else:
        preflight = dict(finalization.get("preflight") or {})
        warnings = [
            warning for warning in preflight.get("warnings") or []
            if isinstance(warning, dict)
            and warning.get("code") != "narrative_map_review_required"
        ]
        preflight["warnings"] = warnings
        preflight["renderable"] = not preflight.get("blockers") and (
            not warnings or bool(str(preflight.get("warning_override_reason") or "").strip())
        )
        finalization.update({"preflight": preflight, "renderable": preflight["renderable"]})
        changes["renderable"] = finalization["renderable"]
    version_id = f"narrative-map-{len(versions) + 1}"
    finalization["active_version_id"] = version_id
    versions.append(
        _fusion_version_entry(
            version_id=version_id,
            kind="narrative_map_review",
            item_count=len(finalization.get("finalized_script") or []),
            snapshot=_fusion_version_snapshot(finalization),
            action=action,
            changed_story_beats=list(impact["changed_story_beats"]),
        )
    )
    finalization["version_history"] = versions
    return store.update(task_id, **changes)


def approve_fusion_quality_repair(
    task_id: str, *, segment_id: str, finding_code: str
) -> dict:
    """Let a creator approve one evidence-bounded Segment Match repair."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    finding = next(
        (
            item for item in finalization.get("narrative_quality_findings") or []
            if isinstance(item, dict)
            and str(item.get("segment_id") or "") == str(segment_id)
            and str(item.get("code") or "") == str(finding_code)
        ),
        None,
    )
    if finding is None:
        raise ValueError("The selected quality finding is not available for this Segment Match")
    matching_snapshot = dict(task.get("matching_snapshot") or {})
    completed = dict(matching_snapshot.get("completed_segment_results") or {})
    if str(segment_id) not in completed:
        raise ValueError("The selected Segment Match is not available for targeted repair")
    matching_snapshot["completed_segment_results"] = {
        current_id: response
        for current_id, response in completed.items()
        if current_id != str(segment_id)
    }
    matches = []
    for match in task.get("segment_matches") or []:
        entry = dict(match)
        if str(entry.get("segment_id") or "") == str(segment_id):
            entry.update({"status": "repairing", "error_message": f"Creator approved quality repair: {finding_code}"})
        matches.append(entry)
    versions = list(finalization.get("version_history") or [])
    version_id = f"quality-repair-{len(versions) + 1}"
    finalization["active_version_id"] = version_id
    preflight = dict(finalization.get("preflight") or {})
    blockers = list(preflight.get("blockers") or [])
    blockers.append(
        {
            "code": "quality_repair_requires_rematch",
            "message": "Creator-approved quality repair must finish matching before rendering.",
            "segment_id": str(segment_id),
        }
    )
    preflight.update({"blockers": blockers, "renderable": False})
    decisions = list(finalization.get("review_decisions") or [])
    decisions.append(
        {
            "decision_id": f"quality-adopted-{len(decisions) + 1}",
            "kind": "quality",
            "action": "adopted",
            "segment_id": str(segment_id),
            "code": str(finding_code),
            "created_at": time.time(),
        }
    )
    finalization.update(
        {
            "review_decisions": decisions,
            "preflight": preflight,
            "renderable": False,
        }
    )
    versions.append(
        _fusion_version_entry(
            version_id=version_id,
            kind="quality_repair",
            item_count=len(finalization.get("finalized_script") or []),
            snapshot=_fusion_version_snapshot(finalization),
            segment_id=str(segment_id),
            finding_code=str(finding_code),
        )
    )
    finalization["version_history"] = versions
    batches = [
        batch for batch in task.get("completed_batches") or []
        if str(batch.get("segment_id") or batch.get("batch_index") or "") != str(segment_id)
    ]
    request = {
        **task.get("request", {}),
        "quality_repair_request": {"segment_id": str(segment_id), "finding_code": str(finding_code)},
    }
    return store.update(
        task_id,
        finalization=finalization,
        matching_snapshot=matching_snapshot,
        segment_matches=matches,
        completed_batches=batches,
        request=request,
        status="interrupted",
        error_message="Creator-approved quality repair is ready to resume.",
        renderable=False,
    )


def find_fusion_matching_task(
    *, source_identity: dict | None, plan_payload: dict, narration_copy: str
) -> dict | None:
    request = {"plan_payload": plan_payload, "narration_copy": narration_copy}
    return _fusion_matching_task_store().find_latest_for_source(
        source_identity or {},
        _fusion_matching_signature(request),
        include_completed=True,
    )


def ignore_fusion_quality_finding(
    task_id: str, *, segment_id: str, finding_code: str
) -> dict:
    """Persist a creator's ignore decision for one non-blocking quality suggestion."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    finding = next(
        (
            item for item in finalization.get("narrative_quality_findings") or []
            if isinstance(item, dict)
            and str(item.get("segment_id") or "") == str(segment_id)
            and str(item.get("code") or "") == str(finding_code)
        ),
        None,
    )
    if finding is None:
        raise ValueError("The selected quality finding is not available to ignore")
    decisions = list(finalization.get("review_decisions") or [])
    if any(
        isinstance(item, dict)
        and item.get("action") == "ignored"
        and item.get("kind") == "quality"
        and str(item.get("segment_id") or "") == str(segment_id)
        and str(item.get("code") or "") == str(finding_code)
        for item in decisions
    ):
        raise ValueError("The selected quality finding has already been ignored")
    decisions.append(
        {
            "decision_id": f"quality-ignored-{len(decisions) + 1}",
            "kind": "quality",
            "action": "ignored",
            "segment_id": str(segment_id),
            "code": str(finding_code),
            "finding": finding,
            "created_at": time.time(),
        }
    )
    finalization["review_decisions"] = decisions
    return store.update(task_id, finalization=finalization)


def undo_fusion_quality_ignore(task_id: str, *, decision_id: str) -> dict:
    """Undo one persisted quality-ignore decision without touching blockers or warnings."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    decisions = list(finalization.get("review_decisions") or [])
    index = next(
        (
            current_index
            for current_index, item in enumerate(decisions)
            if isinstance(item, dict)
            and str(item.get("decision_id") or "") == str(decision_id)
            and item.get("kind") == "quality"
            and item.get("action") == "ignored"
        ),
        None,
    )
    if index is None:
        raise ValueError("The selected quality-ignore decision cannot be undone")
    decisions.pop(index)
    finalization["review_decisions"] = decisions
    return store.update(task_id, finalization=finalization)


def acknowledge_fusion_evidence_conflict(task_id: str, *, conflict_key: str) -> dict:
    """Record a creator acknowledgement without resolving or weakening a conflict."""
    from app.services.fusion_workspace import fusion_evidence_conflict_key

    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    conflict = next(
        (
            item for item in finalization.get("evidence_conflicts") or []
            if isinstance(item, dict) and fusion_evidence_conflict_key(item) == str(conflict_key)
        ),
        None,
    )
    if conflict is None:
        raise ValueError("The selected Evidence Conflict is not available")
    decisions = list(finalization.get("review_decisions") or [])
    if any(
        isinstance(item, dict)
        and item.get("kind") == "evidence_conflict"
        and item.get("action") == "acknowledged"
        and str(item.get("conflict_key") or "") == str(conflict_key)
        for item in decisions
    ):
        raise ValueError("The selected Evidence Conflict has already been acknowledged")
    decisions.append(
        {
            "decision_id": f"evidence-conflict-acknowledged-{len(decisions) + 1}",
            "kind": "evidence_conflict",
            "action": "acknowledged",
            "conflict_key": str(conflict_key),
            "severity": str(conflict.get("severity") or ""),
            "time_range": str(conflict.get("time_range") or ""),
            "created_at": time.time(),
        }
    )
    finalization["review_decisions"] = decisions
    return store.update(task_id, finalization=finalization)


def undo_fusion_evidence_conflict_acknowledgement(task_id: str, *, decision_id: str) -> dict:
    """Undo a durable conflict acknowledgement; it never changes conflict status."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    finalization = dict(task.get("finalization") or {})
    decisions = list(finalization.get("review_decisions") or [])
    index = next(
        (
            current_index
            for current_index, item in enumerate(decisions)
            if isinstance(item, dict)
            and str(item.get("decision_id") or "") == str(decision_id)
            and item.get("kind") == "evidence_conflict"
            and item.get("action") == "acknowledged"
        ),
        None,
    )
    if index is None:
        raise ValueError("The selected Evidence Conflict acknowledgement cannot be undone")
    decisions.pop(index)
    finalization["review_decisions"] = decisions
    return store.update(task_id, finalization=finalization)


def compare_fusion_matching_versions(
    task_id: str, *, baseline_version_id: str, candidate_version_id: str
) -> dict:
    """Compare two durable review-context versions for one Fusion Matching Task."""
    from app.services.fusion_workspace import compare_fusion_versions

    task = _fusion_matching_task_store().read(task_id)
    return compare_fusion_versions(
        versions=list((task.get("finalization") or {}).get("version_history") or []),
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
    )


def restore_fusion_matching_version(task_id: str, *, version_id: str) -> dict:
    """Restore an explicit saved review context without bypassing its Preflight state."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    if str(task.get("status") or "") in {"queued", "running"}:
        raise ValueError("A running Fusion Matching Task cannot restore a saved version")
    finalization = dict(task.get("finalization") or {})
    versions = list(finalization.get("version_history") or [])
    selected = next(
        (
            item for item in versions
            if isinstance(item, dict) and str(item.get("version_id") or "") == str(version_id)
        ),
        None,
    )
    snapshot = selected.get("snapshot") if isinstance(selected, dict) else None
    if not isinstance(snapshot, dict):
        raise ValueError("The selected Fusion version has no restorable review context")
    restored = {**finalization, **_fusion_version_snapshot(snapshot)}
    restored["review_decisions"] = list(snapshot.get("review_decisions") or [])
    restore_version_id = f"restore-{len(versions) + 1}"
    restored["active_version_id"] = restore_version_id
    restore_entry = _fusion_version_entry(
        version_id=restore_version_id,
        kind="restored_context",
        item_count=len(restored.get("finalized_script") or []),
        snapshot=_fusion_version_snapshot(restored),
        restored_from=str(version_id),
    )
    restored["version_history"] = versions + [restore_entry]
    return store.update(
        task_id,
        finalization=restored,
        status="completed",
        renderable=bool(restored.get("renderable")),
        error_message="",
    )


def edit_fusion_timeline_item(
    task_id: str, *, item_id: int | str, new_timestamp: str
) -> dict:
    """Apply one creator timeline edit without leaving its approved Evidence Window."""
    store = _fusion_matching_task_store()
    task = store.read(task_id)
    if str(task.get("status") or "") in {"queued", "running"}:
        raise ValueError("A running Fusion Matching Task cannot edit the timeline")
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    finalization = dict(task.get("finalization") or {})
    script = [dict(item) for item in finalization.get("finalized_script") or []]
    target = next(
        (item for item in script if str(item.get("_id")) == str(item_id)),
        None,
    )
    if target is None:
        raise ValueError("The selected Fusion timeline item does not exist")
    segment_id = str(target.get("_segment_id") or "")
    plan = request.get("plan_payload") if isinstance(request.get("plan_payload"), dict) else {}
    segment = next(
        (
            item for item in plan.get("segments") or []
            if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id
        ),
        None,
    )
    if segment is None:
        raise ValueError("The selected timeline item has no approved Segment identity")
    edited_range = TimeRange.parse(str(new_timestamp or ""))
    evidence_range = TimeRange.parse(str(segment.get("core_window") or ""))
    if (
        edited_range.start_seconds < evidence_range.start_seconds
        or edited_range.end_seconds > evidence_range.end_seconds
    ):
        raise ValueError("Timeline edits cannot expand beyond the approved Evidence Window")
    target["timestamp"] = str(new_timestamp)
    context = request.get("finalization_context")
    context = context if isinstance(context, dict) else {}
    FusionScriptFinalizer().validate_authored_timeline(
        script, dict(context.get("source_durations") or {})
    )
    warning_reason = str(
        (finalization.get("preflight") or {}).get("warning_override_reason") or ""
    )
    preflight = build_render_preflight(
        continuity_report=finalization.get("continuity_report") or {},
        evidence_conflicts=finalization.get("evidence_conflicts") or [],
        segment_matches=task.get("segment_matches") or [],
    ).to_dict(warning_reason)
    versions = list(finalization.get("version_history") or [])
    version_id = f"timeline-edit-{len(versions) + 1}"
    finalization.update(
        {
            "finalized_script": script,
            "preflight": preflight,
            "renderable": bool(preflight.get("renderable")),
            "active_version_id": version_id,
        }
    )
    versions.append(
        _fusion_version_entry(
            version_id=version_id,
            kind="timeline_edit",
            item_count=len(script),
            snapshot=_fusion_version_snapshot(finalization),
            edited_item_id=str(item_id),
            segment_id=segment_id,
        )
    )
    finalization["version_history"] = versions
    return store.update(
        task_id,
        finalization=finalization,
        status="completed",
        renderable=bool(finalization.get("renderable")),
        error_message="",
    )


def cancel_fusion_matching_task(task_id: str) -> None:
    _fusion_matching_task_store().request_cancel(task_id)


def _start_fusion_matching_runner(
    store: LocalAnalysisTaskStore,
    task_id: str,
    request: dict,
    completed_records: list[dict],
) -> None:
    completed_responses = {
        str(record.get("segment_id")): record["response"]
        for record in completed_records
        if (
            isinstance(record, dict)
            and record.get("status") == "succeeded"
            and isinstance(record.get("response"), dict)
        )
    }
    persisted_snapshot = request.get("resume_snapshot")
    if not isinstance(persisted_snapshot, dict):
        persisted_snapshot = {}

    def work(progress, checkpoint, cancelled):
        provider = str(config.app.get("text_llm_provider", "gemini")).lower()
        analyzer = SubtitleAnalyzerAdapter(
            config.app.get(f"text_{provider}_api_key"),
            config.app.get(f"text_{provider}_model_name"),
            config.app.get(f"text_{provider}_base_url"),
            provider,
            prompt_category=FILM_TV_PROMPT_CATEGORY,
        )
        segment_count = max(1, len(request["plan_payload"].get("segments") or []))
        task_state_lock = RLock()
        attempts_by_segment = dict(persisted_snapshot.get("attempts_by_segment") or {})
        repair_attempts_by_segment = dict(
            persisted_snapshot.get("repair_attempts_by_segment") or {}
        )
        stream_revision = 0
        latest_stream_snapshot = None
        last_stream_snapshot_write_at = 0.0

        def checkpoint_stream(segment_request, event):
            nonlocal stream_revision, latest_stream_snapshot, last_stream_snapshot_write_at
            event = event if isinstance(event, dict) else {}
            chunk_type = str(event.get("type") or "content")
            chunk_text = str(event.get("text") or "")
            now = time.time()
            with task_state_lock:
                current = latest_stream_snapshot or store.read(task_id).get("stream_snapshot") or {}
                segment_id = str(segment_request.segment_id)
                attempt = int(attempts_by_segment.get(segment_id) or 1)
                if (
                    current.get("phase") != "matching"
                    or current.get("segment_id") != segment_id
                    or current.get("attempt") != attempt
                ):
                    current = {
                        "phase": "matching",
                        "segment_id": segment_id,
                        "attempt": attempt,
                        "reasoning_text": "",
                        "content_text": "",
                        "first_chunk_at": now,
                    }
                bucket = "reasoning_text" if chunk_type == "reasoning" else "content_text"
                if chunk_type in {"reasoning", "content"} and chunk_text:
                    current[bucket] = _append_fusion_stream_preview(
                        current.get(bucket) or "", chunk_text
                    )
                current.update(
                    {
                        "state": "completed" if chunk_type == "done" else "streaming",
                        "updated_at": now,
                        "last_chunk_at": now,
                    }
                )
                latest_stream_snapshot = current
                if (
                    chunk_type == "done"
                    or now - last_stream_snapshot_write_at >= FUSION_STREAM_WRITE_INTERVAL_SECONDS
                ):
                    stream_revision += 1
                    current["revision"] = stream_revision
                    store.update(task_id, stream_snapshot=current)
                    last_stream_snapshot_write_at = now

        def persist_matching_snapshot():
            with task_state_lock:
                store.update(
                    task_id,
                    matching_snapshot={
                        "plan_payload": request["plan_payload"],
                        "completed_segment_results": dict(completed_responses),
                        "attempts_by_segment": dict(attempts_by_segment),
                        "repair_attempts_by_segment": dict(repair_attempts_by_segment),
                    },
                )

        def update_segment_status(
            segment_id, status, *, response=None, error_message="", attempts=None,
            repair_attempts=None,
        ):
            with task_state_lock:
                task = store.read(task_id)
                entries = list(task.get("segment_matches") or [])
                updated = False
                for entry in entries:
                    if str(entry.get("segment_id")) == str(segment_id):
                        entry["status"] = status
                        entry["error_message"] = error_message
                        if response is not None:
                            entry["response"] = response
                        if attempts is not None:
                            entry["attempts"] = attempts
                        if repair_attempts is not None:
                            entry["repair_attempts"] = repair_attempts
                        updated = True
                        break
                if not updated:
                    entries.append({
                        "segment_id": str(segment_id),
                        "status": status,
                        "error_message": error_message,
                        **({"response": response} if response is not None else {}),
                        **({"attempts": attempts} if attempts is not None else {}),
                        **({"repair_attempts": repair_attempts} if repair_attempts is not None else {}),
                    })
                store.update(task_id, segment_matches=entries)

        def mark_segment_started(segment_request):
            nonlocal latest_stream_snapshot, last_stream_snapshot_write_at
            update_segment_status(segment_request.segment_id, "running")
            with task_state_lock:
                current = store.read(task_id).get("stream_snapshot") or {}
                stream_id = str(segment_request.segment_id)
                if current.get("segment_id") != stream_id:
                    latest_stream_snapshot = {
                            "revision": stream_revision,
                            "phase": "matching",
                            "segment_id": stream_id,
                            "attempt": int(attempts_by_segment.get(stream_id) or 1),
                            "state": "waiting_first_chunk",
                            "reasoning_text": "",
                            "content_text": "",
                            "updated_at": time.time(),
                    }
                    store.update(task_id, stream_snapshot=latest_stream_snapshot)
                    last_stream_snapshot_write_at = time.time()

        def checkpoint_segment(segment_request, response):
            checkpoint({
                "batch_index": segment_request.segment_id,
                "segment_id": segment_request.segment_id,
                "status": "succeeded",
                "response": response,
            })
            completed_responses[segment_request.segment_id] = response
            update_segment_status(segment_request.segment_id, "succeeded", response=response)
            persist_matching_snapshot()
            progress(
                15 + (len(completed_responses) / segment_count) * 75,
                f"正在匹配剪辑段落 ({len(completed_responses)}/{segment_count})...",
            )

        def checkpoint_failure(segment_request, error):
            nonlocal stream_revision, latest_stream_snapshot, last_stream_snapshot_write_at
            checkpoint({
                "batch_index": segment_request.segment_id,
                "segment_id": segment_request.segment_id,
                "status": "failed",
                "error_message": str(error),
            })
            update_segment_status(segment_request.segment_id, "failed", error_message=str(error))
            with task_state_lock:
                latest_stream_snapshot = _fusion_stream_failure_snapshot(
                    latest_stream_snapshot or store.read(task_id).get("stream_snapshot"),
                    error,
                    time.time(),
                )
                stream_revision += 1
                latest_stream_snapshot["revision"] = stream_revision
                store.update(task_id, stream_snapshot=latest_stream_snapshot)
                last_stream_snapshot_write_at = time.time()

        def checkpoint_attempt(segment_request, attempt_count):
            nonlocal stream_revision, latest_stream_snapshot, last_stream_snapshot_write_at
            with task_state_lock:
                attempts_by_segment[segment_request.segment_id] = attempt_count
                update_segment_status(
                    segment_request.segment_id,
                    "retrying" if attempt_count > 1 else "running",
                    attempts=attempt_count,
                )
                if attempt_count > 1:
                    stream_revision += 1
                    latest_stream_snapshot = {
                            "revision": stream_revision,
                            "phase": "matching",
                            "segment_id": str(segment_request.segment_id),
                            "attempt": attempt_count,
                            "state": "retrying",
                            "reasoning_text": "",
                            "content_text": "",
                            "updated_at": time.time(),
                    }
                    store.update(task_id, stream_snapshot=latest_stream_snapshot)
                    last_stream_snapshot_write_at = time.time()
                persist_matching_snapshot()

        def checkpoint_repair_attempt(repair_request, attempt_count):
            with task_state_lock:
                repair_attempts_by_segment[repair_request.affected_segment_id] = attempt_count
                update_segment_status(
                    repair_request.affected_segment_id,
                    "repairing",
                    repair_attempts=attempt_count,
                )
                persist_matching_snapshot()

        matching_request = {
            key: value
            for key, value in request.items()
            if key not in {
                "analysis_signature",
                "finalization_context",
                "resume_snapshot",
                # Durable workflow metadata is consumed by this runner after
                # matching; it is not part of the matcher contract.
                "quality_repair_request",
            }
        }
        matched = match_approved_fusion_segment_plan(
            analyzer=analyzer,
            completed_segment_results=completed_responses,
            resume_snapshot=persisted_snapshot,
            on_segment_started=mark_segment_started,
            on_segment_complete=checkpoint_segment,
            on_segment_failed=checkpoint_failure,
            on_segment_attempt=checkpoint_attempt,
            on_repair_attempt=checkpoint_repair_attempt,
            on_stream_chunk=checkpoint_stream,
            is_cancelled=cancelled,
            **matching_request,
        )
        snapshot = matched.get("matching_snapshot") or {}
        repaired_segment_ids = set(snapshot.get("repaired_segment_ids") or [])
        for segment_id, attempts in (snapshot.get("attempts_by_segment") or {}).items():
            update_segment_status(
                segment_id,
                "repaired" if segment_id in repaired_segment_ids else "succeeded",
                attempts=attempts,
                repair_attempts=(snapshot.get("repair_attempts_by_segment") or {}).get(segment_id, 0),
            )
        store.update(task_id, matching_snapshot=snapshot, stream_snapshot=None)
        progress(92, "正在执行剪辑脚本最终校验...")
        finalization = finalize_fusion_matching_result(
            matched_plan=matched,
            finalization_context=request["finalization_context"],
        )
        prior_finalization = store.read(task_id).get("finalization") or {}
        prior_versions = list(prior_finalization.get("version_history") or [])
        prior_decisions = list(prior_finalization.get("review_decisions") or [])
        quality_repair = request.get("quality_repair_request")
        if prior_versions and isinstance(quality_repair, dict):
            finalization["review_decisions"] = prior_decisions
            output_version_id = f"quality-repair-output-{len(prior_versions) + 1}"
            finalization["active_version_id"] = output_version_id
            finalization["version_history"] = prior_versions + [
                _fusion_version_entry(
                    version_id=output_version_id,
                    kind="quality_repair_output",
                    item_count=len(finalization.get("finalized_script") or []),
                    snapshot=_fusion_version_snapshot(finalization),
                    segment_id=str(quality_repair.get("segment_id") or ""),
                )
            ]
        return {
            "matched_plan": matched,
            "finalization": finalization,
            "renderable": finalization["renderable"],
            "request": {
                key: value for key, value in request.items()
                if key != "quality_repair_request"
            },
        }

    LocalAnalysisTaskRunner(store).start(task_id, work)


def _fusion_matching_signature(request: dict) -> str:
    payload = {
        "plan_payload": request.get("plan_payload"),
        "narration_copy": request.get("narration_copy"),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fusion_plan_approval_signature(
    plan_payload: dict, narration_copy: str, source_identity: dict | None
) -> str:
    payload = {
        "plan_payload": plan_payload,
        "narration_copy": narration_copy,
        "source_video_identity": source_identity or {},
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _has_valid_fusion_plan_approval(
    approval: dict | None, plan_payload: dict, narration_copy: str, source_identity: dict | None
) -> bool:
    return bool(
        isinstance(approval, dict)
        and approval.get("approval_signature")
        == _fusion_plan_approval_signature(plan_payload, narration_copy, source_identity)
    )


def parse_and_fix_json(json_string):
    """
    解析并修复JSON字符串

    Args:
        json_string: 待解析的JSON字符串

    Returns:
        dict: 解析后的字典，如果解析失败返回None
    """
    if not json_string or not json_string.strip():
        logger.error("JSON字符串为空")
        return None

    # 清理字符串
    json_string = json_string.strip()

    # 尝试直接解析
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.warning(f"直接JSON解析失败: {e}")

    # 尝试修复双大括号问题（LLM生成的常见问题）
    try:
        # 将双大括号替换为单大括号
        fixed_braces = json_string.replace('{{', '{').replace('}}', '}')
        logger.info("修复双大括号格式")
        return json.loads(fixed_braces)
    except json.JSONDecodeError:
        pass

    # 尝试提取JSON部分
    try:
        # 查找JSON代码块
        json_match = re.search(r'```json\s*(.*?)\s*```', json_string, re.DOTALL)
        if json_match:
            json_content = json_match.group(1).strip()
            logger.info("从代码块中提取JSON内容")
            return json.loads(json_content)
    except json.JSONDecodeError:
        pass

    # 尝试查找大括号包围的内容
    try:
        # 查找第一个 { 到最后一个 } 的内容
        start_idx = json_string.find('{')
        end_idx = json_string.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_content = json_string[start_idx:end_idx+1]
            logger.info("提取大括号包围的JSON内容")
            return json.loads(json_content)
    except json.JSONDecodeError:
        pass

    # 尝试综合修复JSON格式问题
    try:
        fixed_json = json_string

        # 1. 修复双大括号问题
        fixed_json = fixed_json.replace('{{', '{').replace('}}', '}')

        # 2. 提取JSON内容（如果有其他文本包围）
        start_idx = fixed_json.find('{')
        end_idx = fixed_json.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            fixed_json = fixed_json[start_idx:end_idx+1]

        # 3. 移除注释
        fixed_json = re.sub(r'#.*', '', fixed_json)
        fixed_json = re.sub(r'//.*', '', fixed_json)

        # 4. 移除多余的逗号
        fixed_json = re.sub(r',\s*}', '}', fixed_json)
        fixed_json = re.sub(r',\s*]', ']', fixed_json)

        # 5. 修复单引号
        fixed_json = re.sub(r"'([^']*)':", r'"\1":', fixed_json)

        # 6. 修复没有引号的属性名，仅匹配对象边界后的 key，避免误伤时间戳等字符串值
        fixed_json = re.sub(r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', fixed_json)

        # 7. 修复重复的引号
        fixed_json = re.sub(r'""([^"]*?)""', r'"\1"', fixed_json)

        logger.info("尝试综合修复JSON格式问题后解析")
        return json.loads(fixed_json)
    except json.JSONDecodeError as e:
        logger.debug(f"综合修复失败: {e}")
        pass

    # 如果所有方法都失败，直接返回 None，避免生成不可剪辑的默认假脚本
    logger.error(f"所有JSON解析方法都失败，原始内容: {json_string[:200]}...")
    return None


def _get_tavily_api_key() -> str:
    return (
        st.session_state.get("tavily_api_key")
        or config.app.get("tavily_api_key")
        or ""
    ).strip()


def _build_tavily_context(
    title: str,
    tr=lambda key: key,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
) -> str | None:
    title = str(title or "").strip()
    if not title:
        st.error(tr(empty_title_message_key))
        return None

    api_key = _get_tavily_api_key()
    if not api_key:
        st.error(tr("Please configure Tavily API Key in Basic Settings"))
        return None

    try:
        search_data = search_story_context(
            title,
            api_key,
            search_keywords=search_keywords,
            empty_name_message=tr(empty_title_message_key),
            search_depth=config.app.get("tavily_search_depth", "basic"),
            max_results=config.app.get("tavily_max_results", 5),
        )
        return format_search_context(search_data)
    except TavilySearchError as e:
        logger.error(f"Tavily 短剧检索失败: {str(e)}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Tavily 短剧检索异常: {traceback.format_exc()}")
        st.error(f"{tr('Tavily search failed')}: {str(e)}")
        return None


def _build_plot_analysis_input(
    subtitle_content: str,
    short_name: str = "",
    enable_web_search: bool = False,
    tr=lambda key: key,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
) -> str | None:
    subtitle_content = str(subtitle_content or "").strip()
    if not enable_web_search:
        return subtitle_content

    tavily_context = _build_tavily_context(
        short_name,
        tr,
        search_keywords=search_keywords,
        empty_title_message_key=empty_title_message_key,
    )
    if tavily_context is None:
        return None

    return f"""# 分析补充说明
请先参考 Tavily 联网检索结果理解{web_search_context_description}，再结合原始字幕完成剧情理解。
如果联网检索结果与字幕内容冲突，请以字幕内容为准；时间戳必须只从字幕内容中提取。

{tavily_context}

# 原始字幕
{subtitle_content}"""


def analyze_short_drama_plot(
    subtitle_path,
    temperature,
    tr=lambda key: key,
    subtitle_content=None,
    short_name: str = "",
    enable_web_search: bool = False,
    video_paths=None,
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
):
    """仅执行短剧字幕剧情理解，返回可编辑的剧情分析文本。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    plot_analysis_input = _build_plot_analysis_input(
        subtitle_content,
        short_name=short_name,
        enable_web_search=enable_web_search,
        tr=tr,
        search_keywords=search_keywords,
        empty_title_message_key=empty_title_message_key,
        web_search_context_description=web_search_context_description,
    )
    if plot_analysis_input is None:
        return None

    try:
        logger.info("使用新的LLM服务架构进行字幕分析")
        analyzer = SubtitleAnalyzerAdapter(
            text_api_key,
            text_model,
            text_base_url,
            text_provider,
            prompt_category=prompt_category,
        )
        analysis_result = analyzer.analyze_subtitle(plot_analysis_input)
    except Exception as e:
        logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
        analysis_result = analyze_subtitle(
            subtitle_content=plot_analysis_input,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            save_result=True,
            temperature=temperature,
            provider=text_provider,
            prompt_category=prompt_category,
        )

    if analysis_result["status"] != "success":
        logger.error(f"分析失败: {analysis_result['message']}")
        st.error(tr("Script generation failed check logs"))
        return None

    return analysis_result["analysis"]


def generate_short_drama_narration_copy(
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    drama_genre: str = "逆袭/复仇",
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
    narration_word_count: int = 500,
    visual_evidence: str = "",
    highlight_candidates: str = "",
):
    """生成可由用户审核修改的短剧解说正文，不绑定时间戳。"""
    subtitle_paths = _normalize_paths(subtitle_path)
    if not subtitle_paths:
        st.error(tr("Please generate or upload subtitles first"))
        return None
    missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
    if missing_subtitle_paths:
        st.error(tr("Subtitle file does not exist"))
        return None

    selected_video_paths = _normalize_paths(video_paths)
    subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
        subtitle_paths,
        selected_video_paths,
    )
    if not subtitle_content:
        st.error(tr("Subtitle file is empty or unreadable"))
        return None

    analysis_text = str(plot_analysis or "").strip()
    if not analysis_text:
        analysis_text = analyze_short_drama_plot(
            subtitle_paths,
            temperature,
            tr,
            subtitle_content=subtitle_content,
            short_name=video_theme,
            enable_web_search=enable_web_search,
            video_paths=selected_video_paths,
            prompt_category=prompt_category,
            search_keywords=search_keywords,
            empty_title_message_key=empty_title_message_key,
            web_search_context_description=web_search_context_description,
        )
        if not analysis_text:
            return None

    text_provider = config.app.get('text_llm_provider', 'gemini').lower()
    text_api_key = config.app.get(f'text_{text_provider}_api_key')
    text_model = config.app.get(f'text_{text_provider}_model_name')
    text_base_url = config.app.get(f'text_{text_provider}_base_url')

    try:
        logger.info("使用新的LLM服务架构生成可审核解说文案")
        analyzer = SubtitleAnalyzerAdapter(
            text_api_key,
            text_model,
            text_base_url,
            text_provider,
            prompt_category=prompt_category,
        )
        narration_result = analyzer.generate_narration_copy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            temperature=temperature,
            narration_language=narration_language,
            drama_genre=drama_genre,
            narration_word_count=narration_word_count,
            visual_evidence=visual_evidence,
        )
    except Exception as e:
        logger.warning(f"使用新LLM服务生成文案失败，回退到旧实现: {str(e)}")
        if visual_evidence:
            raise RuntimeError("视觉融合文案生成失败，已拒绝混合视觉证据与剧情分析的旧版回退。") from e
        narration_result = generate_narration_copy_legacy(
            short_name=video_theme,
            plot_analysis=analysis_text,
            subtitle_content=subtitle_content,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            temperature=temperature,
            provider=text_provider,
            narration_language=narration_language,
            drama_genre=drama_genre,
            narration_word_count=narration_word_count,
            prompt_category=prompt_category,
        )

    if narration_result.get("status") != "success":
        logger.error(f"解说文案正文生成失败: {narration_result.get('message')}")
        st.error(tr("Script generation failed check logs"))
        return None

    narration_copy = str(narration_result.get("narration_copy", "")).strip()
    if not narration_copy:
        logger.error("模型返回空解说文案正文")
        st.error(tr("Generated narration copy is empty"))
        return None

    return {
        "narration_copy": narration_copy,
        "plot_analysis": analysis_text,
        "subtitle_content": subtitle_content,
    }


def generate_script_short_sunmmary(
    params,
    subtitle_path,
    video_theme,
    temperature,
    tr=lambda key: key,
    plot_analysis=None,
    subtitle_content=None,
    enable_web_search: bool = False,
    video_paths=None,
    narration_language: str = "简体中文（中国）",
    narration_copy: str = "",
    drama_genre: str = "逆袭/复仇",
    original_sound_ratio: int = 30,
    prompt_category: str = SHORT_DRAMA_PROMPT_CATEGORY,
    search_keywords: str = SHORT_DRAMA_SEARCH_KEYWORDS,
    empty_title_message_key: str = "Please enter short drama name before web search",
    web_search_context_description: str = "短剧名称、人物关系、剧情背景和公开剧情梗概",
    visual_evidence: str = "",
    highlight_candidates: str = "",
    highlight_candidate_items: list[dict] | None = None,
    highlight_candidate_rejections: list[dict] | None = None,
    highlight_candidate_intake: HighlightCandidateIntake | None = None,
    visual_source_identity: dict | None = None,
    fusion_segment_plan: dict | None = None,
    fusion_plan_approval: dict | None = None,
    pre_matched_fusion_result: dict | None = None,
):
    """
    生成 短剧解说 视频脚本
    要求: 提供高质量短剧字幕
    适合场景: 短剧
    """
    progress_bar = st.empty()
    status_text = st.empty()
    stream_text = st.empty()
    stream_state = {
        "reasoning": "",
        "content": "",
        "last_update": 0.0,
    }

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        status_text.text(_format_progress_status(progress, message, tr))

    def update_waiting(message: str = ""):
        progress_bar.empty()
        if message:
            status_text.text(message)
        else:
            status_text.empty()

    def update_stream_window(event):
        event = event or {}
        chunk_type = str(event.get("type") or "content")
        chunk_text = str(event.get("text") or "")
        if chunk_type == "done" or not chunk_text:
            return

        bucket = "reasoning" if chunk_type == "reasoning" else "content"
        stream_state[bucket] += chunk_text

        now = time.time()
        if now - stream_state["last_update"] < 0.12:
            return
        stream_state["last_update"] = now

        blocks = []
        if stream_state["reasoning"].strip():
            blocks.append(
                f"{tr('Model reasoning stream')}\n"
                f"{stream_state['reasoning'][-900:]}"
            )
        if stream_state["content"].strip():
            blocks.append(
                f"{tr('Model output preview')}\n"
                f"{stream_state['content'][-900:]}"
            )

        preview = "\n\n".join(blocks)[-1800:]
        escaped_preview = html.escape(preview)
        stream_text.markdown(
            f"""
            <div style="height:150px; overflow:hidden; border:1px solid #e5e7eb;
                        border-radius:8px; padding:10px 12px; background:#f8fafc;
                        color:#334155;">
              <div style="font-size:12px; font-weight:600; color:#64748b; margin-bottom:6px;">
                {html.escape(tr('LLM stream window title'))}
              </div>
              <pre style="white-space:pre-wrap; margin:0; font-size:12px; line-height:1.45;
                          font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{escaped_preview}</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )

    try:
        with st.spinner(tr("Generating script...")):
            selected_video_paths = _normalize_paths(
                video_paths
                or getattr(params, "video_origin_paths", [])
                or getattr(params, "video_origin_path", "")
            )
            if not selected_video_paths:
                st.error(tr("Please select video file first"))
                return
            """
            1. 获取字幕
            """
            update_progress(30, tr("Parsing subtitles..."))
            # 判断字幕文件是否存在
            subtitle_paths = _normalize_paths(subtitle_path)
            missing_subtitle_paths = [path for path in subtitle_paths if not os.path.exists(path)]
            if not subtitle_paths or missing_subtitle_paths:
                st.error(tr("Subtitle file does not exist"))
                return

            """
            2. 分析字幕总结剧情 - 使用新的LLM服务架构
            """
            text_provider = config.app.get('text_llm_provider', 'gemini').lower()
            text_api_key = config.app.get(f'text_{text_provider}_api_key')
            text_model = config.app.get(f'text_{text_provider}_model_name')
            text_base_url = config.app.get(f'text_{text_provider}_base_url')

            # 读取字幕文件内容（无论使用哪种实现都需要）
            subtitle_content = str(subtitle_content or "").strip() or _build_combined_subtitle_content(
                subtitle_paths,
                selected_video_paths,
            )
            if not subtitle_content:
                st.error(tr("Subtitle file is empty or unreadable"))
                return

            narration_copy = str(narration_copy or "").strip()
            if not narration_copy:
                st.error(tr("Please generate and review narration copy first"))
                return

            analyzer = SubtitleAnalyzerAdapter(
                text_api_key,
                text_model,
                text_base_url,
                text_provider,
                prompt_category=prompt_category,
            )
            if plot_analysis and str(plot_analysis).strip():
                logger.info("使用用户编辑后的剧情理解结果匹配剪辑脚本")
                analysis_result = {
                    "status": "success",
                    "analysis": str(plot_analysis).strip(),
                }
            else:
                plot_analysis_input = subtitle_content
                if enable_web_search:
                    update_waiting(tr("Searching short drama with Tavily..."))
                    plot_analysis_input = _build_plot_analysis_input(
                        subtitle_content,
                        short_name=video_theme,
                        enable_web_search=True,
                        tr=tr,
                        search_keywords=search_keywords,
                        empty_title_message_key=empty_title_message_key,
                        web_search_context_description=web_search_context_description,
                    )
                    if plot_analysis_input is None:
                        return
                try:
                    # 优先使用新的LLM服务架构
                    logger.info("使用新的LLM服务架构进行字幕分析")
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyzer.analyze_subtitle(plot_analysis_input)

                except Exception as e:
                    logger.warning(f"使用新LLM服务失败，回退到旧实现: {str(e)}")
                    # 回退到旧的实现
                    update_waiting(tr("Analyzing subtitles with model..."))
                    analysis_result = analyze_subtitle(
                        subtitle_content=plot_analysis_input,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        save_result=True,
                        temperature=temperature,
                        provider=text_provider,
                        prompt_category=prompt_category,
                    )
            if visual_evidence and fusion_segment_plan is None:
                plan = create_fusion_segment_plan(
                    analyzer=analyzer,
                    short_name=video_theme,
                    plot_analysis=str(analysis_result.get("analysis") or ""),
                    subtitle_content=subtitle_content,
                    narration_copy=narration_copy,
                    narration_language=narration_language,
                    drama_genre=drama_genre,
                    visual_evidence=visual_evidence,
                    highlight_candidates=highlight_candidates,
                    temperature=temperature,
                    stream_callback=update_stream_window,
                    on_retry=lambda _error: update_waiting(
                        tr("分段计划请求超时，正在进行第 2 次尝试…")
                    ),
                    attempt_store=_fusion_plan_attempt_store(),
                    attempt_context={
                        "provider": text_provider,
                        "model": text_model,
                    },
                )
                st.session_state["fusion_segment_plan_pending"] = plan
                st.session_state["fusion_segment_plan_editor"] = json.dumps(
                    plan, ensure_ascii=False, indent=2
                )
                st.info("分段计划已生成。请审核并确认计划后再生成剪辑脚本。")
                st.rerun()
                return
            """
            3. 根据用户审核后的文案匹配画面与时间戳
            """
            if analysis_result["status"] == "success":
                logger.info("字幕分析成功！")
                update_waiting()

                try:
                    logger.info("使用新的LLM服务架构将审核文案匹配到字幕画面")
                    update_waiting(tr("Matching narration copy to footage..."))
                    stream_text.info(tr("Waiting for model stream..."))
                    if visual_evidence and pre_matched_fusion_result:
                        narration_result = {
                            "status": "success",
                            "narration_script": json.dumps(pre_matched_fusion_result, ensure_ascii=False),
                        }
                    elif visual_evidence and fusion_segment_plan:
                        matched_plan = match_approved_fusion_segment_plan(
                            analyzer=analyzer,
                            short_name=video_theme,
                            narration_copy=narration_copy,
                            narration_language=narration_language,
                            drama_genre=drama_genre,
                            original_sound_ratio=original_sound_ratio,
                            subtitle_content=subtitle_content,
                            visual_evidence=visual_evidence,
                            highlight_candidates=highlight_candidates,
                            plan_payload=fusion_segment_plan,
                            plan_approval=fusion_plan_approval,
                            temperature=temperature,
                        )
                        narration_result = {
                            "status": "success",
                            "narration_script": json.dumps(matched_plan, ensure_ascii=False),
                        }
                    else:
                        narration_result = analyzer.match_narration_copy_to_script(
                            short_name=video_theme,
                            plot_analysis=analysis_result["analysis"],
                            subtitle_content=subtitle_content,
                            narration_copy=narration_copy,
                            temperature=temperature,
                            narration_language=narration_language,
                            drama_genre=drama_genre,
                            original_sound_ratio=original_sound_ratio,
                            visual_evidence=visual_evidence,
                            highlight_candidates=highlight_candidates,
                            stream_callback=update_stream_window,
                        )
                except Exception as e:
                    logger.warning(f"使用新LLM服务匹配画面失败，回退到旧实现: {str(e)}")
                    if visual_evidence or highlight_candidates:
                        raise RuntimeError("视觉融合脚本匹配失败，已拒绝混合视觉证据与剧情分析的旧版回退。") from e
                    stream_text.info(tr("Streaming unavailable fallback waiting..."))
                    narration_result = match_narration_copy_to_script_legacy(
                        short_name=video_theme,
                        plot_analysis=analysis_result["analysis"],
                        subtitle_content=subtitle_content,
                        narration_copy=narration_copy,
                        api_key=text_api_key,
                        model=text_model,
                        base_url=text_base_url,
                        temperature=temperature,
                        provider=text_provider,
                        narration_language=narration_language,
                        drama_genre=drama_genre,
                        original_sound_ratio=original_sound_ratio,
                        prompt_category=prompt_category,
                    )

                if narration_result["status"] == "success":
                    logger.info("\n剪辑脚本匹配成功！")
                    logger.info(narration_result["narration_script"])
                else:
                    logger.info(f"\n剪辑脚本匹配失败: {narration_result['message']}")
                    st.error(tr("Script generation failed check logs"))
                    st.stop()
            else:
                logger.error(f"分析失败: {analysis_result['message']}")
                st.error(tr("Script generation failed check logs"))
                st.stop()

            """
            4. 生成文案
            """
            logger.info("开始准备生成解说文案")

            # 结果转换为JSON字符串
            narration_script = narration_result["narration_script"]

            # 增强JSON解析，包含错误处理和修复
            narration_dict = parse_and_fix_json(narration_script)
            if narration_dict is None:
                st.error(tr("Generated narration JSON parse failed"))
                logger.error(f"JSON解析失败，原始内容: {narration_script}")
                st.stop()

            # 验证JSON结构
            if 'items' not in narration_dict:
                st.error(tr("Generated narration missing items field"))
                logger.error(f"JSON结构错误，缺少items字段: {narration_dict}")
                st.stop()

            narration_items = _normalize_narration_items_video_sources(
                narration_dict['items'],
                selected_video_paths,
            )
            narration_items = _strip_planner_only_fields(narration_items)
            if visual_evidence:
                st.session_state["fusion_original_matched_script"] = narration_items
                source_durations = {
                    os.path.basename(video_path): VideoProcessor(video_path).duration
                    for video_path in selected_video_paths
                }
                candidate_items = highlight_candidate_items or []
                candidate_payloads = [
                    candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
                    for candidate in candidate_items
                ]
                default_video_name = str(narration_items[0].get("video_name", "")) if narration_items else ""
                identity_by_video = {
                    str(candidate.get("video_name") or default_video_name): candidate.get(
                        "source_video_identity"
                    )
                    for candidate in candidate_payloads
                    if isinstance(candidate, dict) and isinstance(candidate.get("source_video_identity"), dict)
                }
                if isinstance(visual_source_identity, dict) and default_video_name:
                    identity_by_video.setdefault(default_video_name, visual_source_identity)
                evidence_conflicts = []
                try:
                    evidence_conflicts = _normalize_fusion_evidence_conflicts(
                        narration_dict.get("evidence_conflicts", []),
                        default_video_name=default_video_name,
                        identity_by_video=identity_by_video,
                        default_source_identity=visual_source_identity,
                    )
                    intake = highlight_candidate_intake or HighlightCandidateIntake(
                        candidates=tuple(candidate_items),
                        rejections=tuple(
                            CandidateRejection(
                                candidate_id=str(item.get("candidate_id") or ""),
                                time_range=str(item.get("time_range") or ""),
                                reason=str(item.get("reason") or "malformed_candidate"),
                            )
                            for item in (highlight_candidate_rejections or [])
                            if isinstance(item, dict)
                        ),
                        submitted_count=len(candidate_items) + len(highlight_candidate_rejections or []),
                    )
                    finalization = FusionScriptFinalizer().finalize(
                        FinalizationRequest(
                            script=tuple(narration_items),
                            requested_original_sound_ratio=original_sound_ratio,
                            candidate_intake=intake,
                            evidence_conflicts=tuple(evidence_conflicts),
                            source_durations=source_durations,
                        )
                    )
                except Exception as finalization_error:
                    failure_payload = {
                        "status": "failed",
                        "regression_only": bool(
                            st.session_state.get("fusion_visual_regression_only")
                        ),
                        "source_verified": bool(
                            st.session_state.get("fusion_visual_source_verified")
                        ),
                        "source_identity_waiver": bool(
                            st.session_state.get("fusion_visual_regression_only")
                        ),
                        "original_script": narration_items,
                        "finalized_script": None,
                        "finalization_report": None,
                        "evidence_conflicts": (
                            [conflict.to_dict() for conflict in evidence_conflicts]
                            if evidence_conflicts
                            else [
                                conflict
                                for conflict in narration_dict.get("evidence_conflicts", [])
                                if isinstance(conflict, dict)
                            ]
                        ),
                        "error": str(finalization_error),
                    }
                    st.session_state["fusion_generation_audit_path"] = _persist_fusion_generation_result(
                        failure_payload
                    )
                    raise
                narration_items = finalization.script
                _store_fusion_finalization_result(
                    finalization,
                    regression_only=bool(
                        st.session_state.get("fusion_visual_regression_only")
                    ),
                    source_verified=bool(
                        st.session_state.get("fusion_visual_source_verified", True)
                    ),
                )
                if finalization.report.unresolved_conflict_count:
                    st.session_state["fusion_finalized_script_pending_review"] = finalization.script
                    st.session_state.pop("video_clip_json", None)
                    st.error("存在待审阅的证据冲突，剪辑脚本不会进入可渲染状态。")
                    st.stop()
            script = json.dumps(narration_items, ensure_ascii=False, indent=2)

            if script is None:
                st.error(tr("Script generation failed check logs"))
                st.stop()
            logger.success(f"剪辑脚本生成完成")
            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)
            if not visual_evidence:
                st.session_state["fusion_visual_regression_only"] = False
            update_progress(90, tr("Preparing output..."))

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text(tr("Script generation completed!"))
        st.success(tr("Video script generated successfully"))

    except FusionPlanRecoveryRequired as err:
        st.session_state["fusion_plan_recovery"] = err.to_dict()
        st.warning(str(err))
        logger.warning(
            f"Fusion Segment Plan waiting for creator review: {err.attempt_id}"
        )
    except Exception as err:
        st.error(f"{tr('Generation error')}: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
        stream_text.empty()

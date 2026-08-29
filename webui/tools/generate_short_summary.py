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
from app.services.fusion_script_pipeline import FusionScriptPipeline
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
) -> dict:
    """Generate and validate a creator-approvable Fusion Segment Plan."""
    plan_raw = analyzer.plan_narration_segments(
        short_name=short_name,
        plot_analysis=plot_analysis,
        subtitle_content=subtitle_content,
        narration_copy=narration_copy,
        narration_language=narration_language,
        drama_genre=drama_genre,
        visual_evidence=visual_evidence,
        highlight_candidates=highlight_candidates,
        temperature=temperature,
    )
    plan = parse_and_fix_json(plan_raw)
    if not isinstance(plan, dict):
        raise ValueError("Fusion Segment Plan is not valid JSON")
    pipeline = FusionScriptPipeline()
    pipeline.validate_plan(narration_copy, plan)
    continuity_report = pipeline.validate_continuity(narration_copy, plan)
    if not continuity_report.is_renderable:
        repaired_raw = analyzer.repair_fusion_segment_plan(
            plan_payload=json.dumps(plan, ensure_ascii=False),
            continuity_findings=json.dumps(continuity_report.to_dict(), ensure_ascii=False),
            subtitle_content=subtitle_content,
            visual_evidence=visual_evidence,
            highlight_candidates=highlight_candidates,
            temperature=temperature,
        )
        repaired_plan = parse_and_fix_json(repaired_raw)
        if not isinstance(repaired_plan, dict):
            raise ValueError("Fusion Segment Plan repair is not valid JSON")
        pipeline.validate_plan(narration_copy, repaired_plan)
        continuity_report = pipeline.validate_continuity(narration_copy, repaired_plan)
        if not continuity_report.is_renderable:
            messages = "; ".join(finding.message for finding in continuity_report.findings)
            raise ValueError(f"Fusion Segment Plan lacks narrative continuity after repair: {messages}")
        plan = repaired_plan
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
    is_cancelled=None,
) -> dict:
    """Match each approved plan entry against a bounded Evidence Window."""
    approval_source_identity = (
        plan_approval.get("source_video_identity") if isinstance(plan_approval, dict) else None
    )
    if not _has_valid_fusion_plan_approval(
        plan_approval, plan_payload, narration_copy, approval_source_identity
    ):
        raise ValueError("Fusion Segment Plan requires creator approval before matching")
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
            )
            if response.get("status") != "success":
                raise RuntimeError(str(response.get("message") or "segment matching failed"))
            parsed = parse_and_fix_json(str(response.get("narration_script") or ""))
            if not isinstance(parsed, dict):
                raise ValueError("segment matching returned invalid JSON")
            return parsed

        def repair_transition(self, repair_request):
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
                previous_script=json.dumps(repair_request.previous_response, ensure_ascii=False),
                continuity_finding=(
                    f"{repair_request.previous_segment_id} -> {repair_request.next_segment_id}: "
                    f"{repair_request.time_range}"
                ),
                subtitle_content=repair_request.subtitle_evidence,
                visual_evidence=repair_request.visual_evidence,
                highlight_candidates=repair_request.highlight_candidates,
                core_window=str(segment.get("core_window") or ""),
                temperature=temperature,
                narration_language=narration_language,
                drama_genre=drama_genre,
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
        is_cancelled=is_cancelled,
    )
    return {
        "items": [
            {key: value for key, value in item.items() if key != "_segment_id"}
            for item in result.items
        ],
        "evidence_conflicts": result.evidence_conflicts,
        "continuity_report": result.continuity_report.to_dict(),
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
        return {
            "status": "blocked_for_continuity_review",
            "original_script": list(matched_plan.get("items") or []),
            "finalized_script": [],
            "finalization_report": {},
            "evidence_conflicts": matched_plan.get("evidence_conflicts", []),
            "continuity_report": continuity_report,
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
    return {
        "original_script": finalization.original_script,
        "finalized_script": finalization.script,
        "finalization_report": asdict(finalization.report),
        "evidence_conflicts": finalization.evidence_conflicts,
        "continuity_report": continuity_report,
        "renderable": not finalization.report.unresolved_conflict_count,
    }


def _fusion_matching_task_store() -> LocalAnalysisTaskStore:
    return LocalAnalysisTaskStore(Path(utils.task_dir("fusion_matching")))


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
    completed = list(task.get("completed_batches") or [])
    store.update(task_id, status="queued", cancel_requested=False, error_message="")
    _start_fusion_matching_runner(store, task_id, request, completed)


def fusion_matching_task_status(task_id: str) -> dict:
    return _fusion_matching_task_store().read(task_id)


def find_fusion_matching_task(
    *, source_identity: dict | None, plan_payload: dict, narration_copy: str
) -> dict | None:
    request = {"plan_payload": plan_payload, "narration_copy": narration_copy}
    return _fusion_matching_task_store().find_latest_for_source(
        source_identity or {},
        _fusion_matching_signature(request),
        include_completed=True,
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

        def update_segment_status(
            segment_id, status, *, response=None, error_message="", attempts=None,
            repair_attempts=None,
        ):
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
            update_segment_status(segment_request.segment_id, "running")

        def checkpoint_segment(segment_request, response):
            checkpoint({
                "batch_index": segment_request.segment_id,
                "segment_id": segment_request.segment_id,
                "status": "succeeded",
                "response": response,
            })
            completed_responses[segment_request.segment_id] = response
            update_segment_status(segment_request.segment_id, "succeeded", response=response)
            progress(
                15 + (len(completed_responses) / segment_count) * 75,
                f"正在匹配剪辑段落 ({len(completed_responses)}/{segment_count})...",
            )

        def checkpoint_failure(segment_request, error):
            checkpoint({
                "batch_index": segment_request.segment_id,
                "segment_id": segment_request.segment_id,
                "status": "failed",
                "error_message": str(error),
            })
            update_segment_status(segment_request.segment_id, "failed", error_message=str(error))

        matching_request = {
            key: value
            for key, value in request.items()
            if key not in {"analysis_signature", "finalization_context", "resume_snapshot"}
        }
        matched = match_approved_fusion_segment_plan(
            analyzer=analyzer,
            completed_segment_results=completed_responses,
            resume_snapshot=persisted_snapshot,
            on_segment_started=mark_segment_started,
            on_segment_complete=checkpoint_segment,
            on_segment_failed=checkpoint_failure,
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
        store.update(task_id, matching_snapshot=snapshot)
        progress(92, "正在执行剪辑脚本最终校验...")
        finalization = finalize_fusion_matching_result(
            matched_plan=matched,
            finalization_context=request["finalization_context"],
        )
        return {"matched_plan": matched, "finalization": finalization, "renderable": finalization["renderable"]}

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

    except Exception as err:
        st.error(f"{tr('Generation error')}: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
        stream_text.empty()

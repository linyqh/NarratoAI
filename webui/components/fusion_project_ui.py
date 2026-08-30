"""Project-centered Streamlit surface for Film Vision Fusion."""

from __future__ import annotations

from html import escape
from pathlib import Path
import json
from uuid import uuid4

import streamlit as st

from app.services.fusion_projects import FusionProjectStore, STAGES, project_projection
from app.utils import utils
from webui.fusion_navigation import (
    LEGACY_MODES_ROUTE,
    NEW_PROJECT_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    PROJECT_WORKSPACE_ROUTE,
    TASK_CENTER_ROUTE,
    navigate,
)


STAGE_LABELS = {
    "setup": "项目设置",
    "evidence": "媒体与证据",
    "narration": "解说词与叙事地图",
    "matching": "画面匹配",
    "review": "审核",
    "output": "输出",
}


def project_store() -> FusionProjectStore:
    return FusionProjectStore(Path(utils.storage_dir("fusion_projects", create=True)))


def _theme() -> None:
    st.markdown(
        """
        <style>
        .stApp { background:#07090d; color:#f5f7fb; }
        [data-testid="stHeader"] { background:#0d1117; border-bottom:1px solid #2a3038; }
        .fusion-shell { max-width:1540px; margin:0 auto; padding:8px 4px 28px; }
        .fusion-card { background:#14171c; border:1px solid #303640; border-radius:14px;
                       padding:18px; min-height:178px; margin-bottom:12px; }
        .fusion-kicker { color:#69a0ff; font-weight:700; font-size:12px; letter-spacing:.08em; }
        .fusion-title { color:#f7f8fb; font-size:22px; font-weight:760; margin:8px 0; }
        .fusion-meta { color:#9aa3af; font-size:13px; line-height:1.65; }
        .fusion-status { display:inline-block; background:#172744; color:#70a5ff;
                         padding:4px 9px; border-radius:999px; font-size:12px; }
        div[data-testid="stForm"], div[data-testid="stExpander"] {
            background:#14171c; border-color:#303640; border-radius:12px;
        }
        .stButton > button { background:#171b22; color:#eef2f8; border:1px solid #353d48; }
        .stButton > button p { color:inherit; }
        .stButton > button:hover { border-color:#5d8ff4; color:#8bb2ff; }
        .stButton > button:disabled { background:#11151a; color:#697381; border-color:#252b33; }
        .stButton > button[kind="primary"] { background:#4f83f1; color:white; border-color:#4f83f1; }
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
        [data-baseweb="select"] > div { background:#11151a; color:#eef2f8; border-color:#353d48; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_project_app(tr=lambda key: key) -> None:
    _theme()
    if st.session_state.pop("fusion_legacy_redirect_notice", False):
        st.info("Film Vision Fusion 已迁移到项目工作区；旧设置页不再承载新的 Fusion 流程。")
    route = st.session_state.get("fusion_ui_route", PROJECT_LIBRARY_ROUTE)
    if route == NEW_PROJECT_ROUTE:
        _render_new_project()
    elif route == PROJECT_WORKSPACE_ROUTE:
        _render_workspace()
    elif route == TASK_CENTER_ROUTE:
        _render_task_center()
    else:
        _render_library()


def _top_bar(*, project: dict | None = None) -> None:
    left, middle, tasks, legacy = st.columns([4, 2, 1.2, 1.4], vertical_alignment="center")
    with left:
        st.markdown(
            f"### Narrato<span style='color:#61d68b'>AI</span>"
            + (f" · {project['name']}" if project else ""),
            unsafe_allow_html=True,
        )
    with middle:
        if project:
            st.caption("已自动保存 · 本地项目")
    with tasks:
        if st.button("任务中心", use_container_width=True):
            navigate(st.session_state, TASK_CENTER_ROUTE)
            st.rerun()
    with legacy:
        if st.button("传统模式", use_container_width=True):
            navigate(st.session_state, LEGACY_MODES_ROUTE)
            st.rerun()
    st.divider()


def _render_library() -> None:
    _top_bar()
    store = project_store()
    header, create = st.columns([5, 1.2], vertical_alignment="center")
    with header:
        st.title("项目库")
        st.caption("创建、继续和审核 Film Vision Fusion 电影解说项目")
    with create:
        if st.button("＋ 新建项目", type="primary", use_container_width=True):
            project = store.create("未命名电影解说")
            navigate(st.session_state, NEW_PROJECT_ROUTE, project_id=project["project_id"])
            st.rerun()

    search_col, filter_col, sort_col = st.columns([3, 1.2, 1.2])
    search = search_col.text_input("搜索项目", placeholder="输入项目名称…", label_visibility="collapsed")
    status_filter = filter_col.selectbox(
        "状态", ["全部", "进行中", "等待审核", "已完成", "已归档", "回收站"], label_visibility="collapsed"
    )
    sort = sort_col.selectbox(
        "排序", ["最近更新", "最早创建", "名称"], label_visibility="collapsed"
    )

    projects = store.list_projects(include_trashed=status_filter == "回收站")
    cards = []
    for project in projects:
        projection = project_projection(project)
        if search and search.lower() not in str(project.get("name") or "").lower():
            continue
        if status_filter == "回收站" and projection["status"] != "trashed":
            continue
        if status_filter == "进行中" and projection["status"] not in {"running", "draft"}:
            continue
        if status_filter == "等待审核" and projection["status"] not in {"waiting_for_review", "blocked"}:
            continue
        if status_filter == "已完成" and projection["status"] != "completed":
            continue
        if status_filter == "已归档" and projection["status"] != "archived":
            continue
        cards.append((project, projection))
    if sort == "最早创建":
        cards.sort(key=lambda item: str(item[0].get("created_at") or ""))
    elif sort == "名称":
        cards.sort(key=lambda item: str(item[0].get("name") or "").lower())

    if not cards:
        st.info("还没有符合条件的项目。点击“新建项目”开始第一条电影解说。")
        return
    columns = st.columns(3)
    for index, (project, projection) in enumerate(cards):
        with columns[index % 3]:
            st.markdown(
                "<div class='fusion-card'>"
                f"<div class='fusion-kicker'>FILM VISION FUSION</div>"
                f"<div class='fusion-title'>{escape(str(project['name']))}</div>"
                f"<span class='fusion-status'>{escape(str(projection['status']))}</span>"
                f"<div class='fusion-meta'>阶段：{escape(str(STAGE_LABELS.get(projection['active_stage'], projection['active_stage'])))}<br>"
                f"待审核：{projection['review_count']} · 运行任务：{projection['running_task_count']}<br>"
                f"下一步：{escape(str(projection['next_action']))}</div></div>",
                unsafe_allow_html=True,
            )
            if st.button("打开项目", key=f"open-{project['project_id']}", use_container_width=True):
                navigate(st.session_state, PROJECT_WORKSPACE_ROUTE, project_id=project["project_id"])
                st.rerun()
            with st.expander("项目操作"):
                renamed = st.text_input("重命名", value=project["name"], key=f"rename-{project['project_id']}")
                actions = st.columns(3)
                if actions[0].button("保存名称", key=f"save-name-{project['project_id']}"):
                    store.rename(project["project_id"], renamed)
                    st.rerun()
                if projection["status"] == "trashed":
                    if actions[1].button("恢复", key=f"restore-{project['project_id']}"):
                        store.restore(project["project_id"])
                        st.rerun()
                elif projection["status"] == "archived":
                    if actions[1].button("取消归档", key=f"unarchive-{project['project_id']}"):
                        store.unarchive(project["project_id"])
                        st.rerun()
                elif actions[1].button("归档", key=f"archive-{project['project_id']}"):
                    store.archive(project["project_id"])
                    st.rerun()
                if projection["status"] != "trashed" and actions[2].button("移到回收站", key=f"trash-{project['project_id']}"):
                    store.trash(project["project_id"])
                    st.rerun()


def _render_new_project() -> None:
    store = project_store()
    project_id = str(st.session_state.get("fusion_project_id") or "")
    if not project_id:
        navigate(st.session_state, PROJECT_LIBRARY_ROUTE)
        st.rerun()
    project = store.reconcile_for_runtime(project_id)
    _top_bar(project=project)
    if st.button("← 返回项目库"):
        navigate(st.session_state, PROJECT_LIBRARY_ROUTE)
        st.rerun()
    st.title("新建 Film Vision Fusion 项目")
    left, right = st.columns([0.85, 1.6], gap="large")
    with left:
        st.subheader("剪辑配置")
        name = st.text_input("项目名称", value=project["name"])
        settings = dict(project.get("project_settings") or {})
        language = st.selectbox("输出语言", ["简体中文（中国）", "繁體中文", "English"], index=0)
        style = st.selectbox("解说风格", ["剧情解说", "悬疑推进", "人物成长", "冷静分析"])
        target = st.number_input("目标文案字数", min_value=300, max_value=10000, value=int(settings.get("target_narration_length") or 1200), step=100)
        ratio = st.slider("原片声音比例", 0, 100, int(settings.get("original_sound_ratio") or 30), 5)
        subtitle_policy = st.selectbox("字幕策略", ["source_or_asr", "source_only", "asr_if_missing"])
        voice_profile = st.text_input("TTS 音色", value=str(settings.get("voice_profile") or ""))
        background_music = st.text_input("背景音乐路径（可选）", value=str(settings.get("background_music") or ""))
        output_format = st.selectbox("输出格式", ["mp4", "mkv"], index=0)
        if st.button("保存配置", use_container_width=True):
            settings.update(
                output_language=language,
                commentary_style=style,
                target_narration_length=int(target),
                original_sound_ratio=int(ratio),
                subtitle_policy=subtitle_policy,
                voice_profile=voice_profile,
                background_music=background_music,
                output_format=output_format,
            )
            project = store.update(project_id, name=name, project_settings=settings)
            st.success("配置已保存")
    with right:
        st.subheader("源视频")
        st.caption("可引用本机文件，也可上传为项目托管素材；删除项目不会触碰本机引用文件。")
        local_path = st.text_input("本机视频路径", placeholder="D:\\Movies\\example.mp4")
        subtitle_path = st.text_input("字幕路径（SRT，可稍后补充）", placeholder="D:\\Movies\\example.srt")
        if st.button("添加本机视频", disabled=not local_path, use_container_width=True):
            store.add_local_reference(project_id, path=local_path, subtitle_path=subtitle_path)
            st.rerun()
        upload = st.file_uploader("上传视频为项目托管素材", type=["mp4", "mkv", "mpeg", "mpg", "3gp"])
        if st.button("保存上传素材", disabled=upload is None, use_container_width=True):
            store.add_managed_asset(
                project_id,
                filename=upload.name,
                content=upload.getvalue(),
                subtitle_path=subtitle_path,
            )
            st.rerun()
        if st.button("重新检测素材状态", use_container_width=True):
            store.refresh_source_availability(project_id)
            st.rerun()
        for source in project.get("source_video_sequence") or []:
            state = "可用" if source.get("available") else "离线 / 路径不可用"
            st.markdown(
                f"<div class='fusion-card'><b>{escape(str(source.get('title') or source.get('path')))}</b>"
                f"<div class='fusion-meta'>{escape(state)}<br>{escape(str(source.get('path')))}</div></div>",
                unsafe_allow_html=True,
            )
    st.divider()
    ready = bool(project.get("source_video_sequence"))
    if st.button("继续到媒体与证据 →", type="primary", disabled=not ready, use_container_width=True):
        store.update(project_id, active_stage="evidence")
        navigate(st.session_state, PROJECT_WORKSPACE_ROUTE, project_id=project_id)
        st.rerun()


def _render_workspace() -> None:
    store = project_store()
    project_id = str(st.session_state.get("fusion_project_id") or "")
    if not project_id:
        navigate(st.session_state, PROJECT_LIBRARY_ROUTE)
        st.rerun()
    project = store.reconcile_for_runtime(project_id)
    projection = project_projection(project)
    _top_bar(project=project)
    back, status = st.columns([1, 5], vertical_alignment="center")
    if back.button("← 项目库", use_container_width=True):
        navigate(st.session_state, PROJECT_LIBRARY_ROUTE)
        st.rerun()
    status.markdown(f"状态：`{projection['status']}` · 下一步：{projection['next_action']}")
    current = project.get("active_stage") if project.get("active_stage") in STAGES else "setup"
    stage = st.radio(
        "项目阶段",
        STAGES,
        index=STAGES.index(current),
        format_func=lambda value: STAGE_LABELS[value],
        horizontal=True,
        label_visibility="collapsed",
    )
    if stage != current:
        project = store.update(project_id, active_stage=stage)
    renderers = {
        "setup": _stage_setup,
        "evidence": _stage_evidence,
        "narration": _stage_narration,
        "matching": _stage_matching,
        "review": _stage_review,
        "output": _stage_output,
    }
    renderers[stage](project, store)


def _stage_setup(project, store) -> None:
    st.header("项目设置")
    st.json(project.get("project_settings") or {}, expanded=False)
    if st.button("编辑项目配置"):
        navigate(st.session_state, NEW_PROJECT_ROUTE, project_id=project["project_id"])
        st.rerun()


def _stage_evidence(project, store) -> None:
    st.header("媒体与证据")
    sources = project.get("source_video_sequence") or []
    if not sources:
        st.warning("请先添加至少一个源视频。")
        return
    for source in sources:
        st.markdown(f"#### {source.get('title') or source.get('path')}")
        a, b, c = st.columns(3)
        a.metric("文件状态", "可用" if source.get("available") else "离线")
        b.metric("字幕", source.get("subtitle_status", "missing"))
        c.metric("视觉证据", source.get("visual_evidence_status", "not_started"))
        if source.get("available"):
            interval = st.number_input(
                "关键帧间隔（秒）", min_value=2.0, max_value=60.0, value=6.0,
                key=f"interval-{source['source_id']}",
            )
            batch = st.number_input(
                "每批帧数", min_value=1, max_value=20, value=8,
                key=f"batch-{source['source_id']}",
            )
            custom_prompt = st.text_area(
                "视觉分析提示词",
                value="按时间顺序记录画面中可见的人物、动作、地点、物体和场景变化；不要推断声音、对白或动机。",
                key=f"prompt-{source['source_id']}",
            )
            estimate_col, start_col = st.columns(2)
            if estimate_col.button("估算完整分析", key=f"estimate-{source['source_id']}"):
                try:
                    from webui.tools.generate_film_vision_fusion import estimate_local_visual_analysis

                    estimate = estimate_local_visual_analysis(source["path"], interval, int(batch))
                    st.session_state[f"estimate-result-{source['source_id']}"] = {
                        "关键帧": estimate.keyframe_count,
                        "请求数": estimate.request_count,
                        "预计分钟": estimate.estimated_minutes,
                    }
                except Exception as error:
                    st.error(f"无法估算：{error}")
            estimate_result = st.session_state.get(f"estimate-result-{source['source_id']}")
            if estimate_result:
                st.json(estimate_result, expanded=False)
            start_projection = store.task_start_projection(
                project["project_id"], kind="visual_analysis", source_id=source["source_id"]
            )
            if start_projection["reason"]:
                st.caption(start_projection["reason"])
            if start_col.button(
                "开始视觉分析", type="primary", key=f"start-{source['source_id']}",
                disabled=not start_projection["allowed"],
            ):
                try:
                    from webui.tools.generate_film_vision_fusion import start_local_visual_analysis

                    task_id = start_local_visual_analysis(
                        video_path=source["path"],
                        video_theme=project["name"],
                        custom_prompt=custom_prompt,
                        frame_interval_seconds=float(interval),
                        vision_batch_size=int(batch),
                    )
                    store.attach_task(
                        project["project_id"], task_id=task_id,
                        kind="visual_analysis", source_id=source["source_id"],
                        input_version_id=project.get("active_version_id") or "setup",
                    )
                    st.rerun()
                except Exception as error:
                    st.error(f"无法开始视觉分析：{error}")

    visual_tasks = [task for task in project.get("task_refs") or [] if task.get("kind") == "visual_analysis"]
    for task_ref in visual_tasks:
        try:
            from webui.tools.generate_film_vision_fusion import (
                cancel_local_visual_analysis,
                local_visual_analysis_status,
                resume_local_visual_analysis,
            )

            task = local_visual_analysis_status(task_ref["task_id"])
            store.update_task_summary(
                project["project_id"], task_ref["task_id"],
                status=task.get("status"), progress=task.get("progress"),
                message=task.get("message"), error_message=task.get("error_message", ""),
            )
            st.progress(float(task.get("progress") or 0) / 100.0, text=str(task.get("message") or task.get("status")))
            actions = st.columns(3)
            if actions[0].button("继续", key=f"resume-visual-{task_ref['task_id']}", disabled=task.get("status") not in {"failed", "interrupted"}):
                resume_local_visual_analysis(task_ref["task_id"])
                st.rerun()
            if actions[1].button("取消", key=f"cancel-visual-{task_ref['task_id']}", disabled=task.get("status") not in {"queued", "running"}):
                cancel_local_visual_analysis(task_ref["task_id"])
                st.rerun()
            if actions[2].button("查看诊断", key=f"diag-visual-{task_ref['task_id']}"):
                st.json({key: task.get(key) for key in ("status", "progress", "message", "error_message")})
            if task.get("status") == "completed" and task.get("visual_evidence"):
                source_state = next(
                    (
                        source for source in project.get("source_video_sequence") or []
                        if source.get("source_id") == task_ref.get("source_id")
                    ),
                    {},
                )
                if source_state.get("visual_evidence_status") != "completed":
                    project = store.attach_source_visual_evidence(
                        project["project_id"],
                        source_id=task_ref.get("source_id"),
                        evidence=task["visual_evidence"],
                        artifact_path=task.get("artifact_path") or "",
                    )
        except Exception as error:
            st.warning(f"任务状态不可用：{error}")


def _stage_narration(project, store) -> None:
    st.header("解说词与 Narrative Map")
    artifacts = project.get("artifact_refs") or {}
    if not artifacts.get("visual_evidence"):
        st.warning("需要先完成或导入视觉证据。现有证据不会因页面切换而丢失。")
    sources = project.get("source_video_sequence") or []
    subtitle_paths = [source.get("subtitle_path") for source in sources if source.get("subtitle_path")]
    narration_start = store.task_start_projection(
        project["project_id"], kind="narration_generation"
    )
    if narration_start["reason"]:
        st.caption(narration_start["reason"])
    if st.button(
        "生成解说词", type="primary",
        disabled=not subtitle_paths or not narration_start["allowed"],
    ):
        task_id = f"narration{uuid4().hex}"
        store.attach_task(
            project["project_id"], task_id=task_id, kind="narration_generation",
            input_version_id=project.get("active_version_id") or "setup", status="running",
        )
        try:
            from webui.tools.generate_short_summary import (
                FILM_TV_PROMPT_CATEGORY,
                generate_short_drama_narration_copy,
            )

            result = generate_short_drama_narration_copy(
                subtitle_path=subtitle_paths,
                video_theme=project["name"],
                temperature=0.3,
                video_paths=[source.get("path") for source in sources],
                narration_language=(project.get("project_settings") or {}).get("output_language", "简体中文（中国）"),
                drama_genre=(project.get("project_settings") or {}).get("commentary_style", "剧情解说"),
                prompt_category=FILM_TV_PROMPT_CATEGORY,
                narration_word_count=int((project.get("project_settings") or {}).get("target_narration_length", 1200)),
                visual_evidence=str(artifacts.get("visual_evidence") or ""),
            )
            if result:
                artifacts = dict(artifacts)
                artifacts.update(
                    narration_draft=result["narration_copy"],
                    plot_analysis=result["plot_analysis"],
                    subtitle_content=result["subtitle_content"],
                )
                project = store.update(project["project_id"], artifact_refs=artifacts)
                store.update_task_summary(
                    project["project_id"], task_id, status="completed", progress=100,
                    message="解说词已生成并保存为待审核草稿",
                )
                st.rerun()
        except Exception as error:
            store.update_task_summary(
                project["project_id"], task_id, status="failed",
                error_message=str(error), failure_category=_failure_category(error),
                recoverable=True,
            )
            st.error(f"解说词生成未完成：{error}")
    draft = st.text_area("解说词草稿", value=str(artifacts.get("narration_draft") or artifacts.get("narration") or ""), height=280)
    if st.button("保存为 Content Draft", use_container_width=True):
        saved = store.save_content_draft(project["project_id"], kind="narration", content=draft)
        st.session_state["fusion_pending_draft_id"] = saved["draft_id"]
        st.success("草稿已保存；尚未影响下游版本。")
    pending_id = st.session_state.get("fusion_pending_draft_id")
    if pending_id:
        try:
            impact = store.preview_draft_impact(project["project_id"], pending_id)
            st.warning(f"应用后将失效：{', '.join(impact['invalidated_artifacts']) or '无下游产物'}")
            if st.button("确认影响并应用草稿", type="primary"):
                store.apply_content_draft(project["project_id"], pending_id, impact_confirmed=True)
                st.session_state.pop("fusion_pending_draft_id", None)
                st.rerun()
        except ValueError:
            st.session_state.pop("fusion_pending_draft_id", None)


def _stage_matching(project, store) -> None:
    st.header("画面匹配")
    artifacts = dict(project.get("artifact_refs") or {})
    narration = str(artifacts.get("narration") or "")
    if not narration:
        st.warning("请先在“解说词与 Narrative Map”阶段应用解说词草稿。")
        return
    plan_store = _plan_attempt_store(project["project_id"])
    attempts = plan_store.list_attempts()
    if attempts:
        st.caption(f"已保存 {len(attempts)} 次 Plan Attempt；失败输出不会覆盖成功版本。")
        with st.expander("Plan Attempt 诊断"):
            st.dataframe(
                [
                    {
                        "类型": item.get("kind"), "状态": item.get("status"),
                        "字符数": item.get("received_characters"),
                        "问题数": len(item.get("findings") or []),
                        "时间": item.get("updated_at"),
                    }
                    for item in attempts
                ],
                use_container_width=True, hide_index=True,
            )
    plan_start = store.task_start_projection(project["project_id"], kind="fusion_plan")
    stream = st.empty()
    if st.button(
        "生成 Fusion Segment Plan", type="primary",
        disabled=not plan_start["allowed"],
    ):
        plan_task_id = f"fusionplan{uuid4().hex}"
        store.attach_task(
            project["project_id"], task_id=plan_task_id, kind="fusion_plan",
            input_version_id=project.get("active_version_id") or "", status="running",
        )
        try:
            from webui.tools.generate_short_summary import create_fusion_segment_plan

            analyzer, provider, model = _text_analyzer()
            plan = create_fusion_segment_plan(
                analyzer=analyzer,
                short_name=project["name"],
                plot_analysis=str(artifacts.get("plot_analysis") or ""),
                subtitle_content=str(artifacts.get("subtitle_content") or ""),
                narration_copy=narration,
                narration_language=str((project.get("project_settings") or {}).get("output_language") or "简体中文（中国）"),
                drama_genre=str((project.get("project_settings") or {}).get("commentary_style") or "剧情解说"),
                visual_evidence=str(artifacts.get("visual_evidence") or ""),
                highlight_candidates=str(artifacts.get("highlight_candidates") or ""),
                temperature=0.3,
                stream_callback=lambda event: stream.info(
                    f"模型正在生成计划：{str((event or {}).get('text') or '')[-600:]}"
                ),
                attempt_store=plan_store,
                attempt_context={
                    "provider": provider, "model": model,
                    "input_fingerprint": project.get("active_version_id") or "setup",
                },
            )
            artifacts["fusion_segment_plan_draft"] = plan
            artifacts["fusion_plan_attempts"] = _safe_attempt_summaries(plan_store)
            project = store.update(project["project_id"], artifact_refs=artifacts)
            store.update_task_summary(
                project["project_id"], plan_task_id, status="completed", progress=100,
                message="分段计划已生成，等待审核批准",
            )
            st.rerun()
        except Exception as error:
            recovery = getattr(error, "to_dict", lambda: {})()
            artifacts["fusion_plan_attempts"] = _safe_attempt_summaries(plan_store)
            store.update(project["project_id"], artifact_refs=artifacts)
            store.update_task_summary(
                project["project_id"], plan_task_id, status="failed",
                error_message=str(error), failure_category=_failure_category(error),
                recoverable=True,
            )
            st.error(str(recovery.get("message") or f"分段计划未完成：{error}"))
            if recovery.get("findings"):
                st.dataframe(recovery["findings"], use_container_width=True, hide_index=True)

    draft_plan = artifacts.get("fusion_segment_plan_draft") or artifacts.get("fusion_segment_plan")
    if draft_plan:
        editor = st.text_area(
            "结构化计划编辑器",
            value=json.dumps(draft_plan, ensure_ascii=False, indent=2),
            height=320,
            key=f"plan-editor-{project['project_id']}-{project.get('active_version_id')}",
        )
        if st.button("验证并批准 Plan", type="primary"):
            try:
                from app.services.fusion_script_pipeline import FusionScriptPipeline
                from webui.tools.generate_short_summary import approve_fusion_segment_plan

                edited = json.loads(editor)
                pipeline = FusionScriptPipeline()
                validation = pipeline.validate_plan_findings(narration, edited)
                if not validation.is_valid:
                    raise ValueError("；".join(item.message for item in validation.findings))
                continuity = pipeline.validate_continuity(narration, edited)
                if not continuity.is_renderable:
                    raise ValueError("；".join(item.message for item in continuity.findings))
                identity = _project_source_identity(project)
                approval = approve_fusion_segment_plan(
                    plan_payload=edited, narration_copy=narration, source_identity=identity
                )
                artifacts.update(
                    fusion_segment_plan=edited,
                    fusion_segment_plan_draft=edited,
                    fusion_plan_approval=approval,
                )
                store.update(project["project_id"], artifact_refs=artifacts)
                st.success("Plan 已通过结构与连续性校验并完成批准。")
                st.rerun()
            except Exception as error:
                st.error(f"Plan 仍不能批准：{error}")

    approved_plan = artifacts.get("fusion_segment_plan")
    approval = artifacts.get("fusion_plan_approval")
    matching_projection = store.task_start_projection(
        project["project_id"], kind="fusion_matching"
    )
    if st.button(
        "开始分段画面匹配", type="primary",
        disabled=not approved_plan or not approval or not matching_projection["allowed"],
    ):
        try:
            from app.utils.video_processor import VideoProcessor
            from webui.tools.generate_short_summary import start_fusion_matching_task

            sources = [source for source in project.get("source_video_sequence") or [] if source.get("available")]
            source_identity = _project_source_identity(project)
            source_durations = {
                Path(source["path"]).name: VideoProcessor(source["path"]).duration
                for source in sources
            }
            task_id = start_fusion_matching_task(
                short_name=project["name"], narration_copy=narration,
                narration_language=str((project.get("project_settings") or {}).get("output_language") or "简体中文（中国）"),
                drama_genre=str((project.get("project_settings") or {}).get("commentary_style") or "剧情解说"),
                original_sound_ratio=int((project.get("project_settings") or {}).get("original_sound_ratio") or 30),
                subtitle_content=str(artifacts.get("subtitle_content") or ""),
                visual_evidence=str(artifacts.get("visual_evidence") or ""),
                highlight_candidates=str(artifacts.get("highlight_candidates") or ""),
                plan_payload=approved_plan, plan_approval=approval, temperature=0.3,
                source_identity=source_identity,
                finalization_context={
                    "candidate_payloads": artifacts.get("highlight_candidate_items") or [],
                    "candidate_rejections": artifacts.get("highlight_candidate_rejections") or [],
                    "original_sound_ratio": int((project.get("project_settings") or {}).get("original_sound_ratio") or 30),
                    "source_identity": source_identity,
                    "source_durations": source_durations,
                },
            )
            store.attach_task(
                project["project_id"], task_id=task_id, kind="fusion_matching",
                input_version_id=project.get("active_version_id") or "", status="queued",
            )
            st.rerun()
        except Exception as error:
            st.error(f"无法开始画面匹配：{error}")

    matching = next(
        (task for task in reversed(project.get("task_refs") or []) if task.get("kind") == "fusion_matching"),
        None,
    )
    if matching:
        _render_matching_task(project, store, matching)
    st.caption("未经验证和 Plan Approval 的计划不能开始匹配。")


def _stage_review(project, store) -> None:
    st.header("审核工作区")
    _render_narrative_map_checkpoint(project, store)
    artifacts = project.get("artifact_refs") or {}
    task_id = str(artifacts.get("fusion_matching_task_id") or "")
    task = {}
    if task_id:
        try:
            from webui.tools.generate_short_summary import fusion_matching_task_status

            task = fusion_matching_task_status(task_id)
        except Exception:
            task = {}
    finalization = (
        task.get("finalization")
        if isinstance(task.get("finalization"), dict)
        else artifacts.get("finalization") or {}
    )
    if not finalization:
        st.info("完成画面匹配后，审核队列、视频、时间线和证据会在这里联动。")
        return
    from app.services.fusion_workspace import (
        project_fusion_review_context,
        project_fusion_workspace,
    )

    workspace = project_fusion_workspace(task=task, finalization=finalization)
    findings = workspace.get("review_queue") or []
    left, center, right = st.columns([0.85, 1.6, 1.05], gap="medium")
    selected_finding = None
    with left:
        st.subheader("审核队列")
        if findings:
            selected_index = st.selectbox(
                "选择审核项",
                list(range(len(findings))),
                format_func=lambda index: (
                    f"{findings[index].get('kind')} · "
                    f"{findings[index].get('code') or findings[index].get('message') or '待审核'}"
                ),
            )
            selected_finding = findings[selected_index]
            st.json(
                {
                    key: selected_finding.get(key)
                    for key in ("kind", "code", "message", "severity", "segment_id", "time_range")
                    if selected_finding.get(key) not in (None, "")
                },
                expanded=False,
            )
            _render_production_review_actions(
                project, store, task_id, task, selected_finding
            )
        else:
            st.success("当前没有待处理审核项")
        _render_review_undo(project, store, task_id, finalization)

    segment_id = str((selected_finding or {}).get("segment_id") or "")
    context = project_fusion_review_context(
        task=task, finalization=finalization, segment_id=segment_id
    ) if segment_id else {}
    with center:
        st.subheader("视频与时间线")
        if not selected_finding:
            st.info("选择审核项后，视频、时间线和 Story Beat 将同步定位。")
        elif not segment_id:
            st.warning("该问题没有可靠的 Segment 身份，已禁止猜测定位到其他画面。")
        else:
            _render_synchronized_video(project, finalization, context)
            if context.get("timeline_items"):
                st.dataframe(context["timeline_items"], use_container_width=True, hide_index=True)
                _render_timeline_editor(project, store, task_id, context)
    with right:
        st.subheader("证据与版本")
        if context:
            st.markdown("**Story Beat**")
            st.json(context.get("story_beat") or {}, expanded=False)
            st.markdown("**Subtitle Evidence**")
            st.text(context.get("subtitle_evidence") or "当前范围没有可定位字幕证据")
            st.markdown("**Visual Evidence**")
            st.text(context.get("visual_evidence") or "当前范围没有可定位视觉证据")
        _render_version_controls(project, store, task_id, finalization)


def _render_narrative_map_checkpoint(project: dict, store: FusionProjectStore) -> None:
    artifacts = project.get("artifact_refs") or {}
    finalization = artifacts.get("finalization") if isinstance(artifacts.get("finalization"), dict) else {}
    narrative_map = finalization.get("narrative_map") if isinstance(finalization.get("narrative_map"), dict) else {}
    if not narrative_map or narrative_map.get("approval_status") not in {"pending", ""}:
        return
    task_id = str(artifacts.get("fusion_matching_task_id") or "")
    if not task_id:
        st.error("Narrative Map 缺少项目任务绑定，不能安全批准。")
        return
    st.warning("Narrative Map 等待审核：批准、明确跳过，或先预览草稿影响。")
    beats_text = st.text_area(
        "Story Beats 草稿",
        value=json.dumps(narrative_map.get("beats") or [], ensure_ascii=False, indent=2),
        height=260,
        key=f"narrative-map-editor-{project['project_id']}-{project.get('active_version_id')}",
    )
    actions = st.columns(3)
    if actions[0].button("批准 Narrative Map", type="primary"):
        _apply_narrative_map_review(project, store, task_id, action="approved")
    if actions[1].button("明确跳过"):
        _apply_narrative_map_review(project, store, task_id, action="skipped")
    if actions[2].button("预览草稿影响"):
        try:
            from webui.tools.generate_short_summary import preview_fusion_narrative_map_review

            edited_beats = json.loads(beats_text)
            preview = preview_fusion_narrative_map_review(
                task_id, action="applied_draft", edited_beats=edited_beats
            )
            st.session_state[f"narrative-map-preview-{project['project_id']}"] = preview
        except Exception as error:
            st.error(f"无法预览 Narrative Map 草稿：{error}")
    preview = st.session_state.get(f"narrative-map-preview-{project['project_id']}")
    if preview:
        impact = preview.get("impact") or {}
        st.info(
            "将失效的 Segment Match："
            + (", ".join(impact.get("invalidates_segment_matches") or []) or "无")
        )
        if st.button("确认影响并应用 Narrative Map 草稿", type="primary"):
            _apply_narrative_map_review(
                project, store, task_id, action="applied_draft",
                edited_beats=preview.get("edited_beats") or [],
                fingerprint=preview.get("narrative_map_fingerprint"),
            )


def _apply_narrative_map_review(
    project: dict,
    store: FusionProjectStore,
    task_id: str,
    *,
    action: str,
    edited_beats: list[dict] | None = None,
    fingerprint: str | None = None,
) -> None:
    try:
        from webui.tools.generate_short_summary import review_fusion_narrative_map

        task = review_fusion_narrative_map(
            task_id,
            action=action,
            edited_beats=edited_beats,
            expected_narrative_map_fingerprint=fingerprint,
        )
        finalization = task.get("finalization") or {}
        store.sync_admitted_matching_state(
            project["project_id"], task_id=task_id, finalization=finalization
        )
        st.session_state.pop(f"narrative-map-preview-{project['project_id']}", None)
        st.rerun()
    except Exception as error:
        st.error(f"Narrative Map 审核未应用：{error}")


def _render_production_review_actions(
    project: dict,
    store: FusionProjectStore,
    task_id: str,
    task: dict,
    finding: dict,
) -> None:
    kind = str(finding.get("kind") or "")
    segment_id = str(finding.get("segment_id") or "")
    code = str(finding.get("code") or "")
    try:
        if kind == "evidence_conflict" and finding.get("conflict_key"):
            if st.button("确认已查看证据冲突", use_container_width=True):
                from webui.tools.generate_short_summary import acknowledge_fusion_evidence_conflict

                updated = acknowledge_fusion_evidence_conflict(
                    task_id, conflict_key=str(finding["conflict_key"])
                )
                _sync_matching_review(project, store, task_id, updated)
        elif kind == "quality" and segment_id and code:
            actions = st.columns(2)
            if actions[0].button("采纳并定向修复", use_container_width=True):
                from webui.tools.generate_short_summary import approve_fusion_quality_repair

                updated = approve_fusion_quality_repair(
                    task_id, segment_id=segment_id, finding_code=code
                )
                _sync_matching_review(project, store, task_id, updated)
            if actions[1].button("忽略建议", use_container_width=True):
                from webui.tools.generate_short_summary import ignore_fusion_quality_finding

                updated = ignore_fusion_quality_finding(
                    task_id, segment_id=segment_id, finding_code=code
                )
                _sync_matching_review(project, store, task_id, updated)
        else:
            reason = st.text_input("审核备注", key=f"review-note-{code}-{segment_id}")
            if st.button("记录已查看", use_container_width=True):
                store.record_review_decision(
                    project["project_id"],
                    finding_id=str(finding.get("finding_id") or code),
                    action="acknowledge",
                    reason=reason,
                )
                st.rerun()
    except Exception as error:
        st.error(f"审核操作未应用：{error}")


def _sync_matching_review(
    project: dict, store: FusionProjectStore, task_id: str, task: dict
) -> None:
    store.sync_admitted_matching_state(
        project["project_id"], task_id=task_id,
        finalization=task.get("finalization") or {},
    )
    st.rerun()


def _render_review_undo(
    project: dict, store: FusionProjectStore, task_id: str, finalization: dict
) -> None:
    decisions = list(finalization.get("review_decisions") or [])
    local_decisions = [
        item for item in project.get("review_decisions") or []
        if item.get("status") == "active"
    ]
    if not decisions and not local_decisions:
        return
    with st.expander("审核历史与撤销"):
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                continue
            label = (
                f"{decision.get('kind') or 'review'} · "
                f"{decision.get('action') or ''} · {decision.get('code') or decision.get('segment_id') or ''}"
            )
            st.caption(label)
            if st.button("撤销", key=f"undo-production-{index}-{decision.get('decision_id')}"):
                try:
                    kind = decision.get("kind")
                    action = decision.get("action")
                    if kind == "quality" and action == "ignored":
                        from webui.tools.generate_short_summary import undo_fusion_quality_ignore

                        updated = undo_fusion_quality_ignore(
                            task_id, decision_id=decision["decision_id"]
                        )
                    elif kind == "evidence_conflict" and action == "acknowledged":
                        from webui.tools.generate_short_summary import undo_fusion_evidence_conflict_acknowledgement

                        updated = undo_fusion_evidence_conflict_acknowledgement(
                            task_id, decision_id=decision["decision_id"]
                        )
                    elif kind == "preflight" and action == "warning_overridden":
                        from webui.tools.generate_short_summary import undo_fusion_render_warning_override

                        updated = undo_fusion_render_warning_override(
                            task_id, decision_id=decision["decision_id"]
                        )
                    else:
                        raise ValueError("该审核决定当前不能撤销")
                    _sync_matching_review(project, store, task_id, updated)
                except Exception as error:
                    st.error(f"无法撤销：{error}")
        for decision in local_decisions:
            st.caption(f"project review · {decision.get('action')} · {decision.get('finding_id')}")
            if st.button("撤销", key=f"undo-local-{decision['decision_id']}"):
                store.undo_review_decision(project["project_id"], decision["decision_id"])
                st.rerun()


def _render_synchronized_video(project: dict, finalization: dict, context: dict) -> None:
    from app.services.documentary.frame_analysis_models import TimeRange

    segment_id = str(context.get("segment_id") or "")
    timeline_item = next(
        (
            item for item in finalization.get("finalized_script") or []
            if isinstance(item, dict) and str(item.get("_segment_id") or "") == segment_id
        ),
        None,
    )
    if timeline_item is None:
        st.warning("该审核项没有可验证的时间线条目，未自动跳转视频。")
        return
    video_name = str(timeline_item.get("video_name") or "")
    source = next(
        (
            item for item in project.get("source_video_sequence") or []
            if video_name
            and video_name in {str(item.get("title") or ""), Path(str(item.get("path") or "")).name}
        ),
        None,
    )
    if source is None or not source.get("available"):
        st.warning("无法按来源身份定位视频；请重新连接对应素材，系统不会回退到其他影片。")
        return
    time_range = str(context.get("time_range") or timeline_item.get("timestamp") or "")
    try:
        start_time = int(TimeRange.parse(time_range).start_seconds)
    except ValueError:
        st.warning("该审核项的时间范围无效，未自动跳转视频。")
        return
    st.video(source["path"], start_time=start_time)
    st.caption(f"来源：{video_name} · 定位：{time_range} · Segment：{segment_id}")


def _render_timeline_editor(
    project: dict, store: FusionProjectStore, task_id: str, context: dict
) -> None:
    if not task_id:
        return
    items = context.get("timeline_items") or []
    ids = [item.get("_id") for item in items if item.get("_id") is not None]
    if not ids:
        return
    with st.expander("受限时间线调整"):
        item_id = st.selectbox("时间线条目", ids)
        selected = next(item for item in items if item.get("_id") == item_id)
        timestamp = st.text_input(
            "新时间范围",
            value=str(selected.get("timestamp") or ""),
            key=f"timeline-edit-{task_id}-{item_id}",
        )
        st.caption("新范围必须留在该 Segment 已批准的 Evidence Window 内，并重新通过时间线与 Preflight 校验。")
        if st.button("验证并应用时间线调整", type="primary"):
            try:
                from webui.tools.generate_short_summary import edit_fusion_timeline_item

                updated = edit_fusion_timeline_item(
                    task_id, item_id=item_id, new_timestamp=timestamp
                )
                _sync_matching_review(project, store, task_id, updated)
            except Exception as error:
                st.error(f"时间线调整未应用：{error}")


def _render_version_controls(
    project: dict, store: FusionProjectStore, task_id: str, finalization: dict
) -> None:
    versions = [item for item in finalization.get("version_history") or [] if item.get("version_id")]
    st.caption(f"当前版本：{project.get('active_version_id') or '无'}")
    if not task_id or not versions:
        return
    with st.expander("版本比较与恢复"):
        ids = [str(item["version_id"]) for item in versions]
        baseline = st.selectbox("基准版本", ids, index=0)
        candidate = st.selectbox("候选版本", ids, index=len(ids) - 1)
        compare_col, restore_col = st.columns(2)
        if compare_col.button("比较版本", use_container_width=True):
            from webui.tools.generate_short_summary import compare_fusion_matching_versions

            st.json(
                compare_fusion_matching_versions(
                    task_id, baseline_version_id=baseline, candidate_version_id=candidate
                ),
                expanded=False,
            )
        if restore_col.button("恢复候选版本", use_container_width=True):
            try:
                from webui.tools.generate_short_summary import restore_fusion_matching_version

                updated = restore_fusion_matching_version(task_id, version_id=candidate)
                _sync_matching_review(project, store, task_id, updated)
            except Exception as error:
                st.error(f"无法恢复版本：{error}")


def _stage_output(project, store) -> None:
    st.header("输出")
    blockers = [
        item
        for item in project.get("review_findings") or []
        if item.get("severity") == "blocker" and item.get("status", "open") == "open"
    ]
    if blockers:
        st.error(f"Render Preflight：存在 {len(blockers)} 个必须修复的问题。")
    elif not project.get("active_version_id"):
        st.warning("Render Preflight：尚无可渲染的活动版本。")
    else:
        st.success("Render Preflight：通过。可以创建新的 Render Outcome。")
    st.button("开始渲染", type="primary", disabled=bool(blockers) or not project.get("active_version_id"))


def _failure_category(error: Exception) -> str:
    text = str(error).lower()
    if "total" in text and ("timeout" in text or "时限" in text):
        return "total_timeout"
    if "timeout" in text or "超时" in text:
        return "stream_timeout"
    if "validation" in text or "校验" in text or "plan" in text:
        return "validation_failed"
    return "generation_failed"


def _plan_attempt_store(project_id: str):
    from app.services.fusion_plan_attempts import FusionPlanAttemptStore

    return FusionPlanAttemptStore(
        Path(utils.task_dir("fusion_plan_attempts")) / str(project_id)
    )


def _safe_attempt_summaries(attempt_store) -> list[dict]:
    return [
        {
            "attempt_id": item.get("attempt_id"),
            "kind": item.get("kind"),
            "parent_attempt_id": item.get("parent_attempt_id"),
            "status": item.get("status"),
            "received_characters": item.get("received_characters"),
            "findings": item.get("findings") or [],
            "updated_at": item.get("updated_at"),
        }
        for item in attempt_store.list_attempts()
    ]


def _text_analyzer():
    from app.config import config
    from app.services.llm.migration_adapter import SubtitleAnalyzerAdapter
    from webui.tools.generate_short_summary import FILM_TV_PROMPT_CATEGORY

    provider = str(config.app.get("text_llm_provider", "gemini")).lower()
    model = str(config.app.get(f"text_{provider}_model_name") or "")
    analyzer = SubtitleAnalyzerAdapter(
        config.app.get(f"text_{provider}_api_key"),
        model,
        config.app.get(f"text_{provider}_base_url"),
        provider,
        prompt_category=FILM_TV_PROMPT_CATEGORY,
    )
    return analyzer, provider, model


def _project_source_identity(project: dict) -> dict:
    sources = []
    for source in project.get("source_video_sequence") or []:
        identity = dict(source.get("identity") or {})
        identity.update(
            source_id=str(source.get("source_id") or ""),
            title=str(source.get("title") or ""),
            sequence=int(source.get("sequence") or 0),
        )
        sources.append(identity)
    return {"project_id": str(project.get("project_id") or ""), "sources": sources}


def _render_matching_task(project: dict, store: FusionProjectStore, task_ref: dict) -> None:
    try:
        from webui.tools.generate_short_summary import (
            cancel_fusion_matching_task,
            fusion_matching_task_status,
            resume_fusion_matching_task,
        )

        task = fusion_matching_task_status(task_ref["task_id"])
        status = str(task.get("status") or "")
        stream = task.get("stream_snapshot") if isinstance(task.get("stream_snapshot"), dict) else {}
        store.update_task_summary(
            project["project_id"], task_ref["task_id"],
            status=status, progress=task.get("progress"), message=task.get("message"),
            error_message=task.get("error_message", ""),
            failure_category=stream.get("failure_category", ""),
            recoverable=status in {"failed", "interrupted", "cancelled"},
        )
        st.progress(
            float(task.get("progress") or 0) / 100.0,
            text=str(task.get("message") or status),
        )
        controls = st.columns(3)
        if controls[0].button(
            "继续匹配", key=f"resume-match-{task_ref['task_id']}",
            disabled=status not in {"failed", "interrupted", "cancelled"},
        ):
            resume_fusion_matching_task(task_ref["task_id"])
            st.rerun()
        if controls[1].button(
            "取消匹配", key=f"cancel-match-{task_ref['task_id']}",
            disabled=status not in {"queued", "running"},
        ):
            cancel_fusion_matching_task(task_ref["task_id"])
            st.rerun()
        if controls[2].button("查看诊断", key=f"diag-match-{task_ref['task_id']}"):
            st.json(
                {
                    "状态": status,
                    "进度": task.get("progress"),
                    "失败类别": stream.get("failure_category"),
                    "错误": str(task.get("error_message") or "")[:1000],
                }
            )
        if status == "completed" and isinstance(task.get("finalization"), dict):
            if task_ref.get("status") != "completed":
                admitted = store.admit_matching_completion(
                    project["project_id"], task_id=task_ref["task_id"],
                    finalization=task["finalization"],
                )
                if admitted["admission"] == "stale":
                    st.warning("匹配已完成，但输入版本已过期；结果已保留，未替换当前版本。")
                else:
                    st.success("匹配与 Finalization 已完成，正在进入审核工作区。")
                    st.rerun()
    except Exception as error:
        st.warning(f"匹配任务状态暂不可用：{error}")


def _render_task_center() -> None:
    _top_bar()
    if st.button("← 返回项目库"):
        navigate(st.session_state, PROJECT_LIBRARY_ROUTE)
        st.rerun()
    st.title("任务中心")
    rows = []
    task_entries = []
    for project in project_store().list_projects():
        for task in project.get("task_refs") or []:
            rows.append(
                {
                    "项目": project["name"],
                    "类型": task.get("kind"),
                    "状态": task.get("status"),
                    "进度": task.get("progress"),
                    "说明": task.get("message"),
                    "更新时间": task.get("updated_at"),
                }
            )
            task_entries.append((project, task))
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.subheader("任务操作")
        for project, task in task_entries:
            label = f"{project['name']} · {task.get('kind')} · {task.get('status')}"
            with st.expander(label):
                controls = st.columns(3)
                can_resume = task.get("status") in {"failed", "interrupted", "cancelled"}
                can_cancel = task.get("status") in {"queued", "running"}
                if controls[0].button(
                    "继续", key=f"task-resume-{task['task_id']}", disabled=not can_resume
                ):
                    _resume_project_task(task)
                    st.rerun()
                if controls[1].button(
                    "取消", key=f"task-cancel-{task['task_id']}", disabled=not can_cancel
                ):
                    _cancel_project_task(task)
                    st.rerun()
                if controls[2].button("查看诊断", key=f"task-diag-{task['task_id']}"):
                    diagnostic = project_store().task_diagnostic_projection(
                        project["project_id"], task["task_id"]
                    )
                    st.json(diagnostic)
    else:
        st.info("当前没有项目任务。")


def _resume_project_task(task: dict) -> None:
    kind = str(task.get("kind") or "")
    if kind == "visual_analysis":
        from webui.tools.generate_film_vision_fusion import resume_local_visual_analysis

        resume_local_visual_analysis(task["task_id"])
    elif kind == "fusion_matching":
        from webui.tools.generate_short_summary import resume_fusion_matching_task

        resume_fusion_matching_task(task["task_id"])
    else:
        raise ValueError(f"该任务类型暂不支持继续：{kind}")


def _cancel_project_task(task: dict) -> None:
    kind = str(task.get("kind") or "")
    if kind == "visual_analysis":
        from webui.tools.generate_film_vision_fusion import cancel_local_visual_analysis

        cancel_local_visual_analysis(task["task_id"])
    elif kind == "fusion_matching":
        from webui.tools.generate_short_summary import cancel_fusion_matching_task

        cancel_fusion_matching_task(task["task_id"])
    else:
        raise ValueError(f"该任务类型暂不支持取消：{kind}")

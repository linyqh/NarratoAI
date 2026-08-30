"""Project-centered Streamlit surface for Film Vision Fusion."""

from __future__ import annotations

from html import escape
from pathlib import Path
import hashlib
import json
from uuid import uuid4
from app.config import config

import streamlit as st

from app.services.fusion_projects import FusionProjectStore, STAGES, project_projection
from app.utils import utils
from webui.fusion_navigation import (
    NEW_PROJECT_ROUTE,
    PROJECT_LIBRARY_ROUTE,
    PROJECT_WORKSPACE_ROUTE,
    TASK_CENTER_ROUTE,
    enter_legacy_modes,
    navigate,
    transfer_project_to_traditional,
)


STAGE_LABELS = {
    "setup": "项目设置",
    "evidence": "媒体与证据",
    "narration": "解说词与叙事地图",
    "matching": "画面匹配",
    "review": "审核",
    "output": "输出",
}

STATUS_LABELS = {
    "draft": "草稿",
    "running": "处理中",
    "interrupted": "已中断",
    "waiting_for_review": "等待审核",
    "blocked": "已阻断",
    "ready_to_render": "可渲染",
    "completed": "已完成",
    "source_offline": "素材离线",
    "stale_result": "存在过期结果",
    "archived": "已归档",
    "trashed": "回收站",
}

TASK_CAPABILITIES = {
    "visual_analysis": {"resume", "cancel"},
    "fusion_matching": {"resume", "cancel"},
    "narration_generation": {"resume", "cancel"},
    "fusion_plan": {"resume", "cancel"},
    "render": {"resume"},
}


def _options_with_current(defaults: list[str], current: str) -> tuple[list[str], int]:
    current = str(current or "")
    options = list(defaults)
    if current and current not in options:
        options.insert(0, current)
    return options, options.index(current) if current in options else 0


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
        .stButton > button[kind="primary"] { background:#3568d4; color:white; border-color:#3568d4; }
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
        legacy_label = "转到传统模式" if project else "传统模式"
        if st.button(legacy_label, use_container_width=True):
            if project:
                transfer_project_to_traditional(project, st.session_state)
            else:
                enter_legacy_modes(st.session_state, fusion=True)
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

    with st.expander("迁移现有 Fusion 工作"):
        st.caption("仅在你明确提交脚本和源视频路径后创建迁移项目；系统不会自动扫描旧会话。")
        migration_name = st.text_input("迁移项目名称", value="迁移的 Film Vision Fusion 项目")
        migration_sources = st.text_area("源视频路径（每行一个）")
        migration_file = st.file_uploader(
            "最终 Fusion Script / Finalization JSON", type=["json"], key="fusion-migration-json"
        )
        if st.button("创建迁移项目", disabled=migration_file is None):
            try:
                payload = json.loads(migration_file.getvalue().decode("utf-8-sig"))
                if isinstance(payload, list):
                    script = payload
                    preflight = {
                        "blockers": [{"code": "migrated_work_requires_review", "message": "迁移脚本需要重新审核"}],
                        "warnings": [], "renderable": False,
                    }
                elif isinstance(payload, dict):
                    script = payload.get("finalized_script") or payload.get("items") or []
                    preflight = payload.get("preflight") or {
                        "blockers": [{"code": "migrated_work_requires_review", "message": "迁移脚本需要重新审核"}],
                        "warnings": [], "renderable": False,
                    }
                else:
                    raise ValueError("迁移 JSON 必须是脚本数组或 Finalization 对象")
                migrated = store.migrate_legacy_project(
                    name=migration_name,
                    source_paths=[line.strip() for line in migration_sources.splitlines() if line.strip()],
                    finalized_script=script,
                    preflight=preflight,
                )
                navigate(
                    st.session_state, PROJECT_WORKSPACE_ROUTE,
                    project_id=migrated["project_id"],
                )
                st.rerun()
            except Exception as error:
                st.error(f"迁移失败：{error}")

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
                f"<span class='fusion-status'>{escape(STATUS_LABELS.get(str(projection['status']), str(projection['status'])))}</span>"
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
        language_options, language_index = _options_with_current(
            ["简体中文（中国）", "繁體中文", "English"],
            str(settings.get("output_language") or "简体中文（中国）"),
        )
        language = st.selectbox("输出语言", language_options, index=language_index)
        style_options, style_index = _options_with_current(
            ["剧情解说", "悬疑推进", "人物成长", "冷静分析", "逆袭/复仇"],
            str(settings.get("commentary_style") or "剧情解说"),
        )
        style = st.selectbox("解说风格", style_options, index=style_index)
        target = st.number_input("目标文案字数", min_value=300, max_value=10000, value=int(settings.get("target_narration_length") or 1200), step=100)
        ratio = st.slider("原片声音比例", 0, 100, int(settings.get("original_sound_ratio") or 30), 5)
        subtitle_policies = {
            "优先使用现有字幕，缺失时自动转录": "source_or_asr",
            "仅使用我提供的字幕": "source_only",
            "始终重新转录": "always_asr",
        }
        policy_values = list(subtitle_policies.values())
        current_policy = str(settings.get("subtitle_policy") or "source_or_asr")
        policy_index = policy_values.index(current_policy) if current_policy in policy_values else 0
        policy_label = st.selectbox("字幕策略", list(subtitle_policies), index=policy_index)
        subtitle_policy = subtitle_policies[policy_label]
        st.caption("策略会按每个源视频执行；字幕上传、转录、翻译与校准结果都只绑定到该源。")
        from webui.components.audio_settings import get_tts_engine_options
        tts_options = get_tts_engine_options()
        saved_engine = str(settings.get("tts_engine") or config.ui.get("tts_engine") or config.INDEXTTS_ENGINE)
        engine_values, engine_index = _options_with_current(list(tts_options), saved_engine)
        tts_engine = st.selectbox("TTS 引擎", engine_values, index=engine_index, format_func=lambda key: tts_options.get(key, key))
        saved_voice = str(settings.get("voice_profile") or config.ui.get("voice_name", ""))
        if tts_engine == "edge_tts":
            from app.services import voice
            edge_voices = voice.get_all_edge_voices()
            voice_options, voice_index = _options_with_current(edge_voices, saved_voice)
            voice_profile = st.selectbox(
                "TTS 音色", voice_options, index=voice_index,
                format_func=lambda value: value.replace("Neural", "").replace("-Female", "（女）").replace("-Male", "（男）"),
                help="与传统 Edge TTS 使用同一份可选音色列表。",
            )
        else:
            voice_profile = st.text_input(
                "TTS 音色", value=saved_voice,
                help="项目保存选择快照；API Key 和本机服务地址仍使用本机设置。",
            )
        voice_parameters = dict(settings.get("voice_parameters") or {})
        voice_rate = st.slider("语速", 0.5, 2.0, float(voice_parameters.get("rate") or 1.0), 0.1)
        voice_volume = st.slider("解说音量", 0.0, 2.0, float(voice_parameters.get("volume") or 1.0), 0.05)
        voice_pitch = st.slider("音调", 0.5, 2.0, float(voice_parameters.get("pitch") or 1.0), 0.1)
        background_music = st.text_input("背景音乐路径（可选）", value=str(settings.get("background_music") or ""))
        format_options, format_index = _options_with_current(
            ["mp4", "mkv"], str(settings.get("output_format") or "mp4")
        )
        output_format = st.selectbox("输出格式", format_options, index=format_index)
        aspect_options, aspect_index = _options_with_current(
            ["9:16", "16:9", "1:1", "3:4", "4:3"],
            str(settings.get("video_aspect") or "9:16"),
        )
        video_aspect = st.selectbox("视频比例", aspect_options, index=aspect_index)
        subtitle_enabled = st.toggle(
            "启用字幕", value=bool(settings.get("subtitle_enabled", True))
        )
        if st.button("保存配置", use_container_width=True):
            settings.update(
                output_language=language,
                commentary_style=style,
                target_narration_length=int(target),
                original_sound_ratio=int(ratio),
                subtitle_policy=subtitle_policy,
                tts_engine=tts_engine,
                voice_profile=voice_profile,
                voice_parameters={"rate": voice_rate, "volume": voice_volume, "pitch": voice_pitch},
                background_music=background_music,
                output_format=output_format,
                video_aspect=video_aspect,
                subtitle_enabled=subtitle_enabled,
            )
            project = store.update(project_id, name=name, project_settings=settings)
            st.success("配置已保存")
    with right:
        st.subheader("源视频")
        st.caption("引用本机文件不会复制也不会在删除项目时删除；项目托管会复制一份，便于项目独立保存。")
        resource_dir = Path(utils.video_dir())
        resource_files = sorted(
            [path for suffix in ("*.mp4", "*.mov", "*.avi", "*.flv", "*.mkv", "*.mpeg", "*.mpg", "*.3gp") for path in resource_dir.glob(suffix)],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ) if resource_dir.is_dir() else []
        resource_path = st.selectbox(
            "从资源目录选择", [""] + [str(path) for path in resource_files],
            format_func=lambda value: "选择资源目录中的视频" if not value else str(Path(value).relative_to(resource_dir)),
        )
        if st.button("引用所选资源目录视频", disabled=not resource_path, use_container_width=True):
            store.add_local_reference(project_id, path=resource_path)
            st.rerun()
        local_path = st.text_input("本机视频路径", placeholder="D:\\Movies\\example.mp4")
        subtitle_path = st.text_input("字幕路径（SRT，可稍后补充）", placeholder="D:\\Movies\\example.srt")
        if st.button("添加本机视频", disabled=not local_path, use_container_width=True):
            store.add_local_reference(project_id, path=local_path, subtitle_path=subtitle_path)
            st.rerun()
        upload = st.file_uploader("上传并由项目托管", type=["mp4", "mkv", "mpeg", "mpg", "3gp"])
        st.caption("托管上传会复制到当前项目；永久删除项目时仅删除这份副本，绝不删除本机引用文件。")
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
        with st.expander("字幕处理", expanded=source.get("subtitle_status") != "available"):
            st.caption("字幕是剧情和对白证据。上传后的字幕只属于当前源视频；转录、翻译和校准将在此处生成同样的源绑定结果。")
            subtitle_path = st.text_input(
                "引用本机 SRT 路径", value=str(source.get("subtitle_path") or ""),
                key=f"subtitle-path-{source['source_id']}",
            )
            update, uploaded = st.columns(2)
            if update.button("采用本机字幕", key=f"subtitle-local-{source['source_id']}", disabled=not subtitle_path):
                store.set_source_subtitle(
                    project["project_id"], source_id=source["source_id"], subtitle_path=subtitle_path, origin="provided"
                )
                st.rerun()
            subtitle_upload = uploaded.file_uploader(
                "上传 SRT", type=["srt"], key=f"subtitle-upload-{source['source_id']}", label_visibility="collapsed"
            )
            if st.button("保存上传字幕", key=f"subtitle-save-{source['source_id']}", disabled=subtitle_upload is None):
                store.save_source_subtitle_upload(
                    project["project_id"], source_id=source["source_id"],
                    filename=subtitle_upload.name, content=subtitle_upload.getvalue(),
                )
                st.rerun()
            asr_backend = st.selectbox(
                "转录方式", ["local", "firered", "bailian"],
                format_func=lambda value: {
                    "local": "本地 FunASR", "firered": "本地 FireRedASR", "bailian": "阿里百炼 Fun-ASR"
                }[value],
                key=f"subtitle-asr-{source['source_id']}",
            )
            transcription, translate, calibrate = st.columns(3)
            if transcription.button("转录字幕", key=f"subtitle-asr-run-{source['source_id']}", disabled=not source.get("available")):
                try:
                    from app.services import fun_asr_subtitle
                    output = store.source_subtitle_output_path(
                        project["project_id"], source_id=source["source_id"], label=f"asr-{asr_backend}"
                    )
                    if asr_backend == "local":
                        result = fun_asr_subtitle.create_with_local_fun_asr(
                            source["path"], output, api_url=config.fun_asr.get("api_url", ""),
                            hotword=config.fun_asr.get("hotword", ""), enable_spk=bool(config.fun_asr.get("enable_spk", False)),
                        )
                    elif asr_backend == "firered":
                        result = fun_asr_subtitle.create_with_local_firered_asr(
                            source["path"], output, api_url=config.fun_asr.get("firered_api_url", ""),
                        )
                    else:
                        result = fun_asr_subtitle.create_with_fun_asr(
                            source["path"], output, api_key=config.fun_asr.get("api_key", ""),
                        )
                    store.set_source_subtitle(
                        project["project_id"], source_id=source["source_id"], subtitle_path=str(result or output), origin=f"asr:{asr_backend}"
                    )
                    st.success("字幕转录完成，已绑定到当前源视频。")
                    st.rerun()
                except Exception as error:
                    st.error(f"字幕转录失败：{error}")
            if translate.button("翻译字幕", key=f"subtitle-translate-{source['source_id']}", disabled=not source.get("subtitle_path")):
                try:
                    from app.services import subtitle_translator
                    provider = config.app.get("text_llm_provider", "openai").lower()
                    output = store.source_subtitle_output_path(project["project_id"], source_id=source["source_id"], label="translated")
                    result = subtitle_translator.translate_subtitle_file(
                        source["subtitle_path"], output_file=output,
                        target_language=str((project.get("project_settings") or {}).get("output_language") or "中文"),
                        provider=provider, api_key=config.app.get(f"text_{provider}_api_key", ""),
                        base_url=config.app.get(f"text_{provider}_base_url", ""),
                    )
                    store.set_source_subtitle(project["project_id"], source_id=source["source_id"], subtitle_path=result, origin="translated")
                    st.success("字幕翻译完成。")
                    st.rerun()
                except Exception as error:
                    st.error(f"字幕翻译失败：{error}")
            if calibrate.button("校准字幕", key=f"subtitle-calibrate-{source['source_id']}", disabled=not source.get("subtitle_path")):
                try:
                    from app.services import subtitle_corrector
                    provider = config.app.get("text_llm_provider", "openai").lower()
                    output = store.source_subtitle_output_path(project["project_id"], source_id=source["source_id"], label="corrected")
                    result = subtitle_corrector.correct_subtitle_file(
                        source["subtitle_path"], output_file=output,
                        provider=provider, api_key=config.app.get(f"text_{provider}_api_key", ""),
                        base_url=config.app.get(f"text_{provider}_base_url", ""),
                    )
                    store.set_source_subtitle(project["project_id"], source_id=source["source_id"], subtitle_path=result, origin="corrected")
                    st.success("字幕校准完成。")
                    st.rerun()
                except Exception as error:
                    st.error(f"字幕校准失败：{error}")
            if source.get("subtitle_path"):
                st.caption(f"当前采用：{source.get('subtitle_origin', 'provided')} · {source['subtitle_path']}")
                with st.expander("字幕预览", expanded=False):
                    try:
                        st.text(Path(str(source["subtitle_path"])).read_text(encoding="utf-8")[:6000])
                    except OSError as error:
                        st.warning(f"无法读取当前字幕：{error}")
        with st.expander("复用已视觉分析的 JSON", expanded=False):
            st.caption("必须选择当前源视频对应的 JSON。内容身份不匹配会被拒绝；未验证旧 JSON 只能回归预览，不能生成正式成片。")
            from webui.tools.generate_film_vision_fusion import list_local_visual_evidence_artifacts
            local_artifacts = list_local_visual_evidence_artifacts()
            selected_artifact = st.selectbox(
                "本地视觉产物", [""] + [str(path) for path in local_artifacts],
                format_func=lambda value: "选择已分析 JSON" if not value else Path(value).name,
                key=f"visual-json-{source['source_id']}",
            )
            regression_only = st.checkbox(
                "允许未验证旧 JSON（仅回归预览）", key=f"visual-unverified-{source['source_id']}"
            )
            uploaded_artifact = st.file_uploader(
                "或上传视觉 JSON", type=["json"], key=f"visual-upload-{source['source_id']}"
            )
            if st.button("校验并导入视觉证据", key=f"visual-import-{source['source_id']}", disabled=not (selected_artifact or uploaded_artifact)):
                try:
                    if uploaded_artifact is not None:
                        artifact_payload = json.loads(uploaded_artifact.getvalue().decode("utf-8"))
                        artifact_name = f"导入：{uploaded_artifact.name}"
                    else:
                        artifact_name = selected_artifact
                        artifact_payload = json.loads(Path(selected_artifact).read_text(encoding="utf-8"))
                    store.import_source_visual_evidence_artifact(
                        project["project_id"], source_id=source["source_id"], artifact=artifact_payload,
                        artifact_path=artifact_name, allow_unverified_source=regression_only,
                    )
                    st.success("视觉证据已绑定到当前源视频。")
                    st.rerun()
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    st.error(f"视觉证据导入失败：{error}")
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
                reservation_id = f"visualreservation{uuid4().hex}"
                try:
                    from webui.tools.generate_film_vision_fusion import start_local_visual_analysis

                    store.reserve_task(
                        project["project_id"], task_id=reservation_id,
                        kind="visual_analysis", source_id=source["source_id"],
                        input_version_id=project.get("active_version_id") or "setup",
                    )

                    task_id = start_local_visual_analysis(
                        video_path=source["path"],
                        video_theme=project["name"],
                        custom_prompt=custom_prompt,
                        frame_interval_seconds=float(interval),
                        vision_batch_size=int(batch),
                    )
                    store.bind_reserved_task(
                        project["project_id"], reservation_id=reservation_id,
                        task_id=task_id,
                    )
                    st.rerun()
                except Exception as error:
                    try:
                        store.update_task_summary(
                            project["project_id"], reservation_id, status="failed",
                            error_message=str(error), recoverable=True,
                        )
                    except ValueError:
                        pass
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
    verified_visual_evidence = all(
        source.get("visual_evidence_status") == "completed" for source in sources
    )
    narration_start = store.task_start_projection(
        project["project_id"], kind="narration_generation"
    )
    if narration_start["reason"]:
        st.caption(narration_start["reason"])
    if st.button(
        "生成解说词", type="primary",
        disabled=not subtitle_paths or not verified_visual_evidence or not narration_start["allowed"],
    ):
        reservation_id = f"matchingreservation{uuid4().hex}"
        try:
            _start_narration_generation(project["project_id"])
            st.rerun()
        except Exception as error:
            st.error(f"无法启动解说词生成：{error}")
    narration_task = next(
        (
            task for task in reversed(project.get("task_refs") or [])
            if task.get("kind") == "narration_generation"
        ),
        None,
    )
    if narration_task and narration_task.get("status") in {
        "queued", "running", "failed", "interrupted", "cancelled"
    }:
        st.info(str(narration_task.get("message") or narration_task.get("status")))
        if st.button("刷新解说词任务状态"):
            st.rerun()
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
        try:
            _start_fusion_plan_generation(project["project_id"])
            st.rerun()
        except Exception as error:
            st.error(f"无法启动分段计划生成：{error}")
    plan_task = next(
        (
            task for task in reversed(project.get("task_refs") or [])
            if task.get("kind") == "fusion_plan"
        ),
        None,
    )
    if plan_task and plan_task.get("status") in {
        "queued", "running", "failed", "interrupted", "cancelled"
    }:
        stream.info(str(plan_task.get("message") or plan_task.get("error_message") or plan_task.get("status")))
        if st.button("刷新 Plan 任务状态"):
            st.rerun()

    draft_plan = artifacts.get("fusion_segment_plan_draft") or artifacts.get("fusion_segment_plan")
    recovered_attempt = None
    if not draft_plan:
        current_version = str(project.get("active_version_id") or "setup")
        current_fingerprint = _plan_input_fingerprint(project, artifacts, narration)
        recoverable = [
            item for item in attempts
            if item.get("status") in {"validation_failed", "waiting_for_review"}
            and str(item.get("project_id") or project["project_id"]) == project["project_id"]
            and str(item.get("version_id") or "setup") == current_version
            and str(item.get("input_fingerprint") or "") == current_fingerprint
        ]
        if recoverable:
            recovered_attempt = recoverable[-1]
            try:
                draft_plan = plan_store.read_recovery_payload(
                    str(recovered_attempt["attempt_id"])
                )
                st.info(
                    "已从失败的 Plan Attempt 恢复完整模型输出；编辑并验证后可继续，"
                    "不会重新消耗整次生成结果。"
                )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                st.warning(f"Plan Attempt 的恢复载荷暂不可用：{error}")
    if draft_plan:
        editor = st.text_area(
            "结构化计划编辑器",
            value=(
                draft_plan
                if isinstance(draft_plan, str)
                else json.dumps(draft_plan, ensure_ascii=False, indent=2)
            ),
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
            store.reserve_task(
                project["project_id"], task_id=reservation_id,
                kind="fusion_matching",
                input_version_id=project.get("active_version_id") or "",
            )
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
            store.bind_reserved_task(
                project["project_id"], reservation_id=reservation_id,
                task_id=task_id,
            )
            st.rerun()
        except Exception as error:
            try:
                store.update_task_summary(
                    project["project_id"], reservation_id, status="failed",
                    error_message=str(error), recoverable=True,
                )
            except ValueError:
                pass
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
    artifacts = project.get("artifact_refs") or {}
    finalization = artifacts.get("finalization") if isinstance(artifacts.get("finalization"), dict) else {}
    preflight = finalization.get("preflight") if isinstance(finalization.get("preflight"), dict) else {}
    migration = dict(project.get("migration_state") or {})
    if migration.get("status") == "requires_revalidation":
        st.warning(
            "这是旧版导入项目。旧 Preflight 不具备渲染授权；请确认当前来源后运行新版校验。"
        )
        if st.button("重新绑定来源并运行当前 Preflight", type="primary"):
            try:
                from app.utils.video_processor import VideoProcessor

                sources = list(project.get("source_video_sequence") or [])
                source_durations = {
                    Path(source["path"]).name: VideoProcessor(source["path"]).duration
                    for source in sources if source.get("available")
                }
                store.revalidate_legacy_project(
                    project["project_id"], source_durations=source_durations
                )
                st.success("旧项目已通过当前来源绑定与 Preflight。")
                st.rerun()
            except Exception as error:
                st.error(f"旧项目仍未通过重新校验：{error}")
    blockers = list(preflight.get("blockers") or [])
    warnings = list(preflight.get("warnings") or [])
    if blockers:
        st.error(f"Render Preflight：存在 {len(blockers)} 个必须修复的问题。")
        st.dataframe(blockers, use_container_width=True, hide_index=True)
    elif not project.get("active_version_id"):
        st.warning("Render Preflight：尚无可渲染的活动版本。")
    elif warnings and not str(preflight.get("warning_override_reason") or "").strip():
        st.warning(f"Render Preflight：存在 {len(warnings)} 个警告，需要填写人工覆盖原因。")
        st.dataframe(warnings, use_container_width=True, hide_index=True)
        reason = st.text_area("警告覆盖原因（必填）")
        if st.button("记录原因并重新检查", disabled=not reason.strip()):
            store.override_render_warnings(project["project_id"], reason=reason)
            st.rerun()
    elif not finalization.get("renderable") or not preflight.get("renderable"):
        st.warning("Render Preflight：Narrative Map 或审核状态尚未允许渲染。")
    else:
        st.success("Render Preflight：通过。可以创建新的 Render Outcome。")
    renderable = bool(
        project.get("active_version_id")
        and not blockers
        and finalization.get("renderable")
        and preflight.get("renderable")
        and (not warnings or str(preflight.get("warning_override_reason") or "").strip())
    )
    script = finalization.get("finalized_script") or []
    sources = [source for source in project.get("source_video_sequence") or [] if source.get("available")]
    active_render = next(
        (
            task for task in reversed(project.get("task_refs") or [])
            if task.get("kind") == "render" and task.get("status") in {"queued", "running", "rendering"}
        ),
        None,
    )
    if st.button(
        "开始渲染", type="primary",
        disabled=not renderable or not script or not sources or active_render is not None,
    ):
        try:
            _start_project_render(project, store, finalization)
            st.rerun()
        except Exception as error:
            st.error(f"无法开始渲染：{error}")
    if active_render:
        _poll_project_render(project, store, active_render)
    outcomes = project.get("render_outcomes") or []
    if outcomes:
        st.subheader("Render Outcomes")
        for outcome in reversed(outcomes):
            st.caption(
                f"版本 {outcome.get('version_id')} · {outcome.get('created_at')}"
                + (" · 过期结果（未设为当前成片）" if outcome.get("admission") == "stale" else "")
            )
            if Path(str(outcome.get("media_path") or "")).is_file():
                st.video(outcome["media_path"])
            else:
                st.warning("该历史成片当前离线；记录仍保留。")


def _failure_category(error: Exception) -> str:
    text = str(error).lower()
    if "total" in text and ("timeout" in text or "时限" in text):
        return "total_timeout"
    if "timeout" in text or "超时" in text:
        return "stream_timeout"
    if "validation" in text or "校验" in text or "plan" in text:
        return "validation_failed"
    return "generation_failed"


def _task_input_version(store: FusionProjectStore, project_id: str, task_id: str) -> str:
    project = store.read(project_id)
    task = next(
        (item for item in project.get("task_refs") or [] if item.get("task_id") == task_id),
        {},
    )
    return str(task.get("input_version_id") or "")


def _task_run_is_current(
    store: FusionProjectStore, project_id: str, task_id: str, run_id: str
) -> bool:
    project = store.read(project_id)
    task = next(
        (item for item in project.get("task_refs") or [] if item.get("task_id") == task_id),
        {},
    )
    return (
        str(task.get("run_id") or "") == str(run_id)
        and task.get("status") not in {"cancelled", "superseded"}
    )


def _start_narration_generation(project_id: str, task_id: str = "") -> str:
    import threading

    store = project_store()
    project = store.read(project_id)
    task_id = task_id or f"narration{uuid4().hex}"
    run_id = uuid4().hex
    store.reserve_task(
        project_id, task_id=task_id, kind="narration_generation",
        input_version_id=project.get("active_version_id") or "setup", run_id=run_id,
    )

    def run() -> None:
        worker_store = project_store()
        try:
            if not _task_run_is_current(worker_store, project_id, task_id, run_id):
                return
            worker_store.update_task_summary(
                project_id, task_id, status="running", progress=5,
                message="正在生成解说词",
            )
            current = worker_store.read(project_id)
            artifacts = dict(current.get("artifact_refs") or {})
            sources = list(current.get("source_video_sequence") or [])
            subtitle_paths = [
                source.get("subtitle_path") for source in sources if source.get("subtitle_path")
            ]
            if not subtitle_paths:
                raise ValueError("Narration generation requires subtitle or ASR evidence")
            if any(source.get("visual_evidence_status") != "completed" for source in sources):
                raise ValueError("Narration generation requires verified visual evidence for every source")
            from webui.tools.generate_short_summary import (
                FILM_TV_PROMPT_CATEGORY,
                generate_short_drama_narration_copy,
            )

            result = generate_short_drama_narration_copy(
                subtitle_path=subtitle_paths,
                video_theme=current["name"],
                temperature=0.3,
                video_paths=[source.get("path") for source in sources],
                narration_language=(current.get("project_settings") or {}).get(
                    "output_language", "简体中文（中国）"
                ),
                drama_genre=(current.get("project_settings") or {}).get(
                    "commentary_style", "剧情解说"
                ),
                prompt_category=FILM_TV_PROMPT_CATEGORY,
                narration_word_count=int(
                    (current.get("project_settings") or {}).get(
                        "target_narration_length", 1200
                    )
                ),
                visual_evidence=str(artifacts.get("visual_evidence") or ""),
            )
            if not _task_run_is_current(worker_store, project_id, task_id, run_id):
                return
            if not result:
                raise ValueError("Narration generation returned no result")
            current = worker_store.read(project_id)
            input_version = _task_input_version(worker_store, project_id, task_id)
            active_input = str(current.get("active_version_id") or "setup")
            if input_version != active_input:
                artifact_path = worker_store.save_json_artifact(
                    project_id, name=f"stale-{task_id}.json", payload=result
                )
                worker_store.commit_stale_task_artifact(
                    project_id, task_id=task_id, run_id=run_id,
                    artifact_ref=artifact_path,
                    message="解说词已完成，但输入版本已变化；结果作为过期产物保留",
                )
                return
            worker_store.commit_task_artifacts(
                project_id, task_id=task_id, run_id=run_id,
                artifact_changes=dict(
                narration_draft=result["narration_copy"],
                plot_analysis=result["plot_analysis"],
                subtitle_content=result["subtitle_content"],
                ),
                message="解说词已生成并保存为待审核草稿",
            )
        except Exception as error:
            try:
                worker_store.finish_task_run(
                    project_id, task_id=task_id, run_id=run_id, status="failed",
                    error_message=str(error), progress=0,
                    message="解说词生成未完成",
                    failure_category=_failure_category(error), recoverable=True,
                )
            except ValueError:
                pass

    threading.Thread(
        target=run, name=f"fusion-narration-{task_id}", daemon=True
    ).start()
    return task_id


def _start_fusion_plan_generation(project_id: str, task_id: str = "") -> str:
    import threading

    store = project_store()
    project = store.read(project_id)
    task_id = task_id or f"fusionplan{uuid4().hex}"
    run_id = uuid4().hex
    store.reserve_task(
        project_id, task_id=task_id, kind="fusion_plan",
        input_version_id=project.get("active_version_id") or "", run_id=run_id,
    )

    def run() -> None:
        worker_store = project_store()
        attempt_store = _plan_attempt_store(project_id)
        try:
            if not _task_run_is_current(worker_store, project_id, task_id, run_id):
                return
            worker_store.update_task_summary(
                project_id, task_id, status="running", progress=5,
                message="正在生成 Fusion Segment Plan",
            )
            current = worker_store.read(project_id)
            artifacts = dict(current.get("artifact_refs") or {})
            narration = str(artifacts.get("narration") or "")
            if not narration:
                raise ValueError("Fusion Segment Plan requires approved narration")
            from webui.tools.generate_short_summary import create_fusion_segment_plan

            analyzer, provider, model = _text_analyzer()
            plan = create_fusion_segment_plan(
                analyzer=analyzer,
                short_name=current["name"],
                plot_analysis=str(artifacts.get("plot_analysis") or ""),
                subtitle_content=str(artifacts.get("subtitle_content") or ""),
                narration_copy=narration,
                narration_language=str((current.get("project_settings") or {}).get("output_language") or "简体中文（中国）"),
                drama_genre=str((current.get("project_settings") or {}).get("commentary_style") or "剧情解说"),
                visual_evidence=str(artifacts.get("visual_evidence") or ""),
                highlight_candidates=str(artifacts.get("highlight_candidates") or ""),
                temperature=0.3,
                attempt_store=attempt_store,
                attempt_context={
                    "provider": provider,
                    "model": model,
                    "input_fingerprint": _plan_input_fingerprint(
                        current, artifacts, narration
                    ),
                    "project_id": project_id,
                    "version_id": current.get("active_version_id") or "setup",
                },
            )
            if not _task_run_is_current(worker_store, project_id, task_id, run_id):
                return
            current = worker_store.read(project_id)
            input_version = _task_input_version(worker_store, project_id, task_id)
            active_input = str(current.get("active_version_id") or "")
            if input_version != active_input:
                artifact_path = worker_store.save_json_artifact(
                    project_id, name=f"stale-{task_id}.json", payload=plan
                )
                worker_store.commit_stale_task_artifact(
                    project_id, task_id=task_id, run_id=run_id,
                    artifact_ref=artifact_path,
                    message="分段计划已完成，但输入版本已变化；结果作为过期产物保留",
                )
                return
            worker_store.commit_task_artifacts(
                project_id, task_id=task_id, run_id=run_id,
                artifact_changes={
                    "fusion_segment_plan_draft": plan,
                    "fusion_plan_attempts": _safe_attempt_summaries(attempt_store),
                },
                message="分段计划已生成，等待审核批准",
            )
        except Exception as error:
            recovery = getattr(error, "to_dict", lambda: {})()
            try:
                worker_store.finish_task_run(
                    project_id, task_id=task_id, run_id=run_id,
                    status=str(recovery.get("status") or "failed"),
                    progress=100 if recovery.get("status") == "waiting_for_review" else 0,
                    error_message=str(error),
                    message=str(recovery.get("message") or "分段计划需要恢复审核"),
                    artifact_changes={
                        "fusion_plan_attempts": _safe_attempt_summaries(attempt_store)
                    },
                    failure_category=_failure_category(error), recoverable=True,
                )
            except ValueError:
                pass

    threading.Thread(
        target=run, name=f"fusion-plan-{task_id}", daemon=True
    ).start()
    return task_id


def _start_project_render(
    project: dict, store: FusionProjectStore, finalization: dict
) -> None:
    import threading

    from app.config import config
    from app.models.schema import VideoClipParams
    from app.services import state as state_service
    from app.services import task as task_service
    from app.models import const

    version_id = str(project.get("active_version_id") or "")
    if not version_id:
        raise ValueError("Render requires an active version")
    script = list(finalization.get("finalized_script") or [])
    if not script:
        raise ValueError("Render requires a finalized Fusion Script")
    sources = [
        source for source in project.get("source_video_sequence") or []
        if source.get("available")
    ]
    if not sources:
        raise ValueError("Render requires at least one available source video")
    settings = dict(project.get("project_settings") or {})
    script_path = store.save_json_artifact(
        project["project_id"], name=f"render-{version_id}.json", payload=script
    )
    source_paths = [str(source["path"]) for source in sources]
    subtitle_paths = [
        str(source.get("subtitle_path") or "") for source in sources
        if source.get("subtitle_path")
    ]
    language_codes = {
        "简体中文（中国）": "zh-CN",
        "繁體中文": "zh-TW",
        "English": "en-US",
    }
    params = VideoClipParams(
        video_clip_json_path=script_path,
        video_origin_path=source_paths[0],
        video_origin_paths=source_paths,
        original_subtitle_path=subtitle_paths[0] if subtitle_paths else "",
        original_subtitle_paths=subtitle_paths,
        video_aspect=str(settings.get("video_aspect") or "9:16"),
        video_language=language_codes.get(
            str(settings.get("output_language") or ""),
            str(settings.get("output_language") or "zh-CN"),
        ),
        voice_name=str(settings.get("voice_profile") or config.ui.get("voice_name", "zh-CN-YunjianNeural")),
        voice_rate=float((settings.get("voice_parameters") or {}).get("rate") or 1.0),
        voice_volume=float((settings.get("voice_parameters") or {}).get("volume") or 1.0),
        voice_pitch=float((settings.get("voice_parameters") or {}).get("pitch") or 1.0),
        tts_engine=str(settings.get("tts_engine") or config.INDEXTTS_ENGINE),
        bgm_type="local" if settings.get("background_music") else "none",
        bgm_file=str(settings.get("background_music") or ""),
        subtitle_enabled=bool(settings.get("subtitle_enabled", True)),
    )
    task_id = f"render{uuid4().hex}"
    configuration_snapshot = {
        "active_version_id": version_id,
        "project_settings": settings,
        "source_identities": [
            {"source_id": source.get("source_id"), "identity": source.get("identity") or {}}
            for source in sources
        ],
        "script_path": script_path,
    }
    authorization = store.create_render_authorization(
        project["project_id"], configuration_snapshot=configuration_snapshot
    )
    store.reserve_task(
        project["project_id"], task_id=task_id, kind="render",
        input_version_id=version_id, run_id=uuid4().hex,
    )
    store.update_task_summary(
        project["project_id"], task_id,
        configuration_snapshot=configuration_snapshot,
        render_authorization=authorization,
        message="渲染已排队",
    )

    def run() -> None:
        try:
            task_service.start_subclip_unified(task_id=task_id, params=params)
        except Exception as error:
            state_service.state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                progress=0,
                message=str(error),
            )

    threading.Thread(
        target=run, name=f"fusion-project-render-{task_id}", daemon=True
    ).start()


def _poll_project_render(
    project: dict, store: FusionProjectStore, task_ref: dict
) -> None:
    from app.models import const
    from app.services import state as state_service

    task = state_service.state.get_task(task_ref["task_id"])
    if not task:
        st.info("等待渲染进程报告状态…")
        if st.button("刷新渲染状态"):
            st.rerun()
        return
    progress = max(0, min(100, int(task.get("progress") or 0)))
    state = task.get("state")
    status = (
        "completed" if state == const.TASK_STATE_COMPLETE
        else "failed" if state == const.TASK_STATE_FAILED
        else "rendering"
    )
    store.update_task_summary(
        project["project_id"], task_ref["task_id"],
        status=status, progress=progress, message=str(task.get("message") or ""),
        error_message=str(task.get("message") or "") if status == "failed" else "",
        recoverable=status == "failed",
    )
    st.progress(progress / 100.0, text=str(task.get("message") or "正在渲染"))
    if status == "completed":
        existing = {
            str(item.get("render_task_id") or "")
            for item in project.get("render_outcomes") or []
        }
        if task_ref["task_id"] not in existing:
            videos = [str(path) for path in task.get("videos") or [] if str(path)]
            if not videos:
                st.error("渲染任务已结束，但没有返回可播放成片。")
                return
            for media_path in videos:
                store.add_render_outcome(
                    project["project_id"],
                    media_path=media_path,
                    render_authorization=task_ref.get("render_authorization") or {},
                    render_task_id=task_ref["task_id"],
                )
            st.rerun()
    elif status == "failed":
        st.error(f"渲染失败：{task.get('message') or '请查看诊断后重新渲染'}")
    elif st.button("刷新渲染状态"):
        st.rerun()


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
            "project_id": item.get("project_id"),
            "version_id": item.get("version_id"),
            "input_fingerprint": item.get("input_fingerprint"),
            "raw_response_ref": item.get("raw_response_ref"),
            "recovery_payload_ref": item.get("recovery_payload_ref"),
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


def _plan_input_fingerprint(
    project: dict, artifacts: dict, narration: str
) -> str:
    payload = {
        "project_id": str(project.get("project_id") or ""),
        "version_id": str(project.get("active_version_id") or "setup"),
        "narration": str(narration or ""),
        "plot_analysis": str(artifacts.get("plot_analysis") or ""),
        "subtitle_content": str(artifacts.get("subtitle_content") or ""),
        "visual_evidence": str(artifacts.get("visual_evidence") or ""),
        "highlight_candidates": str(artifacts.get("highlight_candidates") or ""),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


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
                capabilities = TASK_CAPABILITIES.get(str(task.get("kind") or ""), set())
                can_resume = (
                    "resume" in capabilities
                    and task.get("status") in {"failed", "interrupted", "cancelled"}
                )
                can_cancel = (
                    "cancel" in capabilities
                    and task.get("status") in {"queued", "running"}
                )
                if controls[0].button(
                    "继续", key=f"task-resume-{task['task_id']}", disabled=not can_resume
                ):
                    try:
                        _resume_project_task(project, task)
                        st.rerun()
                    except Exception as error:
                        st.error(f"无法继续任务：{error}")
                if controls[1].button(
                    "取消", key=f"task-cancel-{task['task_id']}", disabled=not can_cancel
                ):
                    try:
                        _cancel_project_task(project, task)
                        st.rerun()
                    except Exception as error:
                        st.error(f"无法取消任务：{error}")
                if controls[2].button("查看诊断", key=f"task-diag-{task['task_id']}"):
                    diagnostic = project_store().task_diagnostic_projection(
                        project["project_id"], task["task_id"]
                    )
                    st.json(diagnostic)
                if not capabilities:
                    st.caption("该任务仅提供诊断；请回到对应阶段重新运行。")
    else:
        st.info("当前没有项目任务。")


def _resume_project_task(project: dict, task: dict) -> None:
    kind = str(task.get("kind") or "")
    if kind == "visual_analysis":
        from webui.tools.generate_film_vision_fusion import resume_local_visual_analysis

        resume_local_visual_analysis(task["task_id"])
    elif kind == "fusion_matching":
        from webui.tools.generate_short_summary import resume_fusion_matching_task

        resume_fusion_matching_task(task["task_id"])
    elif kind == "narration_generation":
        _start_narration_generation(project["project_id"])
    elif kind == "fusion_plan":
        _start_fusion_plan_generation(project["project_id"])
    elif kind == "render":
        finalization = dict(
            (project.get("artifact_refs") or {}).get("finalization") or {}
        )
        _start_project_render(project, project_store(), finalization)
    else:
        raise ValueError(f"该任务类型暂不支持继续：{kind}")


def _cancel_project_task(project: dict, task: dict) -> None:
    kind = str(task.get("kind") or "")
    if kind == "visual_analysis":
        from webui.tools.generate_film_vision_fusion import cancel_local_visual_analysis

        cancel_local_visual_analysis(task["task_id"])
    elif kind == "fusion_matching":
        from webui.tools.generate_short_summary import cancel_fusion_matching_task

        cancel_fusion_matching_task(task["task_id"])
    elif kind in {"narration_generation", "fusion_plan"}:
        project_store().cancel_task_run(
            project["project_id"], task_id=task["task_id"],
            run_id=str(task.get("run_id") or ""),
        )
    else:
        raise ValueError(f"该任务类型暂不支持取消：{kind}")

import streamlit as st
import os
import shutil
from loguru import logger

from app.config import config
from app.utils import ffmpeg_detector, ffmpeg_utils
from app.utils.utils import storage_dir


def clear_directory(dir_path, tr):
    """清理指定目录"""
    if os.path.exists(dir_path):
        try:
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    logger.error(f"Failed to delete {item_path}: {e}")
            st.success(tr("Directory cleared"))
            logger.info(f"Cleared directory: {dir_path}")
        except Exception as e:
            st.error(f"{tr('Failed to clear directory')}: {str(e)}")
            logger.error(f"Failed to clear directory {dir_path}: {e}")
    else:
        st.warning(tr("Directory does not exist"))


def _format_engine_label(engines_by_path, tr):
    def formatter(path):
        engine = engines_by_path.get(path, {})
        source = engine.get("source", "")
        source_key = f"FFmpeg source {source}"
        translated_source = tr(source_key)
        if translated_source == source_key:
            translated_source = source

        version = str(engine.get("version_line", "")).replace("ffmpeg version", "").strip()
        version = version or "unknown version"
        status = _status_text(engine.get("available"), tr)
        return f"{translated_source} - {version} - {path} ({status})"

    return formatter


def _status_text(value, tr):
    return tr("Available") if value else tr("Unavailable")


def _render_ffmpeg_report(report, tr):
    st.write(f"**{tr('FFmpeg detection details')}**")
    st.caption(f"{tr('Path')}: {report.get('path', '')}")
    if report.get("version_line"):
        st.caption(f"{tr('Version')}: {report['version_line']}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("FFmpeg", _status_text(report.get("ffmpeg_available"), tr))
    with col2:
        st.metric("FFprobe", _status_text(report.get("ffprobe_available"), tr))
    with col3:
        hwaccel = report.get("hardware_acceleration", {})
        st.metric(tr("Hardware Acceleration"), _status_text(hwaccel.get("available"), tr))
    with col4:
        subtitle_burn = report.get("subtitle_burn", {})
        st.metric(tr("Subtitle Burn-in"), _status_text(subtitle_burn.get("available"), tr))

    if report.get("ffmpeg_available") and report.get("subtitle_burn", {}).get("available"):
        if report.get("hardware_acceleration", {}).get("available"):
            st.success(tr("FFmpeg engine passed all checks"))
        else:
            st.warning(tr("FFmpeg engine works but hardware acceleration is unavailable"))
    else:
        st.error(tr("FFmpeg engine check failed"))

    hwaccel = report.get("hardware_acceleration", {})
    subtitle_burn = report.get("subtitle_burn", {})
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**{tr('Hardware acceleration detail')}**")
        st.write(f"- {tr('Type')}: {hwaccel.get('type') or '-'}")
        st.write(f"- {tr('Encoder')}: {hwaccel.get('encoder') or '-'}")
        st.write(f"- {tr('Message')}: {hwaccel.get('message') or '-'}")
        hwaccels = report.get("hwaccels") or []
        st.write(f"- {tr('Supported Hardware Methods')}: {', '.join(hwaccels) if hwaccels else '-'}")
    with col2:
        filters = subtitle_burn.get("filters") or {}
        st.write(f"**{tr('Subtitle burn-in detail')}**")
        st.write(f"- {tr('Method')}: {subtitle_burn.get('method') or '-'}")
        st.write(f"- {tr('Message')}: {subtitle_burn.get('message') or '-'}")
        st.write(
            "- "
            + tr("Subtitle Filters")
            + ": "
            + ", ".join(
                f"{name}={_status_text(enabled, tr)}"
                for name, enabled in filters.items()
            )
        )

    errors = report.get("errors") or []
    if errors:
        with st.expander(tr("FFmpeg errors")):
            for error in errors:
                st.write(f"- {error}")

    with st.expander(tr("Raw FFmpeg report")):
        st.json(report)


def render_ffmpeg_engine_settings(tr):
    """Render FFmpeg engine discovery, selection and diagnostics."""
    st.divider()
    st.subheader(tr("FFmpeg Engine Detection"))

    engines = ffmpeg_detector.discover_ffmpeg_engines(
        configured_path=config.app.get("ffmpeg_path", ""),
        root_dir=config.root_dir,
    )
    engines_by_path = {engine["path"]: engine for engine in engines}
    engine_paths = list(engines_by_path.keys())

    if not engine_paths:
        st.warning(tr("No FFmpeg engines found"))

    current_path = config.app.get("ffmpeg_path", "")
    selected_index = 0
    if current_path in engines_by_path:
        selected_index = engine_paths.index(current_path)

    selected_path = ""
    if engine_paths:
        selected_path = st.selectbox(
            tr("FFmpeg Engine"),
            options=engine_paths,
            index=selected_index,
            format_func=_format_engine_label(engines_by_path, tr),
            help=tr("FFmpeg Engine Help"),
        )

    custom_path = st.text_input(
        tr("Custom FFmpeg Path"),
        value="",
        help=tr("Custom FFmpeg Path Help"),
        placeholder="/path/to/ffmpeg",
    ).strip()
    effective_path = custom_path or selected_path

    active_path = config.app.get("ffmpeg_path", "")
    if active_path:
        st.caption(f"{tr('Current FFmpeg Engine')}: {active_path}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button(tr("Save FFmpeg Engine"), use_container_width=True, disabled=not effective_path):
            try:
                if not os.path.isfile(effective_path):
                    st.error(tr("Selected FFmpeg path is invalid"))
                else:
                    config.app["ffmpeg_path"] = effective_path
                    config.ffmpeg_path = effective_path
                    config.apply_ffmpeg_path(effective_path)
                    config.save_config()
                    ffmpeg_utils.reset_hwaccel_detection()
                    st.success(tr("FFmpeg engine saved"))
            except Exception as e:
                st.error(f"{tr('Failed to save config')}: {str(e)}")
                logger.error(f"保存 FFmpeg 引擎失败: {e}")

    with col2:
        if st.button(tr("Test Selected FFmpeg"), use_container_width=True, disabled=not effective_path):
            with st.spinner(tr("Testing FFmpeg engine")):
                try:
                    st.session_state["ffmpeg_engine_report"] = ffmpeg_detector.validate_ffmpeg_engine(effective_path)
                except Exception as e:
                    st.error(f"{tr('FFmpeg engine check failed')}: {str(e)}")
                    logger.error(f"FFmpeg 引擎检测失败: {e}")

    report = st.session_state.get("ffmpeg_engine_report")
    if report:
        _render_ffmpeg_report(report, tr)


def render_system_panel(tr):
    """渲染系统设置面板"""
    with st.expander(tr("System settings"), expanded=False):
        col1, col2, col3 = st.columns(3)
                
        with col1:
            if st.button(tr("Clear frames"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "temp/keyframes"), tr)
                
        with col2:
            if st.button(tr("Clear clip videos"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "temp/clip_video"), tr)
                
        with col3:
            if st.button(tr("Clear tasks"), use_container_width=True):
                clear_directory(os.path.join(storage_dir(), "tasks"), tr)

        render_ffmpeg_engine_settings(tr)

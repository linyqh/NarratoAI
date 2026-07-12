import streamlit as st
from app.config import config
from app.utils import utils
from webui.utils.cache import get_fonts_cache
import hashlib
import os


SUBTITLE_MASK_DEFAULTS = {
    "landscape": {
        "x_percent": 10,
        "y_percent": 78,
        "width_percent": 80,
        "height_percent": 14,
        "blur_radius": 18,
        "opacity_percent": 82,
    },
    "portrait": {
        "x_percent": 8,
        "y_percent": 79,
        "width_percent": 84,
        "height_percent": 16,
        "blur_radius": 26,
        "opacity_percent": 84,
    },
}

SUBTITLE_POSITION_DEFAULTS = {
    "landscape": {
        "y_percent": 85,
    },
    "portrait": {
        "y_percent": 82,
    },
}


VIDEO_PREVIEW_UPLOAD_TYPES = ["mp4", "mov", "avi", "flv", "mkv", "mpeg4"]

SUBTITLE_SAFE_AREA_PREVIEW_IMAGES = {
    "portrait": "subtitle_safe_area_portrait.png",
    "landscape": "subtitle_safe_area_landscape.png",
}

SUBTITLE_PREVIEW_FALLBACK_SIZES = {
    "portrait": (1080, 1920),
    "landscape": (1920, 1080),
}

SUBTITLE_PREVIEW_ORIENTATIONS = ("portrait", "landscape")

SUBTITLE_PREVIEW_ORIENTATION_LABELS = {
    "portrait": "Portrait Safe Area",
    "landscape": "Landscape Safe Area",
}


def render_subtitle_panel(tr):
    """渲染字幕设置面板"""
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))

        tts_engine = config.ui.get('tts_engine', '')
        is_disabled_subtitle = is_disabled_subtitle_settings(tts_engine)

        if is_disabled_subtitle:
            st.warning(tr("TTS engine does not support precise subtitles").format(engine=tts_engine))

        enable_subtitles = st.checkbox(tr("Enable Subtitles"), value=True)
        st.session_state['subtitle_enabled'] = enable_subtitles

        if enable_subtitles:
            render_subtitle_mask_settings(tr)
            render_auto_transcription_settings(tr)
            render_font_settings(tr)
            render_position_settings(tr)
            render_style_settings(tr)
        else:
            st.session_state['subtitle_mask_enabled'] = False
            config.ui["subtitle_mask_enabled"] = False
            st.session_state['subtitle_auto_transcribe_enabled'] = False
            config.fun_asr["auto_transcribe_enabled"] = False


def _subtitle_mask_key(orientation, field):
    return f"subtitle_mask_{orientation}_{field}"


def _get_subtitle_mask_value(orientation, field):
    key = _subtitle_mask_key(orientation, field)
    return config.ui.get(key, SUBTITLE_MASK_DEFAULTS[orientation][field])


def _set_subtitle_mask_value(orientation, field, value):
    key = _subtitle_mask_key(orientation, field)
    config.ui[key] = value
    st.session_state[key] = value


def _subtitle_position_key(orientation, field):
    return f"subtitle_position_{orientation}_{field}"


def _get_orientation_subtitle_position_value(orientation, field):
    key = _subtitle_position_key(orientation, field)
    return config.ui.get(key, SUBTITLE_POSITION_DEFAULTS[orientation][field])


def _set_orientation_subtitle_position_value(orientation, field, value):
    key = _subtitle_position_key(orientation, field)
    config.ui[key] = value
    st.session_state[key] = value


def _format_preview_time(seconds):
    seconds = max(0.0, float(seconds or 0))
    minutes = int(seconds // 60)
    remaining_seconds = seconds - minutes * 60
    return f"{minutes:02d}:{remaining_seconds:04.1f}"


def _get_current_preview_video_path():
    uploaded_path = st.session_state.get("subtitle_mask_preview_video_path")
    if uploaded_path and os.path.exists(uploaded_path):
        return uploaded_path

    video_path = st.session_state.get("video_origin_path", "")
    if isinstance(video_path, str) and video_path and os.path.exists(video_path):
        return video_path

    video_paths = st.session_state.get("video_origin_paths", [])
    if isinstance(video_paths, list):
        for path in video_paths:
            if isinstance(path, str) and path and os.path.exists(path):
                return path

    return ""


def _normalize_subtitle_preview_orientation(value, tr=None):
    if value in SUBTITLE_PREVIEW_ORIENTATIONS:
        return value

    labels = {
        label: orientation
        for orientation, label in SUBTITLE_PREVIEW_ORIENTATION_LABELS.items()
    }
    if tr:
        labels.update(
            {
                tr(label): orientation
                for orientation, label in SUBTITLE_PREVIEW_ORIENTATION_LABELS.items()
            }
        )

    return labels.get(str(value), "portrait")


def _save_subtitle_mask_preview_video(uploaded_file):
    if uploaded_file is None:
        return ""

    signature = f"{uploaded_file.name}:{uploaded_file.size}"
    existing_signature = st.session_state.get("subtitle_mask_preview_upload_signature")
    existing_path = st.session_state.get("subtitle_mask_preview_video_path", "")
    if signature == existing_signature and existing_path and os.path.exists(existing_path):
        return existing_path

    target_dir = utils.temp_dir("subtitle_mask_preview")
    safe_name = os.path.basename(uploaded_file.name).strip() or "preview.mp4"
    digest = hashlib.md5(signature.encode("utf-8")).hexdigest()[:10]
    preview_path = os.path.join(target_dir, f"{digest}_{safe_name}")

    with open(preview_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.session_state["subtitle_mask_preview_upload_signature"] = signature
    st.session_state["subtitle_mask_preview_video_path"] = preview_path
    return preview_path


def _video_mtime(video_path):
    try:
        return os.path.getmtime(video_path)
    except OSError:
        return 0


@st.cache_data(show_spinner=False)
def _probe_subtitle_mask_preview_video(video_path, mtime):
    from moviepy import VideoFileClip

    clip = VideoFileClip(video_path)
    try:
        return {
            "duration": float(clip.duration or 0),
            "width": int(clip.w),
            "height": int(clip.h),
        }
    finally:
        clip.close()


@st.cache_data(show_spinner=False)
def _extract_subtitle_mask_preview_frame(video_path, timestamp, mtime):
    import numpy as np
    from moviepy import VideoFileClip

    clip = VideoFileClip(video_path)
    try:
        safe_time = min(max(float(timestamp or 0), 0.0), max(float(clip.duration or 0), 0.0))
        frame = np.asarray(clip.get_frame(safe_time))
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        return frame
    finally:
        clip.close()


def _build_subtitle_mask_preview_options():
    options = {"subtitle_mask_enabled": True}
    for orientation in ("landscape", "portrait"):
        for field in ("x_percent", "y_percent", "width_percent", "height_percent", "blur_radius", "opacity_percent"):
            options[_subtitle_mask_key(orientation, field)] = _get_subtitle_mask_value(orientation, field)
        options[_subtitle_position_key(orientation, "y_percent")] = _get_orientation_subtitle_position_value(
            orientation,
            "y_percent",
        )
    return options


def _draw_subtitle_mask_preview(frame):
    from PIL import Image, ImageDraw
    from app.services.generate_video import _resolve_subtitle_mask_region

    image = Image.fromarray(frame).convert("RGBA")
    region = _resolve_subtitle_mask_region(image.width, image.height, _build_subtitle_mask_preview_options())

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rect = (
        region["x"],
        region["y"],
        region["x"] + region["width"],
        region["y"] + region["height"],
    )
    draw.rounded_rectangle(
        rect,
        radius=region["corner_radius"],
        fill=(0, 0, 0, 96),
        outline=(255, 75, 85, 235),
        width=max(2, round(min(image.width, image.height) * 0.004)),
    )
    subtitle_y_percent = _get_orientation_subtitle_position_value(region["orientation"], "y_percent")
    subtitle_y = round((image.height - 1) * subtitle_y_percent / 100)
    line_width = max(2, round(min(image.width, image.height) * 0.004))
    draw.line(
        (0, subtitle_y, image.width, subtitle_y),
        fill=(59, 130, 246, 220),
        width=line_width,
    )
    image.alpha_composite(overlay)
    return image.convert("RGB"), region


def _resize_subtitle_mask_preview_image(image, max_width=520, max_height=360):
    image = image.copy()
    image.thumbnail((max_width, max_height))
    return image


def _render_subtitle_mask_preview(tr):
    st.subheader(tr("Subtitle Mask Preview"))

    uploaded_path = st.session_state.get("subtitle_mask_preview_video_path", "")
    if uploaded_path and os.path.exists(uploaded_path):
        preview_cols = st.columns([0.68, 0.32], vertical_alignment="center")
        with preview_cols[0]:
            st.caption(
                tr("Using Subtitle Mask Preview Video").format(
                    file=os.path.basename(uploaded_path)
                )
            )
        with preview_cols[1]:
            if st.button(
                tr("Change Subtitle Mask Preview Video"),
                key="change_subtitle_mask_preview_video",
                use_container_width=True,
            ):
                st.session_state.pop("subtitle_mask_preview_video_path", None)
                st.session_state.pop("subtitle_mask_preview_upload_signature", None)
                st.rerun(scope="fragment")
    else:
        uploaded_file = st.file_uploader(
            tr("Upload Subtitle Mask Preview Video"),
            type=VIDEO_PREVIEW_UPLOAD_TYPES,
            key="subtitle_mask_preview_video_uploader",
            help=tr("Upload Subtitle Mask Preview Video Help"),
        )
        uploaded_path = _save_subtitle_mask_preview_video(uploaded_file)
        if uploaded_path:
            st.rerun(scope="fragment")

    preview_video_path = uploaded_path or _get_current_preview_video_path()

    if not preview_video_path:
        st.info(tr("Subtitle Mask Preview Empty"))
        return

    try:
        mtime = _video_mtime(preview_video_path)
        video_info = _probe_subtitle_mask_preview_video(preview_video_path, mtime)
        duration = max(0.0, video_info["duration"])
        if duration <= 0:
            st.warning(tr("Subtitle Mask Preview Failed"))
            return

        selected_time = st.slider(
            tr("Subtitle Mask Preview Timeline"),
            min_value=0.0,
            max_value=duration,
            value=min(float(st.session_state.get("subtitle_mask_preview_time", 0.0)), duration),
            step=0.1,
            format="%.1f",
            key="subtitle_mask_preview_time",
            help=tr("Subtitle Mask Preview Timeline Help"),
        )
        frame = _extract_subtitle_mask_preview_frame(preview_video_path, selected_time, mtime)
        preview_image, region = _draw_subtitle_mask_preview(frame)
        preview_image = _resize_subtitle_mask_preview_image(preview_image, max_width=420, max_height=280)
        st.image(
            preview_image,
            caption=tr("Subtitle Mask Preview Frame Caption").format(
                time=_format_preview_time(selected_time),
                orientation=tr("Portrait") if region["orientation"] == "portrait" else tr("Landscape"),
            ),
        )
    except Exception:
        st.warning(tr("Subtitle Mask Preview Failed"))


def _render_subtitle_mask_region_controls(tr, orientation):
    x_percent = st.slider(
        tr("Subtitle Mask Left"),
        min_value=0,
        max_value=99,
        value=int(_get_subtitle_mask_value(orientation, "x_percent")),
        help=tr("Subtitle Mask Left Help"),
        key=f"{orientation}_subtitle_mask_x_percent",
    )
    _set_subtitle_mask_value(orientation, "x_percent", x_percent)

    y_percent = st.slider(
        tr("Subtitle Mask Top"),
        min_value=0,
        max_value=99,
        value=int(_get_subtitle_mask_value(orientation, "y_percent")),
        help=tr("Subtitle Mask Top Help"),
        key=f"{orientation}_subtitle_mask_y_percent",
    )
    _set_subtitle_mask_value(orientation, "y_percent", y_percent)

    max_width = max(2, 100 - x_percent)
    width_widget_key = f"{orientation}_subtitle_mask_width_percent"
    if st.session_state.get(width_widget_key, 2) < 2:
        st.session_state[width_widget_key] = 2
    if st.session_state.get(width_widget_key, 0) > max_width:
        st.session_state[width_widget_key] = max_width
    width_percent = st.slider(
        tr("Subtitle Mask Width"),
        min_value=2,
        max_value=max_width,
        value=min(int(_get_subtitle_mask_value(orientation, "width_percent")), max_width),
        help=tr("Subtitle Mask Width Help"),
        key=width_widget_key,
    )
    _set_subtitle_mask_value(orientation, "width_percent", width_percent)

    max_height = max(2, 100 - y_percent)
    height_widget_key = f"{orientation}_subtitle_mask_height_percent"
    if st.session_state.get(height_widget_key, 2) < 2:
        st.session_state[height_widget_key] = 2
    if st.session_state.get(height_widget_key, 0) > max_height:
        st.session_state[height_widget_key] = max_height
    height_percent = st.slider(
        tr("Subtitle Mask Height"),
        min_value=2,
        max_value=max_height,
        value=min(int(_get_subtitle_mask_value(orientation, "height_percent")), max_height),
        help=tr("Subtitle Mask Height Help"),
        key=height_widget_key,
    )
    _set_subtitle_mask_value(orientation, "height_percent", height_percent)

    blur_radius = st.slider(
        tr("Subtitle Mask Blur Radius"),
        min_value=0,
        max_value=200,
        value=int(_get_subtitle_mask_value(orientation, "blur_radius")),
        help=tr("Subtitle Mask Blur Radius Help"),
        key=f"{orientation}_subtitle_mask_blur_radius",
    )
    _set_subtitle_mask_value(orientation, "blur_radius", blur_radius)

    opacity_percent = st.slider(
        tr("Subtitle Mask Opacity"),
        min_value=0,
        max_value=100,
        value=int(_get_subtitle_mask_value(orientation, "opacity_percent")),
        help=tr("Subtitle Mask Opacity Help"),
        key=f"{orientation}_subtitle_mask_opacity_percent",
    )
    _set_subtitle_mask_value(orientation, "opacity_percent", opacity_percent)


def _render_subtitle_position_controls(tr, orientation):
    label = tr("Portrait Subtitle Position") if orientation == "portrait" else tr("Landscape Subtitle Position")
    y_percent = st.slider(
        label,
        min_value=0,
        max_value=99,
        value=int(_get_orientation_subtitle_position_value(orientation, "y_percent")),
        help=tr("Subtitle Burn Position Help"),
        key=f"{orientation}_subtitle_burn_y_percent",
    )
    _set_orientation_subtitle_position_value(orientation, "y_percent", y_percent)


def _render_subtitle_mask_dialog(tr):
    @st.dialog(tr("Subtitle Mask Settings"), width="large")
    def subtitle_mask_dialog():
        preview_col, settings_col = st.columns([1, 1], vertical_alignment="top")

        with settings_col:
            st.caption(tr("Subtitle Mask Settings Caption"))
            st.caption(tr("Subtitle Mask Preview Caption"))
            landscape_mask_tab, portrait_mask_tab = st.tabs([
                tr("Landscape Subtitle Mask"),
                tr("Portrait Subtitle Mask"),
            ])
            with landscape_mask_tab:
                _render_subtitle_mask_region_controls(tr, "landscape")
            with portrait_mask_tab:
                _render_subtitle_mask_region_controls(tr, "portrait")

        with preview_col:
            _render_subtitle_mask_preview(tr)

        if st.button(tr("Save Subtitle Mask Settings"), type="primary", use_container_width=True):
            config.save_config()
            st.rerun()

    subtitle_mask_dialog()


def render_subtitle_mask_settings(tr):
    """渲染原字幕遮罩设置。"""
    mask_enabled = st.checkbox(
        tr("Enable Subtitle Mask"),
        value=bool(config.ui.get("subtitle_mask_enabled", False)),
        help=tr("Enable Subtitle Mask Help"),
        key="subtitle_mask_enabled_checkbox",
    )
    st.session_state['subtitle_mask_enabled'] = mask_enabled
    config.ui["subtitle_mask_enabled"] = mask_enabled

    if not mask_enabled:
        return

    button_col, summary_col = st.columns([0.35, 0.65], vertical_alignment="center")
    with button_col:
        if st.button(tr("Set Subtitle Mask"), key="set_subtitle_mask", use_container_width=True):
            _render_subtitle_mask_dialog(tr)
    with summary_col:
        st.caption(
            tr("Subtitle Mask Summary").format(
                landscape_x=_get_subtitle_mask_value("landscape", "x_percent"),
                landscape_y=_get_subtitle_mask_value("landscape", "y_percent"),
                landscape_width=_get_subtitle_mask_value("landscape", "width_percent"),
                landscape_height=_get_subtitle_mask_value("landscape", "height_percent"),
                portrait_x=_get_subtitle_mask_value("portrait", "x_percent"),
                portrait_y=_get_subtitle_mask_value("portrait", "y_percent"),
                portrait_width=_get_subtitle_mask_value("portrait", "width_percent"),
                portrait_height=_get_subtitle_mask_value("portrait", "height_percent"),
            )
        )


def _get_saved_auto_transcribe_backend():
    saved_backend = str(config.fun_asr.get("backend", "")).strip().lower()
    if saved_backend not in {"local", "firered", "bailian"}:
        saved_backend = (
            "bailian"
            if config.fun_asr.get("api_key") and not config.fun_asr.get("api_url")
            else "local"
        )
    return saved_backend


def render_auto_transcription_settings(tr):
    """渲染最终视频自动转录设置。"""
    from app.services import fun_asr_subtitle

    auto_transcribe_enabled = st.checkbox(
        tr("Enable Auto Transcription"),
        value=bool(config.fun_asr.get("auto_transcribe_enabled", False)),
        help=tr("Enable Auto Transcription Help"),
        key="subtitle_auto_transcribe_enabled_checkbox",
    )
    st.session_state['subtitle_auto_transcribe_enabled'] = auto_transcribe_enabled
    config.fun_asr["auto_transcribe_enabled"] = auto_transcribe_enabled

    backend = _get_saved_auto_transcribe_backend()
    api_url = config.fun_asr.get("api_url", fun_asr_subtitle.LOCAL_FUN_ASR_API_URL)
    firered_api_url = config.fun_asr.get("firered_api_url", fun_asr_subtitle.LOCAL_FIRERED_ASR_API_URL)
    hotword = config.fun_asr.get("hotword", "")
    enable_spk = bool(config.fun_asr.get("enable_spk", False))
    api_key = config.fun_asr.get("api_key", "")

    if not auto_transcribe_enabled:
        st.session_state['subtitle_auto_transcribe_backend'] = backend
        st.session_state['subtitle_auto_transcribe_api_url'] = api_url
        st.session_state['subtitle_auto_transcribe_firered_api_url'] = firered_api_url
        st.session_state['subtitle_auto_transcribe_hotword'] = hotword
        st.session_state['subtitle_auto_transcribe_enable_spk'] = enable_spk
        st.session_state['subtitle_auto_transcribe_api_key'] = api_key
        return

    backend_options = {
        tr("Local FunASR-Pack API"): "local",
        tr("Local FireRedASR API"): "firered",
        tr("Ali Bailian Online Fun-ASR"): "bailian",
    }
    backend_values = list(backend_options.values())
    backend_labels = list(backend_options.keys())

    backend_label = st.selectbox(
        tr("Subtitle Processing Method"),
        options=backend_labels,
        index=backend_values.index(backend),
        key="subtitle_auto_transcribe_backend_select",
    )
    backend = backend_options[backend_label]

    if backend == "local":
        st.caption(tr("Auto Transcription Local Caption"))
        api_url = st.text_input(
            tr("Local FunASR-Pack API URL"),
            value=api_url,
            help=tr("Local FunASR-Pack API URL Help"),
            key="subtitle_auto_transcribe_api_url_input",
        )
        hotword = st.text_input(
            tr("Fun-ASR Hotword"),
            value=hotword,
            help=tr("Fun-ASR Hotword Help"),
            key="subtitle_auto_transcribe_hotword_input",
        )
        enable_spk = st.checkbox(
            tr("Enable speaker diarization"),
            value=enable_spk,
            help=tr("Enable speaker diarization Help"),
            key="subtitle_auto_transcribe_enable_spk_checkbox",
        )
    elif backend == "firered":
        st.caption(tr("Auto Transcription FireRed Caption"))
        firered_api_url = st.text_input(
            tr("Local FireRedASR API URL"),
            value=firered_api_url,
            help=tr("Local FireRedASR API URL Help"),
            key="subtitle_auto_transcribe_firered_api_url_input",
        )
    else:
        st.caption(tr("Auto Transcription Online Caption"))
        st.markdown(
            f"{tr('API Key URL')}: "
            "[https://bailian.console.aliyun.com/?tab=model#/api-key]"
            "(https://bailian.console.aliyun.com/?tab=model#/api-key)"
        )
        api_key = st.text_input(
            tr("Ali Bailian API Key"),
            value=api_key,
            type="password",
            help=tr("Ali Bailian API Key Help"),
            key="subtitle_auto_transcribe_api_key_input",
        )

    config.fun_asr["backend"] = backend
    config.fun_asr["api_url"] = str(api_url).strip()
    config.fun_asr["firered_api_url"] = str(firered_api_url).strip()
    config.fun_asr["api_key"] = str(api_key).strip()
    config.fun_asr["hotword"] = str(hotword).strip()
    config.fun_asr["enable_spk"] = bool(enable_spk)
    config.fun_asr["model"] = "fun-asr"

    st.session_state['subtitle_auto_transcribe_backend'] = backend
    st.session_state['subtitle_auto_transcribe_api_url'] = str(api_url).strip()
    st.session_state['subtitle_auto_transcribe_firered_api_url'] = str(firered_api_url).strip()
    st.session_state['subtitle_auto_transcribe_api_key'] = str(api_key).strip()
    st.session_state['subtitle_auto_transcribe_hotword'] = str(hotword).strip()
    st.session_state['subtitle_auto_transcribe_enable_spk'] = bool(enable_spk)


def render_font_settings(tr):
    """渲染字体设置"""
    # 获取字体列表
    font_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resource", "fonts")
    font_names = get_fonts_cache(font_dir)

    # 获取保存的字体设置
    saved_font_name = config.ui.get("font_name", "")
    saved_font_name_index = 0
    if saved_font_name in font_names:
        saved_font_name_index = font_names.index(saved_font_name)

    # 字体选择
    font_name = st.selectbox(
        tr("Font"),
        options=font_names,
        index=saved_font_name_index
    )
    config.ui["font_name"] = font_name
    st.session_state['font_name'] = font_name

    # 字体大小 和 字幕大小
    font_cols = st.columns([0.3, 0.7])
    with font_cols[0]:
        saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
        text_fore_color = st.color_picker(
            tr("Font Color"),
            saved_text_fore_color
        )
        config.ui["text_fore_color"] = text_fore_color
        st.session_state['text_fore_color'] = text_fore_color

    with font_cols[1]:
        saved_font_size = config.ui.get("font_size", 60)
        saved_font_size = max(20, min(160, int(saved_font_size)))
        font_size = st.slider(
            tr("Font Size"),
            min_value=20,
            max_value=160,
            value=saved_font_size
        )
        config.ui["font_size"] = font_size
        st.session_state['font_size'] = font_size


def is_disabled_subtitle_settings(tts_engine:str)->bool:
    """是否禁用字幕设置"""
    return tts_engine=="soulvoice" or tts_engine=="qwen3_tts" or tts_engine==config.OMNIVOICE_ENGINE

def render_position_settings(tr):
    """渲染位置设置"""
    subtitle_positions = [
        (tr("Top"), "top"),
        (tr("Center"), "center"),
        (tr("Bottom"), "bottom"),
        (tr("Custom"), "custom"),
    ]

    selected_index = st.selectbox(
        tr("Position"),
        index=2,
        options=range(len(subtitle_positions)),
        format_func=lambda x: subtitle_positions[x][0],
    )

    subtitle_position = subtitle_positions[selected_index][1]
    st.session_state['subtitle_position'] = subtitle_position

    # 自定义位置处理
    if subtitle_position == "custom":
        custom_position = st.text_input(
            tr("Custom Position (% from top)"),
            value="70.0"
        )
        try:
            custom_position_value = float(custom_position)
            if custom_position_value < 0 or custom_position_value > 100:
                st.error(tr("Please enter a value between 0 and 100"))
            else:
                st.session_state['custom_position'] = custom_position_value
        except ValueError:
            st.error(tr("Please enter a valid number"))


def _resolve_subtitle_preview_font_path(font_name):
    if not font_name:
        return ""

    font_name = str(font_name)
    candidates = []
    if os.path.isabs(font_name):
        candidates.append(font_name)

    candidates.extend(
        [
            os.path.join(utils.font_dir(), font_name),
            os.path.join(utils.font_dir(), os.path.basename(font_name)),
        ]
    )

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return ""


def _load_subtitle_preview_font(font_name, font_size):
    from PIL import ImageFont

    font_path = _resolve_subtitle_preview_font_path(font_name)
    font_size = max(12, int(round(font_size or 60)))
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            pass

    return ImageFont.load_default(size=font_size)


def _resolve_subtitle_preview_color(color, fallback):
    from PIL import ImageColor

    try:
        value = ImageColor.getrgb(str(color or fallback).strip())
    except ValueError:
        value = ImageColor.getrgb(fallback)

    if len(value) == 4:
        return value
    return (*value, 255)


def _get_subtitle_preview_y(image_height, text_height, orientation):
    subtitle_position = st.session_state.get("subtitle_position", "bottom")

    if subtitle_position == "top":
        return max(12, round(image_height * 0.05))
    if subtitle_position == "center":
        return max(0, round((image_height - text_height) / 2))

    y_percent = _get_orientation_subtitle_position_value(orientation, "y_percent")
    if y_percent is None and subtitle_position == "custom":
        y_percent = st.session_state.get("custom_position", 70.0)

    try:
        y_percent = max(0.0, min(100.0, float(y_percent)))
    except (TypeError, ValueError):
        y_percent = 85.0

    return max(0, round((image_height - text_height) * y_percent / 100))


def _get_subtitle_preview_background(orientation):
    from PIL import Image

    image_path = os.path.join(
        utils.resource_dir("safe_areas"),
        SUBTITLE_SAFE_AREA_PREVIEW_IMAGES.get(orientation, SUBTITLE_SAFE_AREA_PREVIEW_IMAGES["portrait"]),
    )

    if os.path.exists(image_path):
        return Image.open(image_path).convert("RGBA")

    width, height = SUBTITLE_PREVIEW_FALLBACK_SIZES.get(orientation, SUBTITLE_PREVIEW_FALLBACK_SIZES["portrait"])
    return Image.new("RGBA", (width, height), (19, 24, 35, 255))


def _render_subtitle_preview_image(tr):
    from PIL import ImageDraw

    font_name = st.session_state.get("font_name") or config.ui.get("font_name", "")
    font_size = int(st.session_state.get("font_size", config.ui.get("font_size", 60)) or 60)
    text_color = st.session_state.get("text_fore_color", config.ui.get("text_fore_color", "#FFFFFF"))
    stroke_color = st.session_state.get("stroke_color", config.ui.get("stroke_color", "#000000"))
    stroke_width = float(st.session_state.get("stroke_width", config.ui.get("stroke_width", 1.5)) or 0)

    orientation_default = _normalize_subtitle_preview_orientation(
        st.session_state.get("subtitle_preview_orientation", "portrait"),
        tr,
    )
    st.session_state["subtitle_preview_orientation"] = orientation_default

    orientation = st.pills(
        tr("Subtitle Preview Orientation"),
        options=SUBTITLE_PREVIEW_ORIENTATIONS,
        format_func=lambda value: tr(SUBTITLE_PREVIEW_ORIENTATION_LABELS[value]),
        key="subtitle_preview_orientation",
        width="stretch",
    ) or orientation_default
    _render_subtitle_position_controls(tr, orientation)

    preview_text = tr("Subtitle Preview Sample Text")
    image = _get_subtitle_preview_background(orientation)
    draw = ImageDraw.Draw(image)

    font = _load_subtitle_preview_font(font_name, font_size)
    stroke_width_px = max(0, int(round(stroke_width)))
    bbox = draw.textbbox((0, 0), preview_text, font=font, stroke_width=stroke_width_px)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = max(20, round((image.width - text_width) / 2))
    y = _get_subtitle_preview_y(image.height, text_height, orientation)
    margin = max(10, stroke_width_px * 2 + 6)
    y = max(margin, min(y, image.height - text_height - margin))

    draw.text(
        (x - bbox[0], y - bbox[1]),
        preview_text,
        font=font,
        fill=_resolve_subtitle_preview_color(text_color, "#FFFFFF"),
        stroke_width=stroke_width_px,
        stroke_fill=_resolve_subtitle_preview_color(stroke_color, "#000000"),
    )

    st.image(image.convert("RGB"), width="stretch", output_format="PNG")


def render_style_settings(tr):
    """渲染样式设置"""
    stroke_cols = st.columns([0.3, 0.7])

    with stroke_cols[0]:
        stroke_color = st.color_picker(
            tr("Stroke Color"),
            value="#000000"
        )
        st.session_state['stroke_color'] = stroke_color

    with stroke_cols[1]:
        stroke_width = st.slider(
            tr("Stroke Width"),
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.01
        )
        st.session_state['stroke_width'] = stroke_width

    with st.expander(tr("Subtitle Preview"), expanded=False):
        _render_subtitle_preview_image(tr)


def get_subtitle_params():
    """获取字幕参数"""
    font_name = st.session_state.get('font_name') or "SimHei"
    return {
        'subtitle_enabled': st.session_state.get('subtitle_enabled', True),
        'subtitle_mask_enabled': st.session_state.get('subtitle_mask_enabled', False),
        'subtitle_mask_landscape_x_percent': _get_subtitle_mask_value("landscape", "x_percent"),
        'subtitle_mask_landscape_y_percent': _get_subtitle_mask_value("landscape", "y_percent"),
        'subtitle_mask_landscape_width_percent': _get_subtitle_mask_value("landscape", "width_percent"),
        'subtitle_mask_landscape_height_percent': _get_subtitle_mask_value("landscape", "height_percent"),
        'subtitle_mask_landscape_blur_radius': _get_subtitle_mask_value("landscape", "blur_radius"),
        'subtitle_mask_landscape_opacity_percent': _get_subtitle_mask_value("landscape", "opacity_percent"),
        'subtitle_mask_portrait_x_percent': _get_subtitle_mask_value("portrait", "x_percent"),
        'subtitle_mask_portrait_y_percent': _get_subtitle_mask_value("portrait", "y_percent"),
        'subtitle_mask_portrait_width_percent': _get_subtitle_mask_value("portrait", "width_percent"),
        'subtitle_mask_portrait_height_percent': _get_subtitle_mask_value("portrait", "height_percent"),
        'subtitle_mask_portrait_blur_radius': _get_subtitle_mask_value("portrait", "blur_radius"),
        'subtitle_mask_portrait_opacity_percent': _get_subtitle_mask_value("portrait", "opacity_percent"),
        'subtitle_position_landscape_y_percent': _get_orientation_subtitle_position_value("landscape", "y_percent"),
        'subtitle_position_portrait_y_percent': _get_orientation_subtitle_position_value("portrait", "y_percent"),
        'subtitle_auto_transcribe_enabled': st.session_state.get('subtitle_auto_transcribe_enabled', False),
        'subtitle_auto_transcribe_backend': st.session_state.get(
            'subtitle_auto_transcribe_backend',
            _get_saved_auto_transcribe_backend()
        ),
        'subtitle_auto_transcribe_api_url': st.session_state.get(
            'subtitle_auto_transcribe_api_url',
            config.fun_asr.get("api_url", "")
        ),
        'subtitle_auto_transcribe_firered_api_url': st.session_state.get(
            'subtitle_auto_transcribe_firered_api_url',
            config.fun_asr.get("firered_api_url", "")
        ),
        'subtitle_auto_transcribe_api_key': st.session_state.get(
            'subtitle_auto_transcribe_api_key',
            config.fun_asr.get("api_key", "")
        ),
        'subtitle_auto_transcribe_hotword': st.session_state.get(
            'subtitle_auto_transcribe_hotword',
            config.fun_asr.get("hotword", "")
        ),
        'subtitle_auto_transcribe_enable_spk': st.session_state.get(
            'subtitle_auto_transcribe_enable_spk',
            bool(config.fun_asr.get("enable_spk", False))
        ),
        'font_name': font_name,
        'font_size': st.session_state.get('font_size', 60),
        'text_fore_color': st.session_state.get('text_fore_color', '#FFFFFF'),
        'subtitle_position': st.session_state.get('subtitle_position', 'bottom'),
        'custom_position': st.session_state.get('custom_position', 70.0),
        'stroke_color': st.session_state.get('stroke_color', '#000000'),
        'stroke_width': st.session_state.get('stroke_width', 1.5),
    }

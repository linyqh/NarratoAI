import streamlit as st
from app.config import config
from webui.utils.cache import get_fonts_cache
import os


def render_subtitle_panel(tr):
    """渲染字幕设置面板"""
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))

        # 启用字幕选项
        enable_subtitles = st.checkbox(tr("Enable Subtitles"), value=True)
        st.session_state['subtitle_enabled'] = enable_subtitles

        if enable_subtitles:
            render_font_settings(tr)
            render_position_settings(tr)
            render_style_settings(tr)


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
        font_size = st.slider(
            tr("Font Size"),
            min_value=20,
            max_value=100,
            value=saved_font_size
        )
        config.ui["font_size"] = font_size
        st.session_state['font_size'] = font_size


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


def get_subtitle_params():
    """获取字幕参数"""
    return {
        'subtitle_enabled': st.session_state.get('subtitle_enabled', True),
        'font_name': st.session_state.get('font_name', ''),
        'font_size': st.session_state.get('font_size', 60),
        'text_fore_color': st.session_state.get('text_fore_color', '#FFFFFF'),
        'position': st.session_state.get('subtitle_position', 'bottom'),
        'custom_position': st.session_state.get('custom_position', 70.0),
        'stroke_color': st.session_state.get('stroke_color', '#000000'),
        'stroke_width': st.session_state.get('stroke_width', 1.5),
    }

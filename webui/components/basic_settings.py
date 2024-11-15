import streamlit as st
import os
from app.config import config
from app.utils import utils


def render_basic_settings(tr):
    """渲染基础设置面板"""
    with st.expander(tr("Basic Settings"), expanded=False):
        config_panels = st.columns(3)
        left_config_panel = config_panels[0]
        middle_config_panel = config_panels[1]
        right_config_panel = config_panels[2]

        with left_config_panel:
            render_language_settings(tr)
            render_proxy_settings(tr)

        with middle_config_panel:
            render_vision_llm_settings(tr)  # 视频分析模型设置

        with right_config_panel:
            render_text_llm_settings(tr)  # 文案生成模型设置


def render_language_settings(tr):
    st.subheader(tr("Proxy Settings"))

    """渲染语言设置"""
    system_locale = utils.get_system_locale()
    i18n_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "i18n")
    locales = utils.load_locales(i18n_dir)

    display_languages = []
    selected_index = 0
    for i, code in enumerate(locales.keys()):
        display_languages.append(f"{code} - {locales[code].get('Language')}")
        if code == st.session_state.get('ui_language', system_locale):
            selected_index = i

    selected_language = st.selectbox(
        tr("Language"),
        options=display_languages,
        index=selected_index
    )

    if selected_language:
        code = selected_language.split(" - ")[0].strip()
        st.session_state['ui_language'] = code
        config.ui['language'] = code


def render_proxy_settings(tr):
    """渲染代理设置"""
    proxy_url_http = config.proxy.get("http", "") or os.getenv("VPN_PROXY_URL", "")
    proxy_url_https = config.proxy.get("https", "") or os.getenv("VPN_PROXY_URL", "")

    HTTP_PROXY = st.text_input(tr("HTTP_PROXY"), value=proxy_url_http)
    HTTPS_PROXY = st.text_input(tr("HTTPs_PROXY"), value=proxy_url_https)

    if HTTP_PROXY:
        config.proxy["http"] = HTTP_PROXY
        os.environ["HTTP_PROXY"] = HTTP_PROXY
    if HTTPS_PROXY:
        config.proxy["https"] = HTTPS_PROXY
        os.environ["HTTPS_PROXY"] = HTTPS_PROXY


def render_vision_llm_settings(tr):
    """渲染视频分析模型设置"""
    st.subheader(tr("Vision Model Settings"))

    # 视频分析模型提供商选择
    vision_providers = ['Gemini', 'NarratoAPI']
    saved_vision_provider = config.app.get("vision_llm_provider", "Gemini").lower()
    saved_provider_index = 0

    for i, provider in enumerate(vision_providers):
        if provider.lower() == saved_vision_provider:
            saved_provider_index = i
            break

    vision_provider = st.selectbox(
        tr("Vision Model Provider"),
        options=vision_providers,
        index=saved_provider_index
    )
    vision_provider = vision_provider.lower()
    config.app["vision_llm_provider"] = vision_provider
    st.session_state['vision_llm_providers'] = vision_provider

    # 获取已保存的视觉模型配置
    vision_api_key = config.app.get(f"vision_{vision_provider}_api_key", "")
    vision_base_url = config.app.get(f"vision_{vision_provider}_base_url", "")
    vision_model_name = config.app.get(f"vision_{vision_provider}_model_name", "")

    # 渲染视觉模型配置输入框
    st_vision_api_key = st.text_input(tr("Vision API Key"), value=vision_api_key, type="password")
    st_vision_base_url = st.text_input(tr("Vision Base URL"), value=vision_base_url)
    st_vision_model_name = st.text_input(tr("Vision Model Name"), value=vision_model_name)

    # 保存视觉模型配置
    if st_vision_api_key:
        config.app[f"vision_{vision_provider}_api_key"] = st_vision_api_key
        st.session_state[f"vision_{vision_provider}_api_key"] = st_vision_api_key  # 用于script_settings.py
    if st_vision_base_url:
        config.app[f"vision_{vision_provider}_base_url"] = st_vision_base_url
        st.session_state[f"vision_{vision_provider}_base_url"] = st_vision_base_url
    if st_vision_model_name:
        config.app[f"vision_{vision_provider}_model_name"] = st_vision_model_name
        st.session_state[f"vision_{vision_provider}_model_name"] = st_vision_model_name

    # NarratoAPI 特殊配置
    if vision_provider == 'narratoapi':
        st.subheader(tr("Narrato Additional Settings"))

        # Narrato API 基础配置
        narrato_api_key = st.text_input(
            tr("Narrato API Key"),
            value=config.app.get("narrato_api_key", ""),
            type="password",
            help="用于访问 Narrato API 的密钥"
        )
        if narrato_api_key:
            config.app["narrato_api_key"] = narrato_api_key
            st.session_state['narrato_api_key'] = narrato_api_key

        narrato_api_url = st.text_input(
            tr("Narrato API URL"),
            value=config.app.get("narrato_api_url", "http://127.0.0.1:8000/api/v1/video/analyze")
        )
        if narrato_api_url:
            config.app["narrato_api_url"] = narrato_api_url
            st.session_state['narrato_api_url'] = narrato_api_url

        # 视频分析模型配置
        st.markdown("##### " + tr("Vision Model Settings"))
        narrato_vision_model = st.text_input(
            tr("Vision Model Name"),
            value=config.app.get("narrato_vision_model", "gemini-1.5-flash")
        )
        narrato_vision_key = st.text_input(
            tr("Vision Model API Key"),
            value=config.app.get("narrato_vision_key", ""),
            type="password",
            help="用于视频分析的模型 API Key"
        )

        if narrato_vision_model:
            config.app["narrato_vision_model"] = narrato_vision_model
            st.session_state['narrato_vision_model'] = narrato_vision_model
        if narrato_vision_key:
            config.app["narrato_vision_key"] = narrato_vision_key
            st.session_state['narrato_vision_key'] = narrato_vision_key

        # 文案生成模型配置
        st.markdown("##### " + tr("Text Generation Model Settings"))
        narrato_llm_model = st.text_input(
            tr("LLM Model Name"),
            value=config.app.get("narrato_llm_model", "qwen-plus")
        )
        narrato_llm_key = st.text_input(
            tr("LLM Model API Key"),
            value=config.app.get("narrato_llm_key", ""),
            type="password",
            help="用于文案生成的模型 API Key"
        )

        if narrato_llm_model:
            config.app["narrato_llm_model"] = narrato_llm_model
            st.session_state['narrato_llm_model'] = narrato_llm_model
        if narrato_llm_key:
            config.app["narrato_llm_key"] = narrato_llm_key
            st.session_state['narrato_llm_key'] = narrato_llm_key

        # 批处理配置
        narrato_batch_size = st.number_input(
            tr("Batch Size"),
            min_value=1,
            max_value=50,
            value=config.app.get("narrato_batch_size", 10),
            help="每批处理的图片数量"
        )
        if narrato_batch_size:
            config.app["narrato_batch_size"] = narrato_batch_size
            st.session_state['narrato_batch_size'] = narrato_batch_size


def render_text_llm_settings(tr):
    """渲染文案生成模型设置"""
    st.subheader(tr("Text Generation Model Settings"))

    # 文案生成模型提供商选择
    text_providers = ['OpenAI', 'Qwen', 'Moonshot', 'DeepSeek', 'Gemini']
    saved_text_provider = config.app.get("text_llm_provider", "OpenAI").lower()
    saved_provider_index = 0

    for i, provider in enumerate(text_providers):
        if provider.lower() == saved_text_provider:
            saved_provider_index = i
            break

    text_provider = st.selectbox(
        tr("Text Model Provider"),
        options=text_providers,
        index=saved_provider_index
    )
    text_provider = text_provider.lower()
    config.app["text_llm_provider"] = text_provider

    # 获取已保存的文本模型配置
    text_api_key = config.app.get(f"text_{text_provider}_api_key", "")
    text_base_url = config.app.get(f"text_{text_provider}_base_url", "")
    text_model_name = config.app.get(f"text_{text_provider}_model_name", "")

    # 渲染文本模型配置输入框
    st_text_api_key = st.text_input(tr("Text API Key"), value=text_api_key, type="password")
    st_text_base_url = st.text_input(tr("Text Base URL"), value=text_base_url)
    st_text_model_name = st.text_input(tr("Text Model Name"), value=text_model_name)

    # 保存文本模型配置
    if st_text_api_key:
        config.app[f"text_{text_provider}_api_key"] = st_text_api_key
    if st_text_base_url:
        config.app[f"text_{text_provider}_base_url"] = st_text_base_url
    if st_text_model_name:
        config.app[f"text_{text_provider}_model_name"] = st_text_model_name

    # Cloudflare 特殊配置
    if text_provider == 'cloudflare':
        st_account_id = st.text_input(
            tr("Account ID"),
            value=config.app.get(f"text_{text_provider}_account_id", "")
        )
        if st_account_id:
            config.app[f"text_{text_provider}_account_id"] = st_account_id

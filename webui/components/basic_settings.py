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
            render_video_llm_settings(tr)
            
        with right_config_panel:
            render_llm_settings(tr)

def render_language_settings(tr):
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

def render_video_llm_settings(tr):
    """渲染视频LLM设置"""
    video_llm_providers = ['Gemini', 'NarratoAPI']
    saved_llm_provider = config.app.get("video_llm_provider", "OpenAI").lower()
    saved_llm_provider_index = 0
    
    for i, provider in enumerate(video_llm_providers):
        if provider.lower() == saved_llm_provider:
            saved_llm_provider_index = i
            break

    video_llm_provider = st.selectbox(
        tr("Video LLM Provider"), 
        options=video_llm_providers, 
        index=saved_llm_provider_index
    )
    video_llm_provider = video_llm_provider.lower()
    config.app["video_llm_provider"] = video_llm_provider

    # 获取已保存的配置
    video_llm_api_key = config.app.get(f"{video_llm_provider}_api_key", "")
    video_llm_base_url = config.app.get(f"{video_llm_provider}_base_url", "")
    video_llm_model_name = config.app.get(f"{video_llm_provider}_model_name", "")
    
    # 渲染输入框
    st_llm_api_key = st.text_input(tr("Video API Key"), value=video_llm_api_key, type="password")
    st_llm_base_url = st.text_input(tr("Video Base Url"), value=video_llm_base_url)
    st_llm_model_name = st.text_input(tr("Video Model Name"), value=video_llm_model_name)
    
    # 保存配置
    if st_llm_api_key:
        config.app[f"{video_llm_provider}_api_key"] = st_llm_api_key
    if st_llm_base_url:
        config.app[f"{video_llm_provider}_base_url"] = st_llm_base_url
    if st_llm_model_name:
        config.app[f"{video_llm_provider}_model_name"] = st_llm_model_name

def render_llm_settings(tr):
    """渲染LLM设置"""
    llm_providers = ['Gemini', 'OpenAI', 'Moonshot', 'Azure', 'Qwen', 'Ollama', 'G4f', 'OneAPI', "Cloudflare"]
    saved_llm_provider = config.app.get("llm_provider", "OpenAI").lower()
    saved_llm_provider_index = 0
    
    for i, provider in enumerate(llm_providers):
        if provider.lower() == saved_llm_provider:
            saved_llm_provider_index = i
            break

    llm_provider = st.selectbox(
        tr("LLM Provider"), 
        options=llm_providers, 
        index=saved_llm_provider_index
    )
    llm_provider = llm_provider.lower()
    config.app["llm_provider"] = llm_provider

    # 获取已保存的配置
    llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
    llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
    llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
    llm_account_id = config.app.get(f"{llm_provider}_account_id", "")
    
    # 渲染输入框
    st_llm_api_key = st.text_input(tr("API Key"), value=llm_api_key, type="password")
    st_llm_base_url = st.text_input(tr("Base Url"), value=llm_base_url)
    st_llm_model_name = st.text_input(tr("Model Name"), value=llm_model_name)
    
    # 保存配置
    if st_llm_api_key:
        config.app[f"{llm_provider}_api_key"] = st_llm_api_key
    if st_llm_base_url:
        config.app[f"{llm_provider}_base_url"] = st_llm_base_url
    if st_llm_model_name:
        config.app[f"{llm_provider}_model_name"] = st_llm_model_name

    # Cloudflare 特殊处理
    if llm_provider == 'cloudflare':
        st_llm_account_id = st.text_input(tr("Account ID"), value=llm_account_id)
        if st_llm_account_id:
            config.app[f"{llm_provider}_account_id"] = st_llm_account_id 
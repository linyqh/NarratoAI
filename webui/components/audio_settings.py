import streamlit as st
import os
from uuid import uuid4
from app.config import config
from app.services import voice
from app.utils import utils
from webui.utils.cache import get_songs_cache

def render_audio_panel(tr):
    """渲染音频设置面板"""
    with st.container(border=True):
        st.write(tr("Audio Settings"))
        
        # 渲染TTS设置
        render_tts_settings(tr)
        
        # 渲染背景音乐设置
        render_bgm_settings(tr)

def render_tts_settings(tr):
    """渲染TTS(文本转语音)设置"""
    # 获取支持的语音列表
    support_locales = ["zh-CN"]
    voices = voice.get_all_azure_voices(filter_locals=support_locales)
    
    # 创建友好的显示名称
    friendly_names = {
        v: v.replace("Female", tr("Female"))
        .replace("Male", tr("Male"))
        .replace("Neural", "")
        for v in voices
    }
    
    # 获取保存的语音设置
    saved_voice_name = config.ui.get("voice_name", "")
    saved_voice_name_index = 0
    
    if saved_voice_name in friendly_names:
        saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
    else:
        # 如果没有保存的设置，选择与UI语言匹配的第一个语音
        for i, v in enumerate(voices):
            if (v.lower().startswith(st.session_state["ui_language"].lower())
                    and "V2" not in v):
                saved_voice_name_index = i
                break

    # 语音选择下拉框
    selected_friendly_name = st.selectbox(
        tr("Speech Synthesis"),
        options=list(friendly_names.values()),
        index=saved_voice_name_index,
    )

    # 获取实际的语音名称
    voice_name = list(friendly_names.keys())[
        list(friendly_names.values()).index(selected_friendly_name)
    ]
    
    # 保存设置
    config.ui["voice_name"] = voice_name

    # Azure V2语音特殊处理
    if voice.is_azure_v2_voice(voice_name):
        render_azure_v2_settings(tr)

    # 语音参数设置
    render_voice_parameters(tr)

    # 试听按钮
    render_voice_preview(tr, voice_name)

def render_azure_v2_settings(tr):
    """渲染Azure V2语音设置"""
    saved_azure_speech_region = config.azure.get("speech_region", "")
    saved_azure_speech_key = config.azure.get("speech_key", "")
    
    azure_speech_region = st.text_input(
        tr("Speech Region"), 
        value=saved_azure_speech_region
    )
    azure_speech_key = st.text_input(
        tr("Speech Key"), 
        value=saved_azure_speech_key, 
        type="password"
    )
    
    config.azure["speech_region"] = azure_speech_region
    config.azure["speech_key"] = azure_speech_key

def render_voice_parameters(tr):
    """渲染语音参数设置"""
    # 音量
    voice_volume = st.selectbox(
        tr("Speech Volume"),
        options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
        index=2,
    )
    st.session_state['voice_volume'] = voice_volume

    # 语速
    voice_rate = st.selectbox(
        tr("Speech Rate"),
        options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
        index=2,
    )
    st.session_state['voice_rate'] = voice_rate

    # 音调
    voice_pitch = st.selectbox(
        tr("Speech Pitch"),
        options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
        index=2,
    )
    st.session_state['voice_pitch'] = voice_pitch

def render_voice_preview(tr, voice_name):
    """渲染语音试听功能"""
    if st.button(tr("Play Voice")):
        play_content = "感谢关注 NarratoAI，有任何问题或建议，可以关注微信公众号，求助或讨论"
        if not play_content:
            play_content = st.session_state.get('video_script', '')
        if not play_content:
            play_content = tr("Voice Example")
            
        with st.spinner(tr("Synthesizing Voice")):
            temp_dir = utils.storage_dir("temp", create=True)
            audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")
            
            sub_maker = voice.tts(
                text=play_content,
                voice_name=voice_name,
                voice_rate=st.session_state.get('voice_rate', 1.0),
                voice_pitch=st.session_state.get('voice_pitch', 1.0),
                voice_file=audio_file,
            )
            
            # 如果语音文件生成失败，使用默认内容重试
            if not sub_maker:
                play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=st.session_state.get('voice_rate', 1.0),
                    voice_pitch=st.session_state.get('voice_pitch', 1.0),
                    voice_file=audio_file,
                )

            if sub_maker and os.path.exists(audio_file):
                st.audio(audio_file, format="audio/mp3")
                if os.path.exists(audio_file):
                    os.remove(audio_file)

def render_bgm_settings(tr):
    """渲染背景音乐设置"""
    # 背景音乐选项
    bgm_options = [
        (tr("No Background Music"), ""),
        (tr("Random Background Music"), "random"),
        (tr("Custom Background Music"), "custom"),
    ]
    
    selected_index = st.selectbox(
        tr("Background Music"),
        index=1,
        options=range(len(bgm_options)),
        format_func=lambda x: bgm_options[x][0],
    )
    
    # 获取选择的背景音乐类型
    bgm_type = bgm_options[selected_index][1]
    st.session_state['bgm_type'] = bgm_type

    # 自定义背景音乐处理
    if bgm_type == "custom":
        custom_bgm_file = st.text_input(tr("Custom Background Music File"))
        if custom_bgm_file and os.path.exists(custom_bgm_file):
            st.session_state['bgm_file'] = custom_bgm_file
    
    # 背景音乐音量
    bgm_volume = st.selectbox(
        tr("Background Music Volume"),
        options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        index=2,
    )
    st.session_state['bgm_volume'] = bgm_volume

def get_audio_params():
    """获取音频参数"""
    return {
        'voice_name': config.ui.get("voice_name", ""),
        'voice_volume': st.session_state.get('voice_volume', 1.0),
        'voice_rate': st.session_state.get('voice_rate', 1.0),
        'voice_pitch': st.session_state.get('voice_pitch', 1.0),
        'bgm_type': st.session_state.get('bgm_type', 'random'),
        'bgm_file': st.session_state.get('bgm_file', ''),
        'bgm_volume': st.session_state.get('bgm_volume', 0.2),
    }
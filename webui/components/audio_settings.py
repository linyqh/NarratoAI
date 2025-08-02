import streamlit as st
import os
from uuid import uuid4
from app.config import config
from app.services import voice
from app.models.schema import AudioVolumeDefaults
from app.utils import utils
from webui.utils.cache import get_songs_cache


def get_soulvoice_voices():
    """获取 SoulVoice 语音列表"""
    # 检查是否配置了 SoulVoice API key
    api_key = config.soulvoice.get("api_key", "")
    if not api_key:
        return []

    # 只返回一个 SoulVoice 选项，音色通过输入框自定义
    return ["soulvoice:custom"]


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
    support_locales = ["zh-CN", "en-US"]
    azure_voices = voice.get_all_azure_voices(filter_locals=support_locales)

    # 添加 SoulVoice 语音选项
    soulvoice_voices = get_soulvoice_voices()

    # 合并所有语音选项
    all_voices = azure_voices + soulvoice_voices

    # 创建友好的显示名称
    friendly_names = {}

    # Azure 语音的友好名称
    for v in azure_voices:
        friendly_names[v] = v.replace("Female", tr("Female")).replace("Male", tr("Male")).replace("Neural", "")

    # SoulVoice 语音的友好名称
    for v in soulvoice_voices:
        friendly_names[v] = "SoulVoice (自定义音色)"

    # 获取保存的语音设置
    saved_voice_name = config.ui.get("voice_name", "")
    saved_voice_name_index = 0

    if saved_voice_name in friendly_names:
        saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
    else:
        # 如果没有保存的设置，选择与UI语言匹配的第一个语音
        for i, v in enumerate(all_voices):
            if (v.lower().startswith(st.session_state["ui_language"].lower())
                    and "V2" not in v and not v.startswith("soulvoice:")):
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

    # 如果选择的是 SoulVoice 自定义选项，使用配置的音色 URI
    if voice_name == "soulvoice:custom":
        custom_voice_uri = config.soulvoice.get("voice_uri", "")
        if custom_voice_uri:
            # 确保音色 URI 有正确的前缀
            if not custom_voice_uri.startswith("soulvoice:") and not custom_voice_uri.startswith("speech:"):
                voice_name = f"soulvoice:{custom_voice_uri}"
            else:
                voice_name = custom_voice_uri if custom_voice_uri.startswith("soulvoice:") else f"soulvoice:{custom_voice_uri}"

    # 保存设置
    config.ui["voice_name"] = voice_name

    # 根据语音类型渲染不同的设置
    if voice.is_soulvoice_voice(voice_name):
        render_soulvoice_settings(tr)
    elif voice.is_azure_v2_voice(voice_name):
        render_azure_v2_settings(tr)

    # 语音参数设置
    render_voice_parameters(tr, voice_name)

    # 试听按钮
    render_voice_preview(tr, voice_name)


def render_soulvoice_settings(tr):
    """渲染 SoulVoice 语音设置"""
    saved_api_key = config.soulvoice.get("api_key", "")
    saved_api_url = config.soulvoice.get("api_url", "https://tts.scsmtech.cn/tts")
    saved_model = config.soulvoice.get("model", "FunAudioLLM/CosyVoice2-0.5B")
    saved_voice_uri = config.soulvoice.get("voice_uri", "speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr")

    # API Key 输入
    api_key = st.text_input(
        "SoulVoice API Key",
        value=saved_api_key,
        type="password",
        help="请输入您的 SoulVoice API 密钥"
    )

    # 音色 URI 输入
    voice_uri = st.text_input(
        "音色 URI",
        value=saved_voice_uri,
        help="请输入 SoulVoice 音色标识符，格式如：speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr",
        placeholder="speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr"
    )

    # API URL 输入（可选）
    with st.expander("高级设置", expanded=False):
        api_url = st.text_input(
            "API 地址",
            value=saved_api_url,
            help="SoulVoice API 接口地址"
        )

        model = st.text_input(
            "模型名称",
            value=saved_model,
            help="使用的 TTS 模型"
        )

    # 保存配置
    config.soulvoice["api_key"] = api_key
    config.soulvoice["voice_uri"] = voice_uri
    config.soulvoice["api_url"] = api_url
    config.soulvoice["model"] = model

    # 显示配置状态
    if api_key and voice_uri:
        st.success("✅ SoulVoice 配置已设置")
    elif not api_key:
        st.warning("⚠️ 请配置 SoulVoice API Key")
    elif not voice_uri:
        st.warning("⚠️ 请配置音色 URI")


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


def render_voice_parameters(tr, voice_name):
    """渲染语音参数设置"""
    # 音量 - 使用统一的默认值
    voice_volume = st.slider(
        tr("Speech Volume"),
        min_value=AudioVolumeDefaults.MIN_VOLUME,
        max_value=AudioVolumeDefaults.MAX_VOLUME,
        value=AudioVolumeDefaults.VOICE_VOLUME,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['voice_volume'] = voice_volume

    # 检查是否为 SoulVoice 引擎
    is_soulvoice = voice.is_soulvoice_voice(voice_name)

    # 语速
    if is_soulvoice:
        # SoulVoice 支持更精细的语速控制
        voice_rate = st.slider(
            tr("Speech Rate"),
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            help="SoulVoice 语音速度控制"
        )
    else:
        # Azure TTS 使用预设选项
        voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )
    st.session_state['voice_rate'] = voice_rate

    # 音调 - SoulVoice 不支持音调调节
    if not is_soulvoice:
        voice_pitch = st.selectbox(
            tr("Speech Pitch"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )
        st.session_state['voice_pitch'] = voice_pitch
    else:
        # SoulVoice 不支持音调调节，设置默认值
        st.session_state['voice_pitch'] = 1.0
        st.info("ℹ️ SoulVoice 引擎不支持音调调节")


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

    # 背景音乐音量 - 使用统一的默认值
    bgm_volume = st.slider(
        tr("Background Music Volume"),
        min_value=AudioVolumeDefaults.MIN_VOLUME,
        max_value=AudioVolumeDefaults.MAX_VOLUME,
        value=AudioVolumeDefaults.BGM_VOLUME,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['bgm_volume'] = bgm_volume


def get_audio_params():
    """获取音频参数"""
    return {
        'voice_name': config.ui.get("voice_name", ""),
        'voice_volume': st.session_state.get('voice_volume', AudioVolumeDefaults.VOICE_VOLUME),
        'voice_rate': st.session_state.get('voice_rate', 1.0),
        'voice_pitch': st.session_state.get('voice_pitch', 1.0),
        'bgm_type': st.session_state.get('bgm_type', 'random'),
        'bgm_file': st.session_state.get('bgm_file', ''),
        'bgm_volume': st.session_state.get('bgm_volume', AudioVolumeDefaults.BGM_VOLUME),
    }

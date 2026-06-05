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


def get_tts_engine_options(tr=lambda key: key):
    """获取TTS引擎选项"""
    return {
        "edge_tts": "Edge TTS",
        "azure_speech": "Azure Speech Services",
        "tencent_tts": tr("Tencent Cloud TTS"),
        "qwen3_tts": tr("Tongyi Qwen3 TTS"),
        "indextts2": tr("IndexTTS2 Voice Clone"),
        "doubaotts": tr("Doubao TTS")
    }


def get_tts_engine_descriptions(tr=lambda key: key):
    """获取TTS引擎详细描述"""
    return {
        "edge_tts": {
            "title": "Edge TTS",
            "features": tr("Edge TTS features"),
            "use_case": tr("Edge TTS use case"),
            "registration": None
        },
        "azure_speech": {
            "title": "Azure Speech Services",
            "features": tr("Azure Speech Services features"),
            "use_case": tr("Azure Speech Services use case"),
            "registration": "https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/SpeechServices"
        },
        "tencent_tts": {
            "title": tr("Tencent Cloud TTS"),
            "features": tr("Tencent Cloud TTS features"),
            "use_case": tr("Tencent Cloud TTS use case"),
            "registration": "https://console.cloud.tencent.com/tts"
        },
        "qwen3_tts": {
            "title": tr("Tongyi Qwen3 TTS"),
            "features": tr("Tongyi Qwen3 TTS features"),
            "use_case": tr("High-quality Chinese speech synthesis use case"),
            "registration": "https://dashscope.aliyuncs.com/"
        },
        "indextts2": {
            "title": tr("IndexTTS2 Voice Clone"),
            "features": tr("IndexTTS2 features"),
            "use_case": tr("IndexTTS2 download link"),
            "registration": None
        },
        "doubaotts": {
            "title": tr("Doubao TTS"),
            "features": tr("Doubao TTS features"),
            "use_case": tr("High-quality Chinese speech synthesis use case"),
            "registration": "https://www.volcengine.com/product/voice-tech"
        }
    }


def is_valid_azure_voice_name(voice_name: str) -> bool:
    """检查是否为有效的Azure音色名称格式"""
    if not voice_name or not isinstance(voice_name, str):
        return False

    voice_name = voice_name.strip()

    # Azure音色名称通常格式为: [语言]-[地区]-[名称]Neural
    # 例如: zh-CN-YunzeNeural, en-US-AvaMultilingualNeural
    import re
    pattern = r'^[a-z]{2}-[A-Z]{2}-\w+Neural$'
    return bool(re.match(pattern, voice_name))


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

    # 1. TTS引擎选择器
    # st.subheader("🎤 TTS引擎选择")

    engine_options = get_tts_engine_options(tr)
    engine_descriptions = get_tts_engine_descriptions(tr)

    # 获取保存的TTS引擎设置
    saved_tts_engine = config.ui.get("tts_engine", "edge_tts")

    # 确保保存的引擎在可用选项中
    if saved_tts_engine not in engine_options:
        saved_tts_engine = "edge_tts"

    # TTS引擎选择下拉框
    selected_engine = st.selectbox(
        tr("Select TTS Engine"),
        options=list(engine_options.keys()),
        format_func=lambda x: engine_options[x],
        index=list(engine_options.keys()).index(saved_tts_engine),
        help=tr("Select TTS Engine Help")
    )

    # 保存TTS引擎选择
    config.ui["tts_engine"] = selected_engine
    st.session_state['tts_engine'] = selected_engine

    # 2. 显示引擎详细说明
    if selected_engine in engine_descriptions:
        desc = engine_descriptions[selected_engine]

        with st.expander(tr("TTS Engine Details").format(engine=desc['title']), expanded=True):
            st.markdown(f"**{tr('Features')}:** {desc['features']}")
            st.markdown(f"**{tr('Use Case')}:** {desc['use_case']}")

            if desc['registration']:
                st.markdown(f"**{tr('Registration URL')}:** [{desc['registration']}]({desc['registration']})")

    # 3. 根据选择的引擎渲染对应的配置界面
    # st.subheader("⚙️ 引擎配置")

    if selected_engine == "edge_tts":
        render_edge_tts_settings(tr)
    elif selected_engine == "azure_speech":
        render_azure_speech_settings(tr)
    elif selected_engine == "soulvoice":
        render_soulvoice_engine_settings(tr)
    elif selected_engine == "tencent_tts":
        render_tencent_tts_settings(tr)
    elif selected_engine == "qwen3_tts":
        render_qwen3_tts_settings(tr)
    elif selected_engine == "indextts2":
        render_indextts2_tts_settings(tr)
    elif selected_engine == "doubaotts":
        render_doubaotts_settings(tr)

    # 4. 试听功能
    render_voice_preview_new(tr, selected_engine)


def render_edge_tts_settings(tr):
    """渲染 Edge TTS 引擎设置"""
    # 获取 Edge TTS 支持的全部语言和音色
    edge_voices = voice.get_all_edge_voices()

    # 创建友好的显示名称
    friendly_names = {}
    for v in edge_voices:
        friendly_names[v] = v.replace("Female", tr("Female")).replace("Male", tr("Male")).replace("Neural", "")

    # 获取保存的语音设置
    saved_voice_name = config.ui.get("edge_voice_name", "zh-CN-XiaoxiaoNeural-Female")

    # 确保保存的音色在可用列表中
    if saved_voice_name not in friendly_names:
        # 选择与UI语言匹配的第一个语音
        for v in edge_voices:
            if v.lower().startswith(st.session_state.get("ui_language", "zh-CN").lower()):
                saved_voice_name = v
                break
        else:
            # 如果没找到匹配的，使用第一个
            saved_voice_name = edge_voices[0] if edge_voices else ""

    # 音色选择下拉框
    selected_friendly_name = st.selectbox(
        tr("Voice Selection"),
        options=list(friendly_names.values()),
        index=list(friendly_names.keys()).index(saved_voice_name) if saved_voice_name in friendly_names else 0,
        help=tr("Select Edge TTS Voice")
    )

    # 获取实际的语音名称
    voice_name = list(friendly_names.keys())[
        list(friendly_names.values()).index(selected_friendly_name)
    ]

    # 显示音色信息
    with st.expander(tr("Edge TTS Voice Description"), expanded=False):
        st.write(tr("Loaded voice count").format(count=len(edge_voices)))
        for v in edge_voices:
            gender = tr("Female Voice") if "Female" in v else tr("Male Voice")
            name = v.replace("-Female", "").replace("-Male", "").replace("Neural", "")
            st.write(f"• {name} ({gender})")

    config.ui["edge_voice_name"] = voice_name
    config.ui["voice_name"] = voice_name  # 兼容性

    # 音量调节
    voice_volume = st.slider(
        tr("Voice Volume"),
        min_value=0,
        max_value=100,
        value=int(config.ui.get("edge_volume", 80)),
        step=1,
        help=tr("Voice Volume Help Percent")
    )
    config.ui["edge_volume"] = voice_volume
    st.session_state['voice_volume'] = voice_volume / 100.0

    # 语速调节
    voice_rate = st.slider(
        tr("Voice Rate"),
        min_value=0.5,
        max_value=2.0,
        value=config.ui.get("edge_rate", 1.0),
        step=0.1,
        help=tr("Voice Rate Help 0.5-2.0")
    )
    config.ui["edge_rate"] = voice_rate
    st.session_state['voice_rate'] = voice_rate

    # 语调调节
    voice_pitch = st.slider(
        tr("Voice Pitch"),
        min_value=-50,
        max_value=50,
        value=int(config.ui.get("edge_pitch", 0)),
        step=5,
        help=tr("Voice Pitch Help Percent")
    )
    config.ui["edge_pitch"] = voice_pitch
    # 转换为比例值
    st.session_state['voice_pitch'] = 1.0 + (voice_pitch / 100.0)


def render_azure_speech_settings(tr):
    """渲染 Azure Speech Services 引擎设置"""
    # 服务区域配置
    azure_speech_region = st.text_input(
        tr("Service Region"),
        value=config.azure.get("speech_region", ""),
        placeholder=tr("Service Region Placeholder"),
        help=tr("Azure Service Region Help")
    )

    # API Key配置
    azure_speech_key = st.text_input(
        "API Key",
        value=config.azure.get("speech_key", ""),
        type="password",
        help=tr("Azure Speech Key Help")
    )

    # 保存Azure配置
    config.azure["speech_region"] = azure_speech_region
    config.azure["speech_key"] = azure_speech_key

    # 音色名称输入框
    saved_voice_name = config.ui.get("azure_voice_name", "zh-CN-XiaoxiaoMultilingualNeural")

    # 音色名称输入
    voice_name = st.text_input(
        tr("Voice Name"),
        value=saved_voice_name,
        help=tr("Azure Voice Name Help"),
        placeholder="zh-CN-YunzeNeural"
    )

    # 显示常用音色示例
    with st.expander(tr("Common Voice Reference"), expanded=False):
        st.write(f"**{tr('Chinese Voices')}:**")
        st.write(f"• zh-CN-XiaoxiaoMultilingualNeural ({tr('Female Voice')}, {tr('Multilingual')})")
        st.write(f"• zh-CN-YunzeNeural ({tr('Male Voice')})")
        st.write(f"• zh-CN-YunxiNeural ({tr('Male Voice')})")
        st.write(f"• zh-CN-XiaochenNeural ({tr('Female Voice')})")
        st.write("")
        st.write(f"**{tr('English Voices')}:**")
        st.write(f"• en-US-AndrewMultilingualNeural ({tr('Male Voice')}, {tr('Multilingual')})")
        st.write(f"• en-US-AvaMultilingualNeural ({tr('Female Voice')}, {tr('Multilingual')})")
        st.write(f"• en-US-BrianMultilingualNeural ({tr('Male Voice')}, {tr('Multilingual')})")
        st.write(f"• en-US-EmmaMultilingualNeural ({tr('Female Voice')}, {tr('Multilingual')})")
        st.write("")
        st.info(tr("Azure Voices Docs Notice"))

    # 快速选择按钮
    st.write(f"**{tr('Quick Select')}:**")
    cols = st.columns(3)
    with cols[0]:
        if st.button(tr("Chinese Female Voice"), help="zh-CN-XiaoxiaoMultilingualNeural"):
            voice_name = "zh-CN-XiaoxiaoMultilingualNeural"
            st.rerun()
    with cols[1]:
        if st.button(tr("Chinese Male Voice"), help="zh-CN-YunzeNeural"):
            voice_name = "zh-CN-YunzeNeural"
            st.rerun()
    with cols[2]:
        if st.button(tr("English Female Voice"), help="en-US-AvaMultilingualNeural"):
            voice_name = "en-US-AvaMultilingualNeural"
            st.rerun()

    # 验证音色名称并显示状态
    if voice_name.strip():
        # 检查是否为有效的Azure音色格式
        if is_valid_azure_voice_name(voice_name):
            st.success(tr("Voice name valid").format(voice=voice_name))
        else:
            st.warning(tr("Voice name format may be invalid").format(voice=voice_name))
            st.info(tr("Azure voice name format notice"))

    # 保存配置
    config.ui["azure_voice_name"] = voice_name
    config.ui["voice_name"] = voice_name  # 兼容性

    # 音量调节
    voice_volume = st.slider(
        tr("Voice Volume"),
        min_value=0,
        max_value=100,
        value=int(config.ui.get("azure_volume", 80)),
        step=1,
        help=tr("Voice Volume Help Percent")
    )
    config.ui["azure_volume"] = voice_volume
    st.session_state['voice_volume'] = voice_volume / 100.0

    # 语速调节
    voice_rate = st.slider(
        tr("Voice Rate"),
        min_value=0.5,
        max_value=2.0,
        value=config.ui.get("azure_rate", 1.0),
        step=0.1,
        help=tr("Voice Rate Help 0.5-2.0")
    )
    config.ui["azure_rate"] = voice_rate
    st.session_state['voice_rate'] = voice_rate

    # 语调调节
    voice_pitch = st.slider(
        tr("Voice Pitch"),
        min_value=-50,
        max_value=50,
        value=int(config.ui.get("azure_pitch", 0)),
        step=5,
        help=tr("Voice Pitch Help Percent")
    )
    config.ui["azure_pitch"] = voice_pitch
    # 转换为比例值
    st.session_state['voice_pitch'] = 1.0 + (voice_pitch / 100.0)

    # 显示配置状态
    if azure_speech_region and azure_speech_key:
        st.success(tr("Azure Speech Services configured"))
    elif not azure_speech_region:
        st.warning(tr("Please configure service region"))
    elif not azure_speech_key:
        st.warning(tr("Please configure API Key"))


def render_tencent_tts_settings(tr):
    """渲染腾讯云 TTS 引擎设置"""
    # Secret ID 输入
    secret_id = st.text_input(
        "Secret ID",
        value=config.tencent.get("secret_id", ""),
        help=tr("Tencent Secret ID Help")
    )

    # Secret Key 输入
    secret_key = st.text_input(
        "Secret Key",
        value=config.tencent.get("secret_key", ""),
        type="password",
        help=tr("Tencent Secret Key Help")
    )

    # 地域选择
    region_options = [
        "ap-beijing",
        "ap-shanghai",
        "ap-guangzhou",
        "ap-chengdu",
        "ap-nanjing",
        "ap-singapore",
        "ap-hongkong"
    ]
    
    saved_region = config.tencent.get("region", "ap-beijing")
    if saved_region not in region_options:
        region_options.append(saved_region)
    
    region = st.selectbox(
        tr("Service Region"),
        options=region_options,
        index=region_options.index(saved_region),
        help=tr("Tencent Service Region Help")
    )

    # 音色选择
    voice_type_options = {
        "101001": "智瑜 - 女声（推荐）",
        "101002": "智聆 - 女声",
        "101003": "智美 - 女声",
        "101004": "智云 - 男声",
        "101005": "智莉 - 女声",
        "101006": "智言 - 男声",
        "101007": "智娜 - 女声",
        "101008": "智琪 - 女声",
        "101009": "智芸 - 女声",
        "101010": "智华 - 男声",
        "101011": "智燕 - 女声",
        "101012": "智丹 - 女声",
        "101013": "智辉 - 男声",
        "101014": "智宁 - 女声",
        "101015": "智萌 - 女声",
        "101016": "智甜 - 女声",
        "101017": "智蓉 - 女声",
        "101018": "智靖 - 男声"
    }
    
    saved_voice_type = config.ui.get("tencent_voice_type", "101001")
    if saved_voice_type not in voice_type_options:
        voice_type_options[saved_voice_type] = f"{tr('Custom Voice')} ({saved_voice_type})"
    
    selected_voice_display = st.selectbox(
        tr("Voice Selection"),
        options=list(voice_type_options.values()),
        index=list(voice_type_options.keys()).index(saved_voice_type),
        help=tr("Select Tencent TTS Voice")
    )
    
    # 获取实际的音色ID
    voice_type = list(voice_type_options.keys())[
        list(voice_type_options.values()).index(selected_voice_display)
    ]
    
    # 语速调节
    voice_rate = st.slider(
        tr("Voice Rate"),
        min_value=0.5,
        max_value=2.0,
        value=config.ui.get("tencent_rate", 1.0),
        step=0.1,
        help=tr("Voice Rate Help 0.5-2.0")
    )
    
    config.ui["voice_name"] = saved_voice_type  # 兼容性
    
    # 显示音色说明
    with st.expander(tr("Tencent Cloud TTS Voice Description"), expanded=False):
        st.write(f"**{tr('Female Voices')}:**")
        female_voices = [(k, v) for k, v in voice_type_options.items() if "女声" in v]
        for voice_id, voice_desc in female_voices[:6]:  # 显示前6个
            st.write(f"• {voice_desc} (ID: {voice_id})")
        
        st.write("")
        st.write(f"**{tr('Male Voices')}:**")
        male_voices = [(k, v) for k, v in voice_type_options.items() if "男声" in v]
        for voice_id, voice_desc in male_voices:
            st.write(f"• {voice_desc} (ID: {voice_id})")
        
        st.write("")
        st.info(tr("Tencent More Voices Notice"))
    
    # 保存配置
    config.tencent["secret_id"] = secret_id
    config.tencent["secret_key"] = secret_key
    config.tencent["region"] = region
    config.ui["tencent_voice_type"] = voice_type
    config.ui["tencent_rate"] = voice_rate
    config.ui["voice_name"] = saved_voice_type #兼容性


def render_qwen3_tts_settings(tr):
    """渲染 Qwen3 TTS 设置"""
    api_key = st.text_input(
        "API Key",
        value=config.tts_qwen.get("api_key", ""),
        type="password",
        help=tr("Qwen DashScope API Key Help")
    )

    model_name = st.text_input(
        tr("TTS Model Name"),
        value=config.tts_qwen.get("model_name", "qwen3-tts-flash"),
        help=tr("Qwen TTS Model Help")
    )

    # Qwen3 TTS 音色选项 - 中文名: 英文参数
    voice_options = {
        "芊悦": "Cherry",
        "晨煦": "Ethan",
        "不吃鱼": "Nofish",
        "詹妮弗": "Jennifer",
        "甜茶": "Ryan",
        "卡捷琳娜": "Katerina",
        "墨讲师": "Elias",
        "上海-阿珍": "Jada",
        "北京-晓东": "Dylan",
        "四川-晴儿": "Sunny",
        "南京-老李": "Li",
        "陕西-秦川": "Marcus",
        "闽南-阿杰": "Roy",
        "天津-李彼得": "Peter",
        "粤语-阿强": "Rocky",
        "粤语-阿清": "Kiki",
        "四川-程川": "Eric"
    }
    
    # 显示给用户的中文名称列表
    display_names = list(voice_options.keys())
    saved_voice_param = config.ui.get("qwen_voice_type", "Cherry")
    
    # 如果保存的英文参数不在选项中，查找对应的中文名称
    saved_display_name = "芊悦"  # 默认值
    for chinese_name, english_param in voice_options.items():
        if english_param == saved_voice_param:
            saved_display_name = chinese_name
            break
    
    # 如果保存的音色不在选项中，添加到自定义选项
    if saved_display_name not in display_names:
        display_names.append(saved_display_name)
        voice_options[saved_display_name] = saved_voice_param

    selected_display_name = st.selectbox(
        tr("Voice Selection"),
        options=display_names,
        index=display_names.index(saved_display_name) if saved_display_name in display_names else 0,
        help=tr("Select Qwen3 TTS Voice")
    )
    
    # 获取对应的英文参数
    voice_type = voice_options.get(selected_display_name, "Cherry")

    voice_rate = st.slider(
        tr("Voice Rate"),
        min_value=0.5,
        max_value=2.0,
        value=1.0,
        step=0.1,
        help=tr("Voice Rate Help 0.5-2.0")
    )

    # 保存配置
    config.tts_qwen["api_key"] = api_key
    config.tts_qwen["model_name"] = model_name
    config.ui["qwen_voice_type"] = voice_type
    config.ui["qwen3_rate"] = voice_rate
    config.ui["voice_name"] = voice_type #兼容性


def render_indextts2_tts_settings(tr):
    """渲染 IndexTTS2 TTS 设置"""
    import os
    
    # API 地址配置
    api_url = st.text_input(
        tr("API URL"),
        value=config.indextts2.get("api_url", "http://127.0.0.1:8081/tts"),
        help=tr("IndexTTS2 API URL Help")
    )
    
    # 参考音频文件路径
    reference_audio = st.text_input(
        tr("Reference Audio Path"),
        value=config.indextts2.get("reference_audio", ""),
        help=tr("Reference Audio Path Help")
    )
    
    # 文件上传功能
    uploaded_file = st.file_uploader(
        tr("Upload Reference Audio File"),
        type=["wav", "mp3"],
        help=tr("Upload Reference Audio Help")
    )
    
    if uploaded_file is not None:
        # 保存上传的文件
        import tempfile
        temp_dir = tempfile.gettempdir()
        audio_path = os.path.join(temp_dir, f"indextts2_ref_{uploaded_file.name}")
        with open(audio_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        reference_audio = audio_path
        st.success(tr("Audio uploaded").format(path=audio_path))
    
    # 推理模式
    infer_mode_options = [
        ("普通推理", tr("Standard Inference")),
        ("快速推理", tr("Fast Inference")),
    ]
    infer_mode_index = 0 if config.indextts2.get("infer_mode", "普通推理") == "普通推理" else 1
    infer_mode = infer_mode_options[st.selectbox(
        tr("Inference Mode"),
        options=range(len(infer_mode_options)),
        index=infer_mode_index,
        format_func=lambda x: infer_mode_options[x][1],
        help=tr("Inference Mode Help")
    )][0]
    
    # 高级参数折叠面板
    with st.expander(tr("Advanced Parameters"), expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            temperature = st.slider(
                tr("Sampling Temperature"),
                min_value=0.1,
                max_value=2.0,
                value=float(config.indextts2.get("temperature", 1.0)),
                step=0.1,
                help=tr("Sampling Temperature Help")
            )
            
            top_p = st.slider(
                "Top P",
                min_value=0.0,
                max_value=1.0,
                value=float(config.indextts2.get("top_p", 0.8)),
                step=0.05,
                help=tr("Top P Help")
            )
            
            top_k = st.slider(
                "Top K",
                min_value=0,
                max_value=100,
                value=int(config.indextts2.get("top_k", 30)),
                step=5,
                help=tr("Top K Help")
            )
        
        with col2:
            num_beams = st.slider(
                tr("Num Beams"),
                min_value=1,
                max_value=10,
                value=int(config.indextts2.get("num_beams", 3)),
                step=1,
                help=tr("Num Beams Help")
            )
            
            repetition_penalty = st.slider(
                tr("Repetition Penalty"),
                min_value=1.0,
                max_value=20.0,
                value=float(config.indextts2.get("repetition_penalty", 10.0)),
                step=0.5,
                help=tr("Repetition Penalty Help")
            )
            
            do_sample = st.checkbox(
                tr("Enable Sampling"),
                value=config.indextts2.get("do_sample", True),
                help=tr("Enable Sampling Help")
            )
    
    # 显示使用说明
    with st.expander(tr("IndexTTS2 Usage Instructions Title"), expanded=False):
        st.markdown(tr("IndexTTS2 Usage Instructions"))
    
    # 保存配置
    config.indextts2["api_url"] = api_url
    config.indextts2["reference_audio"] = reference_audio
    config.indextts2["infer_mode"] = infer_mode
    config.indextts2["temperature"] = temperature
    config.indextts2["top_p"] = top_p
    config.indextts2["top_k"] = top_k
    config.indextts2["num_beams"] = num_beams
    config.indextts2["repetition_penalty"] = repetition_penalty
    config.indextts2["do_sample"] = do_sample
    
    # 保存 voice_name 用于兼容性
    if reference_audio:
        config.ui["voice_name"] = f"indextts2:{reference_audio}"


def render_doubaotts_settings(tr):
    """渲染豆包语音 TTS 设置"""
    # AK 输入
    ak = st.text_input(
        "Access Key",
        value=config.doubaotts.get("ak", ""),
        help=tr("Volcengine Access Key Help")
    )

    # SK 输入
    sk = st.text_input(
        "Secret Key",
        value=config.doubaotts.get("sk", ""),
        type="password",
        help=tr("Volcengine Secret Key Help")
    )

    # AppID 输入
    appid = st.text_input(
        "AppID",
        value=config.doubaotts.get("appid", ""),
        help=tr("Doubao AppID Help")
    )

    # Token 输入
    token = st.text_input(
        "Token",
        value=config.doubaotts.get("token", ""),
        type="password",
        help=tr("Doubao Token Help")
    )

    # 集群配置
    cluster = st.text_input(
        tr("Cluster"),
        value=config.doubaotts.get("cluster", "volcano_tts"),
        help=tr("Doubao Cluster Help")
    )

    # 音色选择
    # 在线音色列表（从文档中提取）
    voice_options = {
        "BV700_V2_streaming": "灿灿 2.0",
        "BV705_streaming": "炀炀",
        "BV701_V2_streaming": "擎苍 2.0",
        "BV001_V2_streaming": "通用女声 2.0",
        "BV700_streaming": "灿灿",
        "BV406_V2_streaming": "超自然音色-梓梓2.0",
        "BV406_streaming": "超自然音色-梓梓",
        "BV407_V2_streaming": "超自然音色-燃燃2.0",
        "BV407_streaming": "超自然音色-燃燃",
        "BV001_streaming": "通用女声",
        "BV002_streaming": "通用男声",
        "BV701_streaming": "擎苍",
        "BV123_streaming": "阳光青年",
        "BV120_streaming": "反卷青年",
        "BV119_streaming": "通用赘婿",
        "BV115_streaming": "古风少御",
        "BV107_streaming": "霸气青叔",
        "BV100_streaming": "质朴青年",
        "BV104_streaming": "温柔淑女",
        "BV004_streaming": "开朗青年",
        "BV113_streaming": "甜宠少御",
        "BV102_streaming": "儒雅青年",
        "BV405_streaming": "甜美小源",
        "BV007_streaming": "亲切女声",
        "BV009_streaming": "知性女声",
        "BV419_streaming": "诚诚",
        "BV415_streaming": "童童",
        "BV008_streaming": "亲切男声",
        "BV408_streaming": "译制片男声",
        "BV426_streaming": "懒小羊",
        "BV428_streaming": "清新文艺女声",
        "BV403_streaming": "鸡汤女声",
        "BV158_streaming": "智慧老者",
        "BV157_streaming": "慈爱姥姥",
        "BR001_streaming": "说唱小哥",
        "BV410_streaming": "活力解说男",
        "BV411_streaming": "影视解说小帅",
        "BV437_streaming": "解说小帅-多情感",
        "BV412_streaming": "影视解说小美",
        "BV159_streaming": "纨绔青年",
        "BV418_streaming": "直播一姐",
        "BV142_streaming": "沉稳解说男",
        "BV143_streaming": "潇洒青年",
        "BV056_streaming": "阳光男声",
        "BV005_streaming": "活泼女声",
        "BV064_streaming": "小萝莉",
        "BV051_streaming": "奶气萌娃",
        "BV063_streaming": "动漫海绵",
        "BV417_streaming": "动漫海星",
        "BV050_streaming": "动漫小新",
        "BV061_streaming": "天才童声",
        "BV401_streaming": "促销男声",
        "BV402_streaming": "促销女声",
        "BV006_streaming": "磁性男声",
        "BV011_streaming": "新闻女声",
        "BV012_streaming": "新闻男声",
        "BV034_streaming": "知性姐姐-双语",
        "BV033_streaming": "温柔小哥",
        "BV511_streaming": "慵懒女声-Ava",
        "BV505_streaming": "议论女声-Alicia",
        "BV138_streaming": "情感女声-Lawrence",
        "BV027_streaming": "美式女声-Amelia",
        "BV502_streaming": "讲述女声-Amanda",
        "BV503_streaming": "活力女声-Ariana",
        "BV504_streaming": "活力男声-Jackson",
        "BV421_streaming": "天才少女",
        "BV702_streaming": "Stefan",
        "BV506_streaming": "天真萌娃-Lily",
        "BV040_streaming": "亲切女声-Anna",
        "BV516_streaming": "澳洲男声-Henry",
        "BV520_streaming": "元气少女",
        "BV521_streaming": "萌系少女",
        "BV522_streaming": "气质女声",
        "BV524_streaming": "日语男声",
        "BV531_streaming": "活力男声Carlos（巴西地区）",
        "BV530_streaming": "活力女声（巴西地区）",
        "BV065_streaming": "气质御姐（墨西哥地区）",
        "BV021_streaming": "东北老铁",
        "BV020_streaming": "东北丫头",
        "BV704_streaming": "方言灿灿",
        "BV210_streaming": "西安佟掌柜",
        "BV217_streaming": "沪上阿姐",
        "BV213_streaming": "广西表哥",
        "BV025_streaming": "甜美台妹",
        "BV227_streaming": "台普男声",
        "BV026_streaming": "港剧男神",
        "BV424_streaming": "广东女仔",
        "BV212_streaming": "相声演员",
        "BV019_streaming": "重庆小伙",
        "BV221_streaming": "四川甜妹儿",
        "BV423_streaming": "重庆幺妹儿",
        "BV214_streaming": "乡村企业家",
        "BV226_streaming": "湖南妹坨",
        "BV216_streaming": "长沙靓女"
    }
    
    saved_voice_type = config.ui.get("doubaotts_voice_type", "BV700_streaming")
    if saved_voice_type not in voice_options:
        voice_options[saved_voice_type] = f"{tr('Custom Voice')} ({saved_voice_type})"
    
    selected_voice_display = st.selectbox(
        tr("Voice Selection"),
        options=list(voice_options.values()),
        index=list(voice_options.keys()).index(saved_voice_type) if saved_voice_type in voice_options else 0,
        help=tr("Select Doubao TTS Voice")
    )
    
    # 获取实际的音色ID
    voice_type = list(voice_options.keys())[
        list(voice_options.values()).index(selected_voice_display)
    ]
    
    # 高级参数折叠面板
    with st.expander(tr("Advanced Parameters"), expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            # 语速调节
            voice_rate = st.slider(
                tr("Voice Rate"),
                min_value=0.2,
                max_value=3.0,
                value=config.ui.get("doubaotts_rate", 1.0),
                step=0.1,
                help=tr("Voice Rate Help 0.2-3.0")
            )
            
            # 音量调节
            voice_volume = st.slider(
                tr("Voice Volume"),
                min_value=0.1,
                max_value=2.0,
                value=config.doubaotts.get("volume", 1.0),
                step=0.1,
                help=tr("Voice Volume Help 0.1-2.0")
            )
        
        with col2:
            # 音高调节
            voice_pitch = st.slider(
                tr("Voice Pitch"),
                min_value=0.5,
                max_value=1.5,
                value=config.doubaotts.get("pitch", 1.0),
                step=0.1,
                help=tr("Voice Pitch Help 0.5-1.5")
            )
            
            # 句尾静音时长
            silence_duration = st.slider(
                tr("Sentence Silence Duration"),
                min_value=0.0,
                max_value=2.0,
                value=config.doubaotts.get("silence_duration", 0.125),
                step=0.05,
                help=tr("Sentence Silence Duration Help")
            )
    
    # 显示API Key申请流程
    with st.expander(tr("Doubao TTS API Key Application Process"), expanded=False):
        st.write(f"**{tr('Application Steps')}:**")
        st.write(tr("Doubao TTS Step 1"))
        st.write(tr("Doubao TTS Step 2"))
        st.write(tr("Doubao TTS Step 3"))
        st.write(tr("Doubao TTS Step 4"))
        st.write(tr("Doubao TTS Step 5"))
        st.write(tr("Doubao TTS Step 6"))
        
        st.write("")
        st.info(tr("Doubao TTS Fill Credentials Notice"))
    
    # 保存配置
    config.doubaotts["ak"] = ak
    config.doubaotts["sk"] = sk
    config.doubaotts["appid"] = appid
    config.doubaotts["token"] = token
    config.doubaotts["cluster"] = cluster
    config.doubaotts["volume"] = voice_volume
    config.doubaotts["pitch"] = voice_pitch
    config.doubaotts["silence_duration"] = silence_duration
    config.ui["doubaotts_voice_type"] = voice_type
    config.ui["doubaotts_rate"] = voice_rate
    config.ui["voice_name"] = voice_type # 兼容性
    st.session_state['voice_rate'] = voice_rate # 确保语速参数被保存到session state

    # 显示配置状态
    if ak and sk and appid and token:
        st.success(tr("Doubao TTS configured"))
    else:
        missing = []
        if not ak:
            missing.append("Access Key")
        if not sk:
            missing.append("Secret Key")
        if not appid:
            missing.append("AppID")
        if not token:
            missing.append("Token")
        if missing:
            st.warning(tr("Please configure missing fields").format(fields=', '.join(missing)))


def render_voice_preview_new(tr, selected_engine):
    """渲染新的语音试听功能"""
    if st.button(tr("Preview Voice Synthesis"), use_container_width=True):
        play_content = tr("Voice Preview Sample")

        # 根据选择的引擎获取对应的语音配置
        voice_name = ""
        voice_rate = 1.0
        voice_pitch = 1.0

        if selected_engine == "edge_tts":
            voice_name = config.ui.get("edge_voice_name", "zh-CN-XiaoyiNeural-Female")
            voice_rate = config.ui.get("edge_rate", 1.0)
            voice_pitch = 1.0 + (config.ui.get("edge_pitch", 0) / 100.0)
        elif selected_engine == "azure_speech":
            voice_name = config.ui.get("azure_voice_name", "zh-CN-XiaoxiaoMultilingualNeural")
            voice_rate = config.ui.get("azure_rate", 1.0)
            voice_pitch = 1.0 + (config.ui.get("azure_pitch", 0) / 100.0)
        elif selected_engine == "soulvoice":
            voice_uri = config.soulvoice.get("voice_uri", "")
            if voice_uri:
                if not voice_uri.startswith("soulvoice:") and not voice_uri.startswith("speech:"):
                    voice_name = f"soulvoice:{voice_uri}"
                else:
                    voice_name = voice_uri if voice_uri.startswith("soulvoice:") else f"soulvoice:{voice_uri}"
            voice_rate = 1.0  # SoulVoice 使用默认语速
            voice_pitch = 1.0  # SoulVoice 不支持音调调节
        elif selected_engine == "tencent_tts":
            voice_type = config.ui.get("tencent_voice_type", "101001")
            voice_name = f"tencent:{voice_type}"
            voice_rate = config.ui.get("tencent_rate", 1.0)
            voice_pitch = 1.0  # 腾讯云 TTS 不支持音调调节
        elif selected_engine == "qwen3_tts":
            vt = config.ui.get("qwen_voice_type", "Cherry")
            voice_name = f"qwen3:{vt}"
            voice_rate = config.ui.get("qwen3_rate", 1.0)
            voice_pitch = 1.0  # Qwen3 TTS 不支持音调调节
        elif selected_engine == "indextts2":
            reference_audio = config.indextts2.get("reference_audio", "")
            if reference_audio:
                voice_name = f"indextts2:{reference_audio}"
            voice_rate = 1.0  # IndexTTS2 不支持速度调节
            voice_pitch = 1.0  # IndexTTS2 不支持音调调节
        elif selected_engine == "doubaotts":
            voice_type = config.ui.get("doubaotts_voice_type", "BV700_streaming")
            voice_name = voice_type
            voice_rate = config.ui.get("doubaotts_rate", 1.0)
            voice_pitch = 1.0  # 豆包语音 TTS 不支持音调调节

        if not voice_name:
            st.error(tr("Please configure voice settings first"))
            return

        with st.spinner(tr("Synthesizing Voice")):
            temp_dir = utils.storage_dir("temp", create=True)
            audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")

            sub_maker = voice.tts(
                text=play_content,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_pitch=voice_pitch,
                voice_file=audio_file,
                tts_engine=st.session_state.get('tts_engine')
            )

            if sub_maker and os.path.exists(audio_file):
                st.success(tr("Voice synthesis successful"))

                # 播放音频
                with open(audio_file, 'rb') as audio_file_obj:
                    audio_bytes = audio_file_obj.read()
                    st.audio(audio_bytes, format='audio/mp3')

                # 清理临时文件
                try:
                    os.remove(audio_file)
                except:
                    pass
            else:
                st.error(tr("Voice synthesis failed"))


def render_azure_v2_settings(tr):
    """渲染Azure V2语音设置（保留兼容性）"""
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
    """渲染语音参数设置（保留兼容性）"""
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
        st.info(tr("SoulVoice pitch not supported"))


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
                st.success(tr("Voice synthesis successful"))
                st.audio(audio_file, format="audio/mp3")
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            else:
                st.error(tr("Voice synthesis failed"))


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
        'tts_engine': st.session_state.get('tts_engine', "edge_tts"),
    }

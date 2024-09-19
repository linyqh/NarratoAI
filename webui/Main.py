import sys
import os
import glob
import json
import time
import datetime
import traceback

# 将项目的根目录添加到系统路径中，以允许从项目导入模块
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

import streamlit as st

import os
from uuid import uuid4
import platform
import streamlit.components.v1 as components
from loguru import logger
from app.config import config

st.set_page_config(
    page_title="NarratoAI",
    page_icon="📽️",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/linyqh/NarratoAI/issues",
        'About': f"# NarratoAI:sunglasses: 📽️ \n #### Version: v{config.project_version} \n "
                 f"自动化影视解说视频详情请移步：https://github.com/linyqh/NarratoAI"
    },
)

from app.models.const import FILE_TYPE_IMAGES, FILE_TYPE_VIDEOS
from app.models.schema import VideoClipParams, VideoAspect, VideoConcatMode
from app.services import task as tm, llm, voice, material
from app.utils import utils

proxy_url_http = config.proxy.get("http", "") or os.getenv("VPN_PROXY_URL", "")
proxy_url_https = config.proxy.get("https", "") or os.getenv("VPN_PROXY_URL", "")
os.environ["HTTP_PROXY"] = proxy_url_http
os.environ["HTTPS_PROXY"] = proxy_url_https

hide_streamlit_style = """
<style>#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 6px; padding-bottom: 10px; padding-left: 20px; padding-right: 20px;}</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
st.title(f"NarratoAI :sunglasses:📽️")
support_locales = [
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "en-US",
]
font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()

if 'video_subject' not in st.session_state:
    st.session_state['video_subject'] = ''
if 'video_clip_json' not in st.session_state:
    st.session_state['video_clip_json'] = ''
if 'video_plot' not in st.session_state:
    st.session_state['video_plot'] = ''
if 'ui_language' not in st.session_state:
    st.session_state['ui_language'] = config.ui.get("language", system_locale)


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def open_task_folder(task_id):
    try:
        sys = platform.system()
        path = os.path.join(root_dir, "storage", "tasks", task_id)
        if os.path.exists(path):
            if sys == 'Windows':
                os.system(f"start {path}")
            if sys == 'Darwin':
                os.system(f"open {path}")
    except Exception as e:
        logger.error(e)


def scroll_to_bottom():
    js = f"""
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){{
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {{
                sections[index].scrollTop = sections[index].scrollHeight;
            }}
        }}
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        record['message'] = record['message'].replace(root_dir, ".")

        _format = '<green>{time:%Y-%m-%d %H:%M:%S}</> | ' + \
                  '<level>{level}</> | ' + \
                  '"{file.path}:{line}":<blue> {function}</> ' + \
                  '- <level>{message}</>' + "\n"
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


def tr(key):
    loc = locales.get(st.session_state['ui_language'], {})
    return loc.get("Translation", {}).get(key, key)


st.write(tr("Get Help"))

# 基础设置
with st.expander(tr("Basic Settings"), expanded=False):
    config_panels = st.columns(3)
    left_config_panel = config_panels[0]
    middle_config_panel = config_panels[1]
    right_config_panel = config_panels[2]
    with left_config_panel:
        display_languages = []
        selected_index = 0
        for i, code in enumerate(locales.keys()):
            display_languages.append(f"{code} - {locales[code].get('Language')}")
            if code == st.session_state['ui_language']:
                selected_index = i

        selected_language = st.selectbox(tr("Language"), options=display_languages,
                                         index=selected_index)
        if selected_language:
            code = selected_language.split(" - ")[0].strip()
            st.session_state['ui_language'] = code
            config.ui['language'] = code

        HTTP_PROXY = st.text_input(tr("HTTP_PROXY"), value=proxy_url_http)
        HTTPS_PROXY = st.text_input(tr("HTTPs_PROXY"), value=proxy_url_https)
        if HTTP_PROXY:
            config.proxy["http"] = HTTP_PROXY
        if HTTPS_PROXY:
            config.proxy["https"] = HTTPS_PROXY


    with middle_config_panel:
        #   openai
        #   moonshot (月之暗面)
        #   oneapi
        #   g4f
        #   azure
        #   qwen (通义千问)
        #   gemini
        #   ollama
        # llm_providers = ['Gemini', 'OpenAI', 'Moonshot', 'Azure', 'Qwen', 'Ollama', 'G4f', 'OneAPI', "Cloudflare"]
        llm_providers = ['Gemini']
        saved_llm_provider = config.app.get("llm_provider", "OpenAI").lower()
        saved_llm_provider_index = 0
        for i, provider in enumerate(llm_providers):
            if provider.lower() == saved_llm_provider:
                saved_llm_provider_index = i
                break

        llm_provider = st.selectbox(tr("LLM Provider"), options=llm_providers, index=saved_llm_provider_index)
        llm_provider = llm_provider.lower()
        config.app["llm_provider"] = llm_provider

        llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
        llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
        llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
        llm_account_id = config.app.get(f"{llm_provider}_account_id", "")
        st_llm_api_key = st.text_input(tr("API Key"), value=llm_api_key, type="password")
        st_llm_base_url = st.text_input(tr("Base Url"), value=llm_base_url)
        st_llm_model_name = st.text_input(tr("Model Name"), value=llm_model_name)
        if st_llm_api_key:
            config.app[f"{llm_provider}_api_key"] = st_llm_api_key
        if st_llm_base_url:
            config.app[f"{llm_provider}_base_url"] = st_llm_base_url
        if st_llm_model_name:
            config.app[f"{llm_provider}_model_name"] = st_llm_model_name

        if llm_provider == 'cloudflare':
            st_llm_account_id = st.text_input(tr("Account ID"), value=llm_account_id)
            if st_llm_account_id:
                config.app[f"{llm_provider}_account_id"] = st_llm_account_id

    with right_config_panel:
        pexels_api_keys = config.app.get("pexels_api_keys", [])
        if isinstance(pexels_api_keys, str):
            pexels_api_keys = [pexels_api_keys]
        pexels_api_key = ", ".join(pexels_api_keys)

        pexels_api_key = st.text_input(tr("Pexels API Key"), value=pexels_api_key, type="password")
        pexels_api_key = pexels_api_key.replace(" ", "")
        if pexels_api_key:
            config.app["pexels_api_keys"] = pexels_api_key.split(",")

panel = st.columns(3)
left_panel = panel[0]
middle_panel = panel[1]
right_panel = panel[2]

params = VideoClipParams()

# 左侧面板
with left_panel:
    with st.container(border=True):
        st.write(tr("Video Script Configuration"))
        # 脚本语言
        video_languages = [
            (tr("Auto Detect"), ""),
        ]
        for code in ["zh-CN", "en-US", "zh-TW"]:
            video_languages.append((code, code))

        selected_index = st.selectbox(tr("Script Language"),
                                      index=0,
                                      options=range(len(video_languages)),  # 使用索引作为内部选项值
                                      format_func=lambda x: video_languages[x][0]  # 显示给用户的是标签
                                      )
        params.video_language = video_languages[selected_index][1]

        # 脚本路径
        suffix = "*.json"
        song_dir = utils.script_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        script_list = []
        for file in files:
            script_list.append({
                "name": os.path.basename(file),
                "size": os.path.getsize(file),
                "file": file,
            })

        script_path = [(tr("Auto Generate"), ""), ]
        for code in [file['file'] for file in script_list]:
            script_path.append((code, code))

        selected_json2 = st.selectbox(tr("Script Files"),
                                      index=0,
                                      options=range(len(script_path)),  # 使用索引作为内部选项值
                                      format_func=lambda x: script_path[x][0]  # 显示给用户的是标签
                                      )
        params.video_clip_json = script_path[selected_json2][1]
        video_json_file = params.video_clip_json

        # 视频文件处理
        files = []
        for suffix in ["*.mp4", "*.mov", "*.avi", "*.mkv"]:
            files.extend(glob.glob(os.path.join(utils.video_dir(), suffix)))
        files = files[::-1]

        video_list = []
        for file in files:
            video_list.append({
                "name": os.path.basename(file),
                "size": os.path.getsize(file),
                "file": file,
            })

        video_path = [("None", ""), (tr("Upload Local Files"), "local")]
        for code in [file['file'] for file in video_list]:
            video_path.append((code, code))

        selected_index2 = st.selectbox(tr("Video File"),
                                       index=0,
                                       options=range(len(video_path)),  # 使用索引作为内部选项值
                                       format_func=lambda x: video_path[x][0]  # 显示给用户的是标签
                                       )
        params.video_origin_path = video_path[selected_index2][1]
        config.app["video_origin_path"] = params.video_origin_path

        # 从本地上传 mp4 文件
        if params.video_origin_path == "local":
            _supported_types = FILE_TYPE_VIDEOS
            uploaded_file = st.file_uploader(
                tr("Upload Local Files"),
                type=["mp4", "mov", "avi", "flv", "mkv"],
                accept_multiple_files=False,
            )
            if uploaded_file is not None:
                # 构造保存路径
                video_file_path = os.path.join(utils.video_dir(), uploaded_file.name)
                file_name, file_extension = os.path.splitext(uploaded_file.name)
                # 检查文件是否存在，如果存在则添加时间戳
                if os.path.exists(video_file_path):
                    timestamp = time.strftime("%Y%m%d%H%M%S")
                    file_name_with_timestamp = f"{file_name}_{timestamp}"
                    video_file_path = os.path.join(utils.video_dir(), file_name_with_timestamp + file_extension)
                # 将文件保存到指定目录
                with open(video_file_path, "wb") as f:
                    f.write(uploaded_file.read())
                    st.success(tr("File Uploaded Successfully"))
                    time.sleep(1)
                    st.rerun()
            # params.video_origin_path = video_path[selected_index2][1]
            # config.app["video_origin_path"] = params.video_origin_path

        # 剧情内容
        video_plot = st.text_area(
            tr("Plot Description"),
            value=st.session_state['video_plot'],
            height=180
        )

        if st.button(tr("Video Script Generate"), key="auto_generate_script"):
            with st.spinner(tr("Video Script Generate")):
                if video_json_file == "" and params.video_origin_path != "":
                    # 使用大模型生成视频脚本
                    script = llm.gemini_video2json(
                        video_origin_name=params.video_origin_path.split("\\")[-1],
                        video_origin_path=params.video_origin_path,
                        video_plot=video_plot,
                        language=params.video_language,
                    )
                    st.session_state['video_clip_json'] = script
                    cleaned_string = script.strip("```json").strip("```")
                    st.session_state['video_script_list'] = json.loads(cleaned_string)
                else:
                    with open(video_json_file, 'r', encoding='utf-8') as f:
                        script = f.read()
                        st.session_state['video_clip_json'] = script
                        cleaned_string = script.strip("```json").strip("```")
                        st.session_state['video_script_list'] = json.loads(cleaned_string)

        video_clip_json_details = st.text_area(
            tr("Video Script"),
            value=st.session_state['video_clip_json'],
            height=180
        )

        button_columns = st.columns(2)
        with button_columns[0]:
            if st.button(tr("Save Script"), key="auto_generate_terms", use_container_width=True):
                if not video_clip_json_details:
                    st.error(tr("请输入视频脚本"))
                    st.stop()

                with st.spinner(tr("Save Script")):
                    script_dir = utils.script_dir()
                    # 获取当前时间戳，形如 2024-0618-171820
                    timestamp = datetime.datetime.now().strftime("%Y-%m%d-%H%M%S")
                    save_path = os.path.join(script_dir, f"{timestamp}.json")

                    # 尝试解析输入的 JSON 数据
                    input_json = str(video_clip_json_details)
                    # 去掉json的头尾标识
                    input_json = input_json.strip('```json').strip('```')
                    try:
                        data = utils.add_new_timestamps(json.loads(input_json))
                    except Exception as err:
                        raise ValueError(
                            f"视频脚本格式错误，请检查脚本是否符合 JSON 格式；{err} \n\n{traceback.format_exc()}")

                    # 检查是否是一个列表
                    if not isinstance(data, list):
                        raise ValueError("JSON is not a list")

                    # 检查列表中的每个元素是否包含所需的键
                    required_keys = {"picture", "timestamp", "narration"}
                    for item in data:
                        if not isinstance(item, dict):
                            raise ValueError("List 元素不是字典")
                        if not required_keys.issubset(item.keys()):
                            raise ValueError("Dict 元素不包含必需的键")

                    # 存储为新的 JSON 文件
                    with open(save_path, 'w', encoding='utf-8') as file:
                        json.dump(data, file, ensure_ascii=False, indent=4)
                        # 将data的值存储到 session_state 中，类似缓存
                        st.session_state['video_script_list'] = data
                        st.session_state['video_clip_json_path'] = save_path
                        # 刷新页面
                        st.rerun()


        def caijian():
            with st.spinner(tr("裁剪视频中...")):
                st.session_state['task_id'] = str(uuid4())

            if st.session_state.get('video_script_list', None) is not None:
                video_script_list = st.session_state.video_script_list
                time_list = [i['timestamp'] for i in video_script_list]
                subclip_videos = material.clip_videos(
                    task_id=st.session_state['task_id'],
                    timestamp_terms=time_list,
                    origin_video=params.video_origin_path
                )
                if subclip_videos is None:
                    st.error(tr("裁剪视频失败"))
                    st.stop()
                st.session_state['subclip_videos'] = subclip_videos
                for video_script in video_script_list:
                    try:
                        video_script['path'] = subclip_videos[video_script['timestamp']]
                    except KeyError as e:
                        st.error(f"裁剪视频失败")
                # logger.debug(f"当前的脚本为：{st.session_state.video_script_list}")
            else:
                st.error(tr("请先生成视频脚本"))


        with button_columns[1]:
            if st.button(tr("Crop Video"), key="auto_crop_video", use_container_width=True):
                caijian()

# 新中间面板
with middle_panel:
    with st.container(border=True):
        st.write(tr("Video Settings"))
        video_concat_modes = [
            (tr("Sequential"), "sequential"),
            (tr("Random"), "random"),
        ]
        # video_sources = [
        #     (tr("Pexels"), "pexels"),
        #     (tr("Pixabay"), "pixabay"),
        #     (tr("Local file"), "local"),
        #     (tr("TikTok"), "douyin"),
        #     (tr("Bilibili"), "bilibili"),
        #     (tr("Xiaohongshu"), "xiaohongshu"),
        # ]
        #
        # saved_video_source_name = config.app.get("video_source", "pexels")
        # saved_video_source_index = [v[1] for v in video_sources].index(
        #     saved_video_source_name
        # )
        #
        # selected_index = st.selectbox(
        #     tr("Video Source"),
        #     options=range(len(video_sources)),
        #     format_func=lambda x: video_sources[x][0],
        #     index=saved_video_source_index,
        # )
        # params.video_source = video_sources[selected_index][1]
        # config.app["video_source"] = params.video_source
        #
        # if params.video_source == "local":
        #     _supported_types = FILE_TYPE_VIDEOS + FILE_TYPE_IMAGES
        #     uploaded_files = st.file_uploader(
        #         "Upload Local Files",
        #         type=["mp4", "mov", "avi", "flv", "mkv", "jpg", "jpeg", "png"],
        #         accept_multiple_files=True,
        #     )

        selected_index = st.selectbox(
            tr("Video Concat Mode"),
            index=1,
            options=range(len(video_concat_modes)),  # 使用索引作为内部选项值
            format_func=lambda x: video_concat_modes[x][0],  # 显示给用户的是标签
        )
        params.video_concat_mode = VideoConcatMode(
            video_concat_modes[selected_index][1]
        )

        video_aspect_ratios = [
            (tr("Portrait"), VideoAspect.portrait.value),
            (tr("Landscape"), VideoAspect.landscape.value),
        ]
        selected_index = st.selectbox(
            tr("Video Ratio"),
            options=range(len(video_aspect_ratios)),  # 使用索引作为内部选项值
            format_func=lambda x: video_aspect_ratios[x][0],  # 显示给用户的是标签
        )
        params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])

        params.video_clip_duration = st.selectbox(
            tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
        )
        params.video_count = st.selectbox(
            tr("Number of Videos Generated Simultaneously"),
            options=[1, 2, 3, 4, 5],
            index=0,
        )
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # tts_providers = ['edge', 'azure']
        # tts_provider = st.selectbox(tr("TTS Provider"), tts_providers)

        voices = voice.get_all_azure_voices(filter_locals=support_locales)
        friendly_names = {
            v: v.replace("Female", tr("Female"))
            .replace("Male", tr("Male"))
            .replace("Neural", "")
            for v in voices
        }
        saved_voice_name = config.ui.get("voice_name", "")
        saved_voice_name_index = 0
        if saved_voice_name in friendly_names:
            saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
        else:
            for i, v in enumerate(voices):
                if (
                        v.lower().startswith(st.session_state["ui_language"].lower())
                        and "V2" not in v
                ):
                    saved_voice_name_index = i
                    break

        selected_friendly_name = st.selectbox(
            tr("Speech Synthesis"),
            options=list(friendly_names.values()),
            index=saved_voice_name_index,
        )

        voice_name = list(friendly_names.keys())[
            list(friendly_names.values()).index(selected_friendly_name)
        ]
        params.voice_name = voice_name
        config.ui["voice_name"] = voice_name

        if st.button(tr("Play Voice")):
            play_content = params.video_subject
            if not play_content:
                play_content = params.video_script
            if not play_content:
                play_content = tr("Voice Example")
            with st.spinner(tr("Synthesizing Voice")):
                temp_dir = utils.storage_dir("temp", create=True)
                audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=params.voice_rate,
                    voice_file=audio_file,
                )
                # if the voice file generation failed, try again with a default content.
                if not sub_maker:
                    play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                    sub_maker = voice.tts(
                        text=play_content,
                        voice_name=voice_name,
                        voice_rate=params.voice_rate,
                        voice_file=audio_file,
                    )

                if sub_maker and os.path.exists(audio_file):
                    st.audio(audio_file, format="audio/mp3")
                    if os.path.exists(audio_file):
                        os.remove(audio_file)

        if voice.is_azure_v2_voice(voice_name):
            saved_azure_speech_region = config.azure.get("speech_region", "")
            saved_azure_speech_key = config.azure.get("speech_key", "")
            azure_speech_region = st.text_input(
                tr("Speech Region"), value=saved_azure_speech_region
            )
            azure_speech_key = st.text_input(
                tr("Speech Key"), value=saved_azure_speech_key, type="password"
            )
            config.azure["speech_region"] = azure_speech_region
            config.azure["speech_key"] = azure_speech_key

        params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
        )

        params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Background Music"),
            index=1,
            options=range(len(bgm_options)),  # 使用索引作为内部选项值
            format_func=lambda x: bgm_options[x][0],  # 显示给用户的是标签
        )
        # 获取选择的背景音乐类型
        params.bgm_type = bgm_options[selected_index][1]

        # 根据选择显示或隐藏组件
        if params.bgm_type == "custom":
            custom_bgm_file = st.text_input(tr("Custom Background Music File"))
            if custom_bgm_file and os.path.exists(custom_bgm_file):
                params.bgm_file = custom_bgm_file
                # st.write(f":red[已选择自定义背景音乐]：**{custom_bgm_file}**")
        params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
        )

# 新右侧面板
with right_panel:
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))
        params.subtitle_enabled = st.checkbox(tr("Enable Subtitles"), value=True)
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "")
        saved_font_name_index = 0
        if saved_font_name in font_names:
            saved_font_name_index = font_names.index(saved_font_name)
        params.font_name = st.selectbox(
            tr("Font"), font_names, index=saved_font_name_index
        )
        config.ui["font_name"] = params.font_name

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
        params.subtitle_position = subtitle_positions[selected_index][1]

        if params.subtitle_position == "custom":
            custom_position = st.text_input(
                tr("Custom Position (% from top)"), value="70.0"
            )
            try:
                params.custom_position = float(custom_position)
                if params.custom_position < 0 or params.custom_position > 100:
                    st.error(tr("Please enter a value between 0 and 100"))
            except ValueError:
                st.error(tr("Please enter a valid number"))

        font_cols = st.columns([0.3, 0.7])
        with font_cols[0]:
            saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
            params.text_fore_color = st.color_picker(
                tr("Font Color"), saved_text_fore_color
            )
            config.ui["text_fore_color"] = params.text_fore_color

        with font_cols[1]:
            saved_font_size = config.ui.get("font_size", 60)
            params.font_size = st.slider(tr("Font Size"), 30, 100, saved_font_size)
            config.ui["font_size"] = params.font_size

        stroke_cols = st.columns([0.3, 0.7])
        with stroke_cols[0]:
            params.stroke_color = st.color_picker(tr("Stroke Color"), "#000000")
        with stroke_cols[1]:
            params.stroke_width = st.slider(tr("Stroke Width"), 0.0, 10.0, 1.5)

# 视频编辑面板
with st.expander(tr("Video Check"), expanded=False):
    try:
        video_list = st.session_state['video_script_list']
    except KeyError as e:
        video_list = []

    # 计算列数和行数
    num_videos = len(video_list)
    cols_per_row = 3
    rows = (num_videos + cols_per_row - 1) // cols_per_row  # 向上取整计算行数

    # 使用容器展示视频
    for row in range(rows):
        cols = st.columns(cols_per_row)
        for col in range(cols_per_row):
            index = row * cols_per_row + col
            if index < num_videos:
                with cols[col]:
                    video_info = video_list[index]
                    video_path = video_info.get('path')
                    if video_path is not None:
                        initial_narration = video_info['narration']
                        initial_picture = video_info['picture']
                        initial_timestamp = video_info['timestamp']

                        with open(video_path, 'rb') as video_file:
                            video_bytes = video_file.read()
                            st.video(video_bytes)

                        # 可编辑的输入框
                        text_panels = st.columns(2)
                        with text_panels[0]:
                            text1 = st.text_area(tr("timestamp"), value=initial_timestamp, height=20)
                        with text_panels[1]:
                            text2 = st.text_area(tr("Picture description"), value=initial_picture, height=20)
                        logger.debug(initial_narration)
                        text3 = st.text_area(tr("Narration"), value=initial_narration, height=100)

                        # 重新生成按钮
                        if st.button(tr("Rebuild"), key=f"button_{index}"):
                            # 更新video_list中的对应项
                            video_list[index]['timestamp'] = text1
                            video_list[index]['picture'] = text2
                            video_list[index]['narration'] = text3

                            for video in video_list:
                                if 'path' in video:
                                    del video['path']
                                    # 更新session_state以确保更改被保存
                            st.session_state['video_clip_json'] = utils.to_json(video_list)
                            # 替换原JSON 文件
                            with open(video_json_file, 'w', encoding='utf-8') as file:
                                json.dump(video_list, file, ensure_ascii=False, indent=4)
                            caijian()
                            st.rerun()

start_button = st.button(tr("Generate Video"), use_container_width=True, type="primary")
if start_button:
    config.save_config()
    task_id = st.session_state.get('task_id')
    if st.session_state.get('video_script_json_path') is not None:
        params.video_clip_json = st.session_state.get('video_clip_json')

    logger.debug(f"当前的脚本为：{params.video_clip_json}")

    if not task_id:
        st.error(tr("请先裁剪视频"))
        scroll_to_bottom()
        st.stop()
    if not params.video_clip_json:
        st.error(tr("脚本文件不能为空"))
        scroll_to_bottom()
        st.stop()
    if not params.video_origin_path:
        st.error(tr("视频文件不能为空"))
        scroll_to_bottom()
        st.stop()
    if llm_provider != 'g4f' and not config.app.get(f"{llm_provider}_api_key", ""):
        st.error(tr("请输入 LLM API 密钥"))
        scroll_to_bottom()
        st.stop()

    log_container = st.empty()
    log_records = []


    def log_received(msg):
        with log_container:
            log_records.append(msg)
            st.code("\n".join(log_records))


    logger.add(log_received)

    st.toast(tr("生成视频"))
    logger.info(tr("开始生成视频"))
    logger.info(utils.to_json(params))
    scroll_to_bottom()

    result = tm.start_subclip(task_id=task_id, params=params, subclip_path_videos=st.session_state.subclip_videos)

    video_files = result.get("videos", [])
    st.success(tr("视频生成完成"))
    try:
        if video_files:
            # 将视频播放器居中
            player_cols = st.columns(len(video_files) * 2 + 1)
            for i, url in enumerate(video_files):
                player_cols[i * 2 + 1].video(url)
    except Exception as e:
        pass

    open_task_folder(task_id)
    logger.info(tr("视频生成完成"))
    scroll_to_bottom()

config.save_config()

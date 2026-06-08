import streamlit as st
import os
import sys
import time
from html import escape
from loguru import logger
from app.config import config
from webui.components import basic_settings, video_settings, audio_settings, subtitle_settings, script_settings, \
    system_settings
# from webui.utils import cache, file_utils
from app.utils import utils
from app.utils import ffmpeg_utils
from app.models.schema import VideoClipParams, VideoAspect


# 初始化配置 - 必须是第一个 Streamlit 命令
st.set_page_config(
    page_title="NarratoAI",
    page_icon="📽️",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/linyqh/NarratoAI/issues",
        'About': f"# Narrato:blue[AI] :sunglasses: 📽️ \n #### Version: v{config.project_version} \n "
                 f"自动化影视解说视频详情请移步：https://github.com/linyqh/NarratoAI"
    },
)

# 设置页面样式
hide_streamlit_style = """
<style>#root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 2rem; padding-bottom: 10px; padding-left: 20px; padding-right: 20px;}</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)


def init_log():
    """初始化日志配置"""
    from loguru import logger
    logger.remove()
    _lvl = "INFO"  # 改为 INFO 级别，过滤掉 DEBUG 日志

    def format_record(record):
        # 简化日志格式化处理，不尝试按特定字符串过滤torch相关内容
        file_path = record["file"].path
        relative_path = os.path.relpath(file_path, config.root_dir)
        record["file"].path = f"./{relative_path}"
        record['message'] = record['message'].replace(config.root_dir, ".")

        _format = '<green>{time:%Y-%m-%d %H:%M:%S}</> | ' + \
                  '<level>{level}</> | ' + \
                  '"{file.path}:{line}":<blue> {function}</> ' + \
                  '- <level>{message}</>' + "\n"
        return _format

    # 添加日志过滤器
    def log_filter(record):
        """过滤不必要的日志消息"""
        # 过滤掉启动时的噪音日志（即使在 DEBUG 模式下也可以选择过滤）
        ignore_patterns = [
            "Examining the path of torch.classes raised",
            "torch.cuda.is_available()",
            "CUDA initialization"
        ]
        return not any(pattern in record["message"] for pattern in ignore_patterns)

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
        filter=log_filter
    )

    # 应用启动后，可以再添加更复杂的过滤器
    def setup_advanced_filters():
        """在应用完全启动后设置高级过滤器"""
        try:
            for handler_id in logger._core.handlers:
                logger.remove(handler_id)

            # 重新添加带有高级过滤的处理器
            def advanced_filter(record):
                """更复杂的过滤器，在应用启动后安全使用"""
                ignore_messages = [
                    "Examining the path of torch.classes raised",
                    "torch.cuda.is_available()",
                    "CUDA initialization"
                ]
                return not any(msg in record["message"] for msg in ignore_messages)

            logger.add(
                sys.stdout,
                level=_lvl,
                format=format_record,
                colorize=True,
                filter=advanced_filter
            )
        except Exception as e:
            # 如果过滤器设置失败，确保日志仍然可用
            logger.add(
                sys.stdout,
                level=_lvl,
                format=format_record,
                colorize=True
            )
            logger.error(f"设置高级日志过滤器失败: {e}")

    # 将高级过滤器设置放到启动主逻辑后
    import threading
    threading.Timer(5.0, setup_advanced_filters).start()


def init_global_state():
    """初始化全局状态"""
    if 'video_clip_json' not in st.session_state:
        st.session_state['video_clip_json'] = []
    if 'video_plot' not in st.session_state:
        st.session_state['video_plot'] = ''
    if 'ui_language' not in st.session_state:
        st.session_state['ui_language'] = config.ui.get("language", utils.get_system_locale())
    # 移除subclip_videos初始化 - 现在使用统一裁剪策略


def tr(key):
    """翻译函数"""
    i18n_dir = os.path.join(os.path.dirname(__file__), "webui", "i18n")
    locales = utils.load_locales(i18n_dir)
    loc = locales.get(st.session_state['ui_language'], {})
    return loc.get("Translation", {}).get(key, key)


def get_help_text():
    """返回带当前项目版本号的帮助文案"""
    return tr("Get Help").replace("🎉🎉🎉", f" v{config.project_version}")


def render_generate_button():
    """渲染生成按钮和处理逻辑"""
    if st.button(tr("Generate Video"), use_container_width=True, type="primary"):
        from app.services import task as tm
        from app.services import state as sm
        from app.models import const
        import threading
        import time
        import uuid

        config.save_config()

        # 移除task_id检查 - 现在使用统一裁剪策略，不再需要预裁剪
        # 直接检查必要的文件是否存在
        if not st.session_state.get('video_clip_json_path'):
            st.error(tr("Script file cannot be empty"))
            return
        if not st.session_state.get('video_origin_path'):
            st.error(tr("Video file cannot be empty"))
            return

        # 获取所有参数
        script_params = script_settings.get_script_params()
        video_params = video_settings.get_video_params()
        audio_params = audio_settings.get_audio_params()
        subtitle_params = subtitle_settings.get_subtitle_params()

        # 合并所有参数
        all_params = {
            **script_params,
            **video_params,
            **audio_params,
            **subtitle_params
        }

        # 创建参数对象
        params = VideoClipParams(**all_params)

        # 生成一个新的task_id用于本次处理
        task_id = str(uuid.uuid4())

        @st.dialog(tr("Generating Video"), width="large")
        def generate_video_dialog():
            st.markdown(
                """
                <style>
                    div[data-testid="stDialog"] div[data-testid="stStatusWidget"] {
                        margin-top: 0.25rem;
                    }
                    div[data-testid="stDialog"] div[data-testid="stProgress"] {
                        margin-bottom: 0.75rem;
                    }
                    div[data-testid="stDialog"] video {
                        max-height: 62vh;
                        object-fit: contain;
                        background: #000;
                    }
                </style>
                """,
                unsafe_allow_html=True,
            )

            progress_bar = st.progress(0)
            status_panel = st.status(tr("Generating Video"), expanded=True)
            status_panel.write(tr("Generating Video"))

            def run_task():
                try:
                    tm.start_subclip_unified(
                        task_id=task_id,
                        params=params
                    )
                except Exception as e:
                    logger.error(f"任务执行失败: {e}")
                    current_task = sm.state.get_task(task_id) or {}
                    sm.state.update_task(
                        task_id,
                        state=const.TASK_STATE_FAILED,
                        progress=current_task.get("progress", 0),
                        message=str(e),
                    )

            # 在新线程中启动任务
            thread = threading.Thread(target=run_task)
            thread.start()

            last_status_key = None

            # 轮询任务状态
            while True:
                task = sm.state.get_task(task_id)
                if task:
                    progress = task.get("progress", 0)
                    state = task.get("state")

                    try:
                        progress = int(progress)
                    except (TypeError, ValueError):
                        progress = 0
                    progress = max(0, min(progress, 100))

                    # 更新进度条和阶段状态
                    progress_bar.progress(progress / 100)
                    current_message = task.get("message") or f"Processing... {progress}%"
                    status_label = f"{current_message} ({progress}%)"
                    status_key = (state, progress, current_message)
                    if status_key != last_status_key:
                        status_panel.write(status_label)
                        last_status_key = status_key

                    if state == const.TASK_STATE_COMPLETE:
                        status_panel.update(
                            label=tr("Video Generation Completed"),
                            state="complete",
                            expanded=False,
                        )
                        progress_bar.progress(1.0)

                        # 显示结果
                        video_files = task.get("videos", [])
                        try:
                            if video_files:
                                aspect = getattr(params, "video_aspect", "")
                                aspect = getattr(aspect, "value", aspect)
                                preview_width = 320 if aspect in {
                                    VideoAspect.portrait.value,
                                    VideoAspect.portrait_2.value,
                                } else 600
                                for url in video_files:
                                    _, preview_col, _ = st.columns([1, 2, 1])
                                    with preview_col:
                                        st.video(url, width=preview_width)
                        except Exception as e:
                            logger.error(f"播放视频失败: {e}")

                        st.success(tr("Video Generation Completed"))
                        break

                    if state == const.TASK_STATE_FAILED:
                        status_panel.update(
                            label=f"{tr('Task failed')}: {task.get('message', 'Unknown error')}",
                            state="error",
                            expanded=True,
                        )
                        st.error(f"{tr('Task failed')}: {task.get('message', 'Unknown error')}")
                        break

                time.sleep(0.5)

        generate_video_dialog()


def get_voice_name_for_tts_engine(tts_engine: str) -> str:
    """根据TTS引擎获取用户选择的音色"""
    if tts_engine == 'edge_tts':
        return config.ui.get('edge_voice_name', 'zh-CN-XiaoxiaoNeural-Female')
    if tts_engine == 'azure_speech':
        return config.ui.get('azure_voice_name', 'zh-CN-XiaoxiaoMultilingualNeural')
    if tts_engine == 'tencent_tts':
        return f"tencent:{config.ui.get('tencent_voice_type', '101001')}"
    if tts_engine == 'qwen3_tts':
        return f"qwen3:{config.ui.get('qwen_voice_type', 'Cherry')}"
    if tts_engine == config.INDEXTTS2_ENGINE:
        reference_audio = config.indextts2.get('reference_audio', '')
        if reference_audio:
            return f"{config.INDEXTTS2_VOICE_PREFIX}{reference_audio}"
        return config.ui.get('voice_name', '')
    if config.normalize_tts_engine_name(tts_engine) == config.INDEXTTS_ENGINE:
        reference_audio = config.indextts.get('reference_audio', '')
        if reference_audio:
            return f"{config.INDEXTTS_VOICE_PREFIX}{reference_audio}"
        return config.ui.get('voice_name', '')
    if tts_engine == config.OMNIVOICE_ENGINE:
        mode = config.omnivoice.get('mode', 'auto')
        reference_audio = config.omnivoice.get('reference_audio', '')
        if mode == 'voice_clone' and reference_audio:
            return f"{config.OMNIVOICE_VOICE_PREFIX}{reference_audio}"
        return f"{config.OMNIVOICE_VOICE_PREFIX}{mode}"
    if tts_engine == 'doubaotts':
        return config.ui.get('doubaotts_voice_type', 'BV700_streaming')
    if tts_engine == 'soulvoice':
        voice_uri = config.soulvoice.get('voice_uri', '')
        if voice_uri and not voice_uri.startswith(('soulvoice:', 'speech:')):
            return f"soulvoice:{voice_uri}"
        return voice_uri
    return config.ui.get('voice_name', config.ui.get('edge_voice_name', 'zh-CN-XiaoxiaoNeural-Female'))


def get_jianying_export_params(draft_name=None) -> VideoClipParams:
    """获取导出到剪映草稿的参数"""
    tts_engine = st.session_state.get('tts_engine', config.ui.get('tts_engine', 'edge_tts'))
    voice_name = get_voice_name_for_tts_engine(tts_engine)
    voice_rate = st.session_state.get('voice_rate', 1.0)
    voice_pitch = st.session_state.get('voice_pitch', 1.0)
    subtitle_paths = st.session_state.get('subtitle_paths', [])
    if isinstance(subtitle_paths, str):
        subtitle_paths = [subtitle_paths]
    subtitle_paths = [
        path for path in subtitle_paths
        if isinstance(path, str) and path.strip()
    ]
    if not subtitle_paths and st.session_state.get('subtitle_path'):
        subtitle_paths = [st.session_state.get('subtitle_path')]
    
    return VideoClipParams(
        video_clip_json_path=st.session_state['video_clip_json_path'],
        video_origin_path=st.session_state['video_origin_path'],
        video_origin_paths=st.session_state.get('video_origin_paths', []),
        original_subtitle_path=subtitle_paths[0] if subtitle_paths else "",
        original_subtitle_paths=subtitle_paths,
        tts_engine=tts_engine,
        voice_name=voice_name,
        voice_rate=voice_rate,
        voice_pitch=voice_pitch,
        n_threads=config.app.get('n_threads', 4),
        video_aspect=VideoAspect.landscape,
        subtitle_enabled=st.session_state.get('subtitle_enabled', False),
        font_name=st.session_state.get('font_name', 'Microsoft YaHei'),
        font_size=st.session_state.get('font_size', 24),
        text_fore_color=st.session_state.get('text_fore_color', '#FFFFFF'),
        subtitle_position=st.session_state.get('subtitle_position', 'bottom'),
        custom_position=st.session_state.get('custom_position', 70.0),
        tts_volume=st.session_state.get('tts_volume', 1.0),
        original_volume=st.session_state.get('original_volume', 0.7),
        bgm_volume=st.session_state.get('bgm_volume', 0.3),
        draft_name=(
            draft_name
            if draft_name is not None
            else st.session_state.get('draft_name_input', f"NarratoAI_{int(time.time())}")
        )
    )


def _render_jianying_export_status():
    """渲染剪映导出的结果提示。"""
    result = st.session_state.get('jianying_export_result')
    error = st.session_state.get('jianying_export_error')

    if result:
        st.success(tr("Jianying draft exported successfully").format(name=result['draft_name']))
        st.info(tr("Draft saved to").format(path=result['draft_path']))
    elif error:
        st.error(f"{tr('Failed to export Jianying draft')}: {error}")


def _render_jianying_export_dialog():
    """使用弹窗确认剪映草稿名称。"""
    import uuid
    from loguru import logger

    @st.dialog(tr("Export to Jianying Draft"), width="small")
    def jianying_export_dialog():
        jianying_draft_path = config.ui.get("jianying_draft_path", "")
        dialog_title = escape(tr("Jianying export dialog title"))
        dialog_description = escape(tr("Jianying export dialog description"))
        destination_label = escape(tr("Jianying export destination"))
        destination_path = escape(jianying_draft_path or "-")

        st.markdown(
            f"""
            <style>
                .jianying-export-panel {{
                    display: flex;
                    gap: 12px;
                    align-items: flex-start;
                    padding: 14px;
                    margin: 2px 0 18px;
                    border: 1px solid rgba(255, 75, 75, 0.24);
                    border-radius: 8px;
                    background: linear-gradient(135deg, rgba(255, 75, 75, 0.10), rgba(255, 255, 255, 0.96));
                }}
                .jianying-export-icon {{
                    width: 38px;
                    height: 38px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex: 0 0 auto;
                    border-radius: 8px;
                    color: #ffffff;
                    background: #ff4b4b;
                    font-size: 20px;
                    line-height: 1;
                }}
                .jianying-export-title {{
                    color: #202534;
                    font-size: 17px;
                    font-weight: 700;
                    line-height: 1.35;
                    margin-bottom: 4px;
                }}
                .jianying-export-description {{
                    color: #5f6575;
                    font-size: 13px;
                    line-height: 1.55;
                }}
                .jianying-export-path {{
                    padding: 10px 12px;
                    margin: 2px 0 16px;
                    border: 1px solid #e4e7ef;
                    border-radius: 8px;
                    background: #f8f9fc;
                    color: #323846;
                    font-size: 13px;
                    line-height: 1.45;
                    word-break: break-all;
                }}
                .jianying-export-path-label {{
                    display: block;
                    color: #7a8192;
                    font-size: 12px;
                    margin-bottom: 4px;
                }}
            </style>
            <div class="jianying-export-panel">
                <div class="jianying-export-icon">📤</div>
                <div>
                    <div class="jianying-export-title">{dialog_title}</div>
                    <div class="jianying-export-description">{dialog_description}</div>
                </div>
            </div>
            <div class="jianying-export-path">
                <span class="jianying-export-path-label">{destination_label}</span>
                {destination_path}
            </div>
            """,
            unsafe_allow_html=True,
        )

        draft_name = st.text_input(
            tr("Jianying draft name"),
            key="draft_name_input",
            placeholder="NarratoAI_",
        )

        error = st.session_state.get('jianying_export_error')
        if error:
            st.error(f"{tr('Failed to export Jianying draft')}: {error}")

        cancel_col, confirm_col = st.columns(2)
        with cancel_col:
            if st.button(tr("Cancel"), key="cancel_export", use_container_width=True):
                st.session_state['jianying_export_error'] = None
                st.rerun()

        with confirm_col:
            if st.button(tr("Confirm Export"), key="confirm_export", type="primary", use_container_width=True):
                draft_name = (draft_name or "").strip()
                if not draft_name:
                    st.error(tr("Please enter draft name"))
                    return

                # 创建任务ID
                task_id = str(uuid.uuid4())
                st.session_state['task_id'] = task_id

                # 构建参数
                try:
                    params = get_jianying_export_params(draft_name)
                except Exception as e:
                    logger.error(f"构建参数失败: {e}")
                    st.session_state['jianying_export_error'] = f"{tr('Failed to build parameters')}: {e}"
                    st.error(st.session_state['jianying_export_error'])
                    return

                with st.spinner(tr("Exporting to Jianying draft...")):
                    try:
                        from app.services import jianying_task

                        # 调用导出到剪映草稿的任务
                        result = jianying_task.start_export_jianying_draft(task_id, params)

                        # 记录日志
                        logger.info(f"成功导出到剪映草稿: {result['draft_name']}")
                        logger.info(f"草稿已保存到: {result['draft_path']}")

                        # 保存结果到session state
                        st.session_state['jianying_export_result'] = result
                        st.session_state['jianying_export_error'] = None
                        st.rerun()
                    except Exception as e:
                        logger.error(f"导出到剪映草稿失败: {e}")
                        import traceback
                        logger.error(f"错误详情: {traceback.format_exc()}")
                        st.session_state['jianying_export_error'] = str(e)
                        st.session_state['jianying_export_result'] = None
                        st.error(f"{tr('Failed to export Jianying draft')}: {e}")

    jianying_export_dialog()


def render_export_jianying_button():
    """渲染导出到剪映草稿按钮和处理逻辑"""
    import os
    import time
    
    # 初始化session state
    if 'jianying_export_result' not in st.session_state:
        st.session_state['jianying_export_result'] = None
    if 'jianying_export_error' not in st.session_state:
        st.session_state['jianying_export_error'] = None
    
    if st.button(tr("Export to Jianying Draft"), use_container_width=True, type="secondary"):
        config.save_config()
        
        if not st.session_state.get('video_clip_json_path'):
            st.error(tr("Script file cannot be empty"))
            return
        if not st.session_state.get('video_origin_path'):
            st.error(tr("Video file cannot be empty"))
            return
        
        jianying_draft_path = config.ui.get("jianying_draft_path", "")
        if not jianying_draft_path:
            st.error(tr("Please configure Jianying draft folder in basic settings"))
            return
        
        if not os.path.exists(jianying_draft_path):
            st.error(tr("Jianying draft folder does not exist").format(path=jianying_draft_path))
            return
        
        st.session_state['jianying_export_result'] = None
        st.session_state['jianying_export_error'] = None
        st.session_state['draft_name_input'] = f"NarratoAI_{int(time.time())}"
        _render_jianying_export_dialog()
    
    _render_jianying_export_status()



def main():
    """主函数"""
    init_log()
    init_global_state()

    # ===== 显式注册 LLM 提供商（最佳实践）=====
    # 在应用启动时立即注册，确保所有 LLM 功能可用
    if 'llm_providers_registered' not in st.session_state:
        try:
            from app.services.llm.providers import register_all_providers
            register_all_providers()
            st.session_state['llm_providers_registered'] = True
            logger.info("✅ LLM 提供商注册成功")
        except Exception as e:
            logger.error(f"❌ LLM 提供商注册失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            st.error(tr("LLM initialization failed").format(error=str(e)))
            # 不抛出异常，允许应用继续运行（但 LLM 功能不可用）

    # 检测FFmpeg硬件加速，但只打印一次日志（使用 session_state 持久化）
    if 'hwaccel_logged' not in st.session_state:
        st.session_state['hwaccel_logged'] = False
    
    hwaccel_info = ffmpeg_utils.detect_hardware_acceleration()
    if not st.session_state['hwaccel_logged']:
        if hwaccel_info["available"]:
            logger.info(f"FFmpeg硬件加速检测结果: 可用 | 类型: {hwaccel_info['type']} | 编码器: {hwaccel_info['encoder']} | 独立显卡: {hwaccel_info['is_dedicated_gpu']}")
        else:
            logger.warning(f"FFmpeg硬件加速不可用: {hwaccel_info['message']}, 将使用CPU软件编码")
        st.session_state['hwaccel_logged'] = True

    # 仅初始化基本资源，避免过早地加载依赖PyTorch的资源
    # 检查是否能分解utils.init_resources()为基本资源和高级资源(如依赖PyTorch的资源)
    try:
        utils.init_resources()
    except Exception as e:
        logger.warning(f"资源初始化时出现警告: {e}")

    st.title(f"Narrato:blue[AI]:sunglasses: 📽️")
    st.write(get_help_text())

    # 首先渲染不依赖PyTorch的UI部分
    # 渲染基础设置面板
    basic_settings.render_basic_settings(tr)

    # 渲染主面板
    panel = st.columns(3)
    with panel[0]:
        script_settings.render_script_panel(tr)
    with panel[1]:
        audio_settings.render_audio_panel(tr)
    with panel[2]:
        video_settings.render_video_panel(tr)
        subtitle_settings.render_subtitle_panel(tr)

    # 放到最后渲染可能使用PyTorch的部分
    # 渲染系统设置面板
    with panel[2]:
        system_settings.render_system_panel(tr)

    # 放到最后渲染生成按钮和处理逻辑
    render_generate_button()
    render_export_jianying_button()


if __name__ == "__main__":
    main()

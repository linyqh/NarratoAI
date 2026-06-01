import traceback

import streamlit as st
import os
from app.config import config
from app.config.defaults import (
    DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME,
    DEFAULT_DIRECT_VIDEO_PROVIDER,
    DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME,
    DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
    DEFAULT_OPENAI_COMPATIBLE_PROVIDER,
    DEFAULT_TEXT_LLM_PROVIDER,
    DEFAULT_TEXT_OPENAI_MODEL_NAME,
    DEFAULT_VIDEO_ANALYSIS_MODE,
    DEFAULT_VISION_LLM_PROVIDER,
    DEFAULT_VISION_OPENAI_MODEL_NAME,
    DIRECT_VIDEO_PROVIDER_GEMINI,
    DIRECT_VIDEO_PROVIDER_QWEN,
    get_openai_compatible_ui_values,
    normalize_openai_compatible_model_name as normalize_openai_compatible_model_id,
)



from app.utils import utils
from loguru import logger
from app.services.llm.unified_service import UnifiedLLMService

# 需要用户手动填写 Base URL 的 OpenAI 兼容网关及其默认接口
OPENAI_COMPATIBLE_GATEWAY_BASE_URLS = {
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "gemini(openai)": "",
}


def build_base_url_help(provider: str, model_type: str) -> tuple[str, bool, str]:
    """
    根据 provider 返回 Base URL 的帮助文案

    Returns:
        help_text: 显示在输入框的帮助内容
        requires_base: 是否强制提示必须填写 Base URL
        placeholder: 推荐的默认值（可为空字符串）
    """
    default_help = "自定义 API 端点（可选），当使用自建或第三方代理时需要填写"
    provider_key = (provider or "").lower()
    example_url = OPENAI_COMPATIBLE_GATEWAY_BASE_URLS.get(provider_key)

    if example_url is not None:
        extra = f"\n推荐接口地址: {example_url}" if example_url else ""
        help_text = (
            f"{model_type} 选择的提供商基于 OpenAI 兼容网关，必须填写完整的接口地址。"
            f"{extra}"
        )
        return help_text, True, example_url

    return default_help, False, ""


def validate_api_key(api_key: str, provider: str) -> tuple[bool, str]:
    """验证API密钥格式"""
    if not api_key or not api_key.strip():
        return False, f"{provider} API密钥不能为空"

    # 基本长度检查
    if len(api_key.strip()) < 10:
        return False, f"{provider} API密钥长度过短，请检查是否正确"

    return True, ""


def validate_base_url(base_url: str, provider: str) -> tuple[bool, str]:
    """验证Base URL格式"""
    if not base_url or not base_url.strip():
        return True, ""  # base_url可以为空

    base_url = base_url.strip()
    if not (base_url.startswith('http://') or base_url.startswith('https://')):
        return False, f"{provider} Base URL必须以http://或https://开头"

    return True, ""


def validate_model_name(model_name: str, provider: str) -> tuple[bool, str]:
    """验证模型名称"""
    if not model_name or not model_name.strip():
        return False, f"{provider} 模型名称不能为空"

    return True, ""


def validate_openai_compatible_model_name(model_name: str, model_type: str) -> tuple[bool, str]:
    """验证 OpenAI 兼容 模型名称格式
    
    Args:
        model_name: 模型名称，应为 provider/model 格式
        model_type: 模型类型（如"视频分析"、"文案生成"）
        
    Returns:
        (是否有效, 错误消息)
    """
    if not model_name or not model_name.strip():
        return False, f"{model_type} 模型名称不能为空"
    
    model_name = model_name.strip()
    
    # OpenAI 兼容 推荐格式：provider/model（如 gemini/gemini-2.0-flash-lite）
    # 但也支持直接的模型名称（如 gpt-4o，OpenAI 兼容 会自动推断 provider）
    
    # 检查是否包含 provider 前缀（推荐格式）
    if "/" in model_name:
        parts = model_name.split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return False, f"{model_type} 模型名称格式错误。推荐格式: provider/model （如 gemini/gemini-2.0-flash-lite）"
        
        # 验证 provider 名称（只允许字母、数字、下划线、连字符）
        provider = parts[0]
        if not provider.replace("-", "").replace("_", "").isalnum():
            return False, f"{model_type} Provider 名称只能包含字母、数字、下划线和连字符"
    else:
        # 直接模型名称也是有效的（OpenAI 兼容 会自动推断）
        # 但给出警告建议使用完整格式
        logger.debug(f"{model_type} 模型名称未包含 provider 前缀，OpenAI 兼容 将自动推断")
    
    # 基本长度检查
    if len(model_name) < 3:
        return False, f"{model_type} 模型名称过短"
    
    if len(model_name) > 200:
        return False, f"{model_type} 模型名称过长"
    
    return True, ""


def normalize_openai_compatible_model_name(model_name: str) -> str:
    """仅剥离误保存的 openai/ 前缀，保留完整模型名称。"""
    return normalize_openai_compatible_model_id(
        model_name,
        provider=DEFAULT_OPENAI_COMPATIBLE_PROVIDER,
    )


def show_config_validation_errors(errors: list):
    """显示配置验证错误"""
    if errors:
        for error in errors:
            st.error(error)


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
    # 获取当前代理状态
    proxy_enabled = config.proxy.get("enabled", False)
    proxy_url_http = config.proxy.get("http")
    proxy_url_https = config.proxy.get("https")

    # 添加代理开关
    proxy_enabled = st.checkbox(tr("Enable Proxy"), value=proxy_enabled)
    
    # 保存代理开关状态
    config.proxy["enabled"] = proxy_enabled

    # 只有在代理启用时才显示代理设置输入框
    if proxy_enabled:
        HTTP_PROXY = st.text_input(tr("HTTP_PROXY"), value=proxy_url_http)
        HTTPS_PROXY = st.text_input(tr("HTTPs_PROXY"), value=proxy_url_https)

        if HTTP_PROXY and HTTPS_PROXY:
            config.proxy["http"] = HTTP_PROXY
            config.proxy["https"] = HTTPS_PROXY
            os.environ["HTTP_PROXY"] = HTTP_PROXY
            os.environ["HTTPS_PROXY"] = HTTPS_PROXY
            # logger.debug(f"代理已启用: {HTTP_PROXY}")
    else:
        # 当代理被禁用时，清除环境变量和配置
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        config.proxy["http"] = ""
        config.proxy["https"] = ""

    # 剪映草稿地址设置
    st.subheader("剪映草稿设置")
    jianying_draft_path = st.text_input(
        "剪映草稿文件夹路径",
        value=config.ui.get("jianying_draft_path", ""),
        help="剪映草稿文件夹路径，例如：C:\\Users\\用户名\\Documents\\JianyingPro Drafts"
    )
    config.ui["jianying_draft_path"] = jianying_draft_path


def test_vision_model_connection(api_key, base_url, model_name, provider, tr):
    """测试视觉模型连接

    Args:
        api_key: API密钥
        base_url: 基础URL
        model_name: 模型名称
        provider: 提供商名称

    Returns:
        bool: 连接是否成功
        str: 测试结果消息
    """
    import requests
    logger.debug(f"大模型连通性测试: {base_url} 模型: {model_name} apikey: {api_key}")
    if provider.lower() == 'gemini':
        # 原生Gemini API测试
        try:
            # 构建请求数据
            request_data = {
                "contents": [{
                    "parts": [{"text": "直接回复我文本'当前网络可用'"}]
                }]
            }

            # 构建请求URL
            api_base_url = base_url
            url = f"{api_base_url}/models/{model_name}:generateContent"
            # 发送请求
            response = requests.post(
                url,
                json=request_data,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json"
                    },
                timeout=10
            )

            if response.status_code == 200:
                return True, tr("原生Gemini模型连接成功")
            else:
                return False, f"{tr('原生Gemini模型连接失败')}: HTTP {response.status_code}"
        except Exception as e:
            return False, f"{tr('原生Gemini模型连接失败')}: {str(e)}"
    elif provider.lower() == 'gemini(openai)':
        # OpenAI兼容的Gemini代理测试
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            test_url = f"{base_url.rstrip('/')}/chat/completions"
            test_data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "直接回复我文本'当前网络可用'"}
                ],
                "stream": False
            }

            response = requests.post(test_url, headers=headers, json=test_data, timeout=10)
            if response.status_code == 200:
                return True, tr("OpenAI兼容Gemini代理连接成功")
            else:
                return False, f"{tr('OpenAI兼容Gemini代理连接失败')}: HTTP {response.status_code}"
        except Exception as e:
            return False, f"{tr('OpenAI兼容Gemini代理连接失败')}: {str(e)}"
    else:
        from openai import OpenAI
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": "You are a helpful assistant."}],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"
                                },
                            },
                            {"type": "text", "text": "回复我网络可用即可"},
                        ],
                    },
                ],
            )
            if response and response.choices:
                return True, tr("QwenVL model is available")
            else:
                return False, tr("QwenVL model returned invalid response")

        except Exception as e:
            # logger.debug(api_key)
            # logger.debug(base_url)
            # logger.debug(model_name)
            return False, f"{tr('QwenVL model is not available')}: {str(e)}"




def test_openai_compatible_vision_model(api_key: str, base_url: str, model_name: str, tr) -> tuple[bool, str]:
    """测试 OpenAI 兼容视觉模型连接。"""
    try:
        import base64
        import io
        from openai import OpenAI
        from PIL import Image

        logger.debug(
            f"OpenAI 兼容视觉模型连通性测试: model={model_name}, api_key={api_key[:10]}..., base_url={base_url}"
        )

        client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=10.0,
            max_retries=1,
        )

        # 创建测试图片（64x64 白色像素）
        test_image = Image.new("RGB", (64, 64), color="white")
        img_buffer = io.BytesIO()
        test_image.save(img_buffer, format="JPEG")
        base64_image = base64.b64encode(img_buffer.getvalue()).decode("utf-8")

        response = client.chat.completions.create(
            model=normalize_openai_compatible_model_name(model_name),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请直接回复'连接成功'"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=50,
        )

        if response and response.choices and len(response.choices) > 0:
            return True, f"OpenAI 兼容视觉模型连接成功 ({model_name})"
        return False, "OpenAI 兼容视觉模型返回空响应"
    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI 兼容视觉模型测试失败: {error_msg}")
        if "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return False, "认证失败，请检查 API Key 是否正确"
        if "not found" in error_msg.lower() or "404" in error_msg:
            return False, "模型不存在，请检查模型名称是否正确"
        if "rate limit" in error_msg.lower():
            return False, "超出速率限制，请稍后重试"
        return False, f"连接失败: {error_msg}"


def test_openai_compatible_text_model(api_key: str, base_url: str, model_name: str, tr) -> tuple[bool, str]:
    """测试 OpenAI 兼容文本模型连接。"""
    try:
        from openai import OpenAI

        logger.debug(
            f"OpenAI 兼容文本模型连通性测试: model={model_name}, api_key={api_key[:10]}..., base_url={base_url}"
        )

        client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=10.0,
            max_retries=1,
        )

        response = client.chat.completions.create(
            model=normalize_openai_compatible_model_name(model_name),
            messages=[{"role": "user", "content": "请直接回复'连接成功'"}],
            temperature=0.1,
            max_tokens=20,
        )

        if response and response.choices and len(response.choices) > 0:
            return True, f"OpenAI 兼容文本模型连接成功 ({model_name})"
        return False, "OpenAI 兼容文本模型返回空响应"
    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI 兼容文本模型测试失败: {error_msg}")
        if "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return False, "认证失败，请检查 API Key 是否正确"
        if "not found" in error_msg.lower() or "404" in error_msg:
            return False, "模型不存在，请检查模型名称是否正确"
        if "rate limit" in error_msg.lower():
            return False, "超出速率限制，请稍后重试"
        return False, f"连接失败: {error_msg}"

def _render_video_analysis_mode_switch(tr) -> str:
    """渲染影片分析模式开关，返回当前选中的模式（frames / direct）。"""
    current_mode = config.app.get("video_analysis_mode") or DEFAULT_VIDEO_ANALYSIS_MODE
    if current_mode not in ("frames", "direct"):
        current_mode = DEFAULT_VIDEO_ANALYSIS_MODE

    mode_options = {
        tr("Frame Extraction Mode"): "frames",
        tr("Direct Upload Mode"): "direct",
    }
    label_keys = list(mode_options.keys())
    current_label = next((label for label, value in mode_options.items() if value == current_mode), label_keys[0])

    selected_label = st.radio(
        tr("Video Analysis Mode"),
        options=label_keys,
        index=label_keys.index(current_label),
        horizontal=True,
        help=tr(
            "Frame mode extracts keyframes locally and analyzes them in batches. "
            "Direct mode uploads the entire video file to Gemini for one-shot analysis."
        ),
        key="video_analysis_mode_radio",
    )

    selected_mode = mode_options[selected_label]
    if selected_mode != current_mode:
        config.app["video_analysis_mode"] = selected_mode
        try:
            config.save_config()
        except Exception as exc:
            logger.error(f"保存影片分析模式失败: {exc}")
    else:
        config.app["video_analysis_mode"] = selected_mode

    st.session_state["video_analysis_mode"] = selected_mode
    return selected_mode


def _render_direct_video_provider_switch(tr) -> str:
    """渲染「直接上传分析」的 provider 切换（gemini / qwen），返回当前选中的 provider。"""
    current_provider = (
        config.app.get("direct_video_provider") or DEFAULT_DIRECT_VIDEO_PROVIDER
    ).lower()
    if current_provider not in (DIRECT_VIDEO_PROVIDER_GEMINI, DIRECT_VIDEO_PROVIDER_QWEN):
        current_provider = DEFAULT_DIRECT_VIDEO_PROVIDER

    provider_options = {
        f"Gemini ({tr('Official')})": DIRECT_VIDEO_PROVIDER_GEMINI,
        f"Qwen-VL ({tr('Official')})": DIRECT_VIDEO_PROVIDER_QWEN,
    }
    label_keys = list(provider_options.keys())
    current_label = next(
        (label for label, value in provider_options.items() if value == current_provider),
        label_keys[0],
    )

    selected_label = st.radio(
        tr("Direct Video Provider"),
        options=label_keys,
        index=label_keys.index(current_label),
        horizontal=True,
        help=tr(
            "Choose the official API used to analyze the uploaded video. "
            "Gemini uploads the file via Files API. Qwen-VL uses DashScope multimodal conversation."
        ),
        key="direct_video_provider_radio",
    )

    selected_provider = provider_options[selected_label]
    if selected_provider != current_provider:
        config.app["direct_video_provider"] = selected_provider
        try:
            config.save_config()
        except Exception as exc:
            logger.error(f"保存 direct_video_provider 失败: {exc}")
    else:
        config.app["direct_video_provider"] = selected_provider

    st.session_state["direct_video_provider"] = selected_provider
    return selected_provider


def _render_gemini_direct_video_settings(tr) -> None:
    """渲染 Gemini 官方原生 API 的配置面板。"""
    api_key = config.app.get("direct_video_gemini_api_key", "")
    model_name = config.app.get("direct_video_gemini_model_name") or DEFAULT_DIRECT_VIDEO_GEMINI_MODEL_NAME

    st.info(
        tr(
            "Gemini mode uploads the whole video to Google's Files API and lets the model "
            "analyze it in one shot. Make sure the network can reach Google APIs."
        )
    )

    st_model = st.text_input(
        tr("Gemini Video Model Name"),
        value=model_name,
        help="支持视频理解的 Gemini 模型，例如：gemini-2.0-flash-exp、gemini-1.5-pro",
        key="direct_video_gemini_model_input",
    )
    st_api_key = st.text_input(
        tr("Gemini Video API Key"),
        value=api_key,
        type="password",
        help="Gemini API Key 获取地址：https://makersuite.google.com/app/apikey",
        key="direct_video_gemini_api_key_input",
    )

    if st.button(tr("Test Connection"), key="test_direct_video_gemini_connection"):
        if not st_api_key:
            st.error(tr("Please enter Gemini API Key first"))
        elif not st_model:
            st.error(tr("Please enter Gemini model name first"))
        else:
            with st.spinner(tr("Testing connection...")):
                ok, message = _test_gemini_native(api_key=st_api_key, model_name=st_model)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    config_changed = False
    if st_model and st_model.strip() != (model_name or "").strip():
        config.app["direct_video_gemini_model_name"] = st_model.strip()
        config_changed = True
    if st_api_key and st_api_key != api_key:
        is_valid, error_msg = validate_api_key(st_api_key, "Gemini 视频分析")
        if is_valid:
            config.app["direct_video_gemini_api_key"] = st_api_key
            config_changed = True
        else:
            st.error(error_msg)

    if config_changed:
        try:
            config.save_config()
            st.success(tr("Direct video analysis settings saved"))
        except Exception as exc:
            st.error(f"保存配置失败: {exc}")
            logger.error(f"保存 Gemini 直接视频分析配置失败: {exc}")


def _render_qwen_direct_video_settings(tr) -> None:
    """渲染 Qwen-VL（DashScope）官方 API 的配置面板。"""
    api_key = config.app.get("direct_video_qwen_api_key", "")
    model_name = config.app.get("direct_video_qwen_model_name") or DEFAULT_DIRECT_VIDEO_QWEN_MODEL_NAME

    st.info(
        tr(
            "Qwen-VL mode uses DashScope multimodal conversation to send the local video file "
            "to Tongyi Qwen-VL. Make sure the local file path is reachable for the SDK."
        )
    )

    st_model = st.text_input(
        tr("Qwen-VL Video Model Name"),
        value=model_name,
        help="支持视频理解的通义 Qwen-VL 模型，例如：qwen-vl-max-latest、qwen-vl-plus、qwen2.5-vl-72b-instruct",
        key="direct_video_qwen_model_input",
    )
    st_api_key = st.text_input(
        tr("Qwen-VL Video API Key"),
        value=api_key,
        type="password",
        help="阿里百炼 / DashScope API Key 获取地址：https://bailian.console.aliyun.com/?tab=model#/api-key",
        key="direct_video_qwen_api_key_input",
    )

    if st.button(tr("Test Connection"), key="test_direct_video_qwen_connection"):
        if not st_api_key:
            st.error(tr("Please enter Qwen API Key first"))
        elif not st_model:
            st.error(tr("Please enter Qwen model name first"))
        else:
            with st.spinner(tr("Testing connection...")):
                ok, message = _test_qwen_native(api_key=st_api_key, model_name=st_model)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    config_changed = False
    if st_model and st_model.strip() != (model_name or "").strip():
        config.app["direct_video_qwen_model_name"] = st_model.strip()
        config_changed = True
    if st_api_key and st_api_key != api_key:
        is_valid, error_msg = validate_api_key(st_api_key, "Qwen 视频分析")
        if is_valid:
            config.app["direct_video_qwen_api_key"] = st_api_key
            config_changed = True
        else:
            st.error(error_msg)

    if config_changed:
        try:
            config.save_config()
            st.success(tr("Direct video analysis settings saved"))
        except Exception as exc:
            st.error(f"保存配置失败: {exc}")
            logger.error(f"保存 Qwen 直接视频分析配置失败: {exc}")


def render_direct_video_analysis_settings(tr):
    """渲染「直接上传分析」的官方 API 配置（Gemini / Qwen-VL 二选一）。"""
    selected_provider = _render_direct_video_provider_switch(tr)
    if selected_provider == DIRECT_VIDEO_PROVIDER_GEMINI:
        _render_gemini_direct_video_settings(tr)
    else:
        _render_qwen_direct_video_settings(tr)


def _test_gemini_native(api_key: str, model_name: str) -> tuple[bool, str]:
    """用 Gemini 新版官方 SDK（google-genai）做一次轻量文本调用以验证 API Key/模型可用。"""
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        return False, "未安装 google-genai，请执行：pip install google-genai"

    try:
        client = google_genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents="请直接回复'连接成功'",
            config=genai_types.GenerateContentConfig(temperature=0.1),
        )
        text = (getattr(response, "text", "") or "").strip()
        if text:
            return True, f"Gemini 视频模型连接成功（{model_name}）"
        return False, "Gemini 返回空响应"
    except Exception as exc:
        msg = str(exc)
        logger.error(f"Gemini 视频模型测试失败: {msg}")
        if "api key" in msg.lower() or "permission" in msg.lower() or "invalid" in msg.lower():
            return False, "认证失败，请检查 API Key 是否正确"
        if "not found" in msg.lower() or "404" in msg:
            return False, "模型不存在，请检查模型名称"
        return False, f"连接失败: {msg}"



def _test_qwen_native(api_key: str, model_name: str) -> tuple[bool, str]:
    """用 DashScope MultiModalConversation 做一次纯文本调用验证 API Key/模型可用。"""
    try:
        from dashscope import MultiModalConversation
    except ImportError:
        return False, "未安装 dashscope，请确认依赖完整"

    try:
        response = MultiModalConversation.call(
            api_key=api_key,
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "请直接回复'连接成功'"}],
                }
            ],
        )
        status_code = getattr(response, "status_code", None)
        if status_code is not None and status_code != 200:
            err_code = getattr(response, "code", "")
            err_msg = getattr(response, "message", "")
            return False, f"Qwen-VL 调用失败 (status={status_code}, code={err_code}): {err_msg}"
        return True, f"Qwen-VL 模型连接成功（{model_name}）"
    except Exception as exc:
        msg = str(exc)
        logger.error(f"Qwen-VL 模型测试失败: {msg}")
        if "api key" in msg.lower() or "auth" in msg.lower() or "invalid" in msg.lower():
            return False, "认证失败，请检查 API Key 是否正确"
        if "model" in msg.lower() and ("not" in msg.lower() or "404" in msg):
            return False, "模型不存在，请检查模型名称"
        return False, f"连接失败: {msg}"




def render_vision_llm_settings(tr):
    """渲染视频分析模型设置（支持「抽帧分析」与「直接上传分析」两种模式）"""
    st.subheader(tr("Vision Model Settings"))

    # 影片分析模式开关
    selected_mode = _render_video_analysis_mode_switch(tr)

    # 直接上传模式：渲染 Gemini File API 配置后直接返回
    if selected_mode == "direct":
        render_direct_video_analysis_settings(tr)
        return

    # 抽帧模式：维持原有 OpenAI 兼容配置
    # 固定使用 OpenAI 兼容 提供商
    config.app["vision_llm_provider"] = DEFAULT_VISION_LLM_PROVIDER


    # 获取已保存的配置
    full_vision_model_name = config.app.get("vision_openai_model_name") or DEFAULT_VISION_OPENAI_MODEL_NAME
    vision_api_key = config.app.get("vision_openai_api_key", "")
    vision_base_url = config.app.get("vision_openai_base_url", DEFAULT_OPENAI_COMPATIBLE_BASE_URL)
    
    # 固定 provider 为 openai，模型输入框保留完整模型名称
    current_provider, current_model = get_openai_compatible_ui_values(
        full_vision_model_name,
        DEFAULT_VISION_OPENAI_MODEL_NAME,
        provider=DEFAULT_VISION_LLM_PROVIDER,
    )

    # 定义支持的 provider 列表
    OPENAI_COMPATIBLE_PROVIDERS = ["openai"]

    # 渲染配置输入框
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_provider = st.selectbox(
            tr("Vision Model Provider"),
            options=OPENAI_COMPATIBLE_PROVIDERS,
            index=OPENAI_COMPATIBLE_PROVIDERS.index(current_provider) if current_provider in OPENAI_COMPATIBLE_PROVIDERS else 0,
            key="vision_provider_select"
        )
    
    with col2:
        model_name_input = st.text_input(
            tr("Vision Model Name"),
            value=current_model,
            help="输入完整模型名称\n\n"
                 "常用示例:\n"
                 "• Qwen/Qwen3.5-122B-A10B\n"
                 "• gemini/gemini-2.0-flash-lite\n"
                 "• gpt-4o\n"
                 "• Qwen/Qwen2.5-VL-32B-Instruct (SiliconFlow)\n\n"
                 "支持常见 OpenAI 兼容网关（如 OpenAI/DeepSeek/OpenRouter/SiliconFlow）",
            key="vision_model_input"
        )

    # 组合完整的模型名称
    st_vision_model_name = normalize_openai_compatible_model_name(model_name_input)

    st_vision_api_key = st.text_input(
        tr("Vision API Key"),
        value=vision_api_key,
        type="password",
        help="对应 provider 的 API 密钥\n\n"
             "获取地址:\n"
             "• Gemini: https://makersuite.google.com/app/apikey\n"
             "• OpenAI: https://platform.openai.com/api-keys\n"
             "• Qwen: https://bailian.console.aliyun.com/\n"
             "• SiliconFlow: https://cloud.siliconflow.cn/account/ak"
    )

    vision_base_help, vision_base_required, vision_placeholder = build_base_url_help(
        selected_provider, "视频分析模型"
    )
    st_vision_base_url = st.text_input(
        tr("Vision Base URL"),
        value=vision_base_url,
        help=vision_base_help,
        placeholder=vision_placeholder or None
    )
    if vision_base_required and not st_vision_base_url:
        info_example = vision_placeholder or "https://your-openai-compatible-endpoint/v1"
        st.info(f"请在上方填写 OpenAI 兼容网关地址，例如：{info_example}")

    # 添加测试连接按钮
    if st.button(tr("Test Connection"), key="test_vision_connection"):
        test_errors = []
        if not st_vision_api_key:
            test_errors.append("请先输入 API 密钥")
        if not model_name_input:
            test_errors.append("请先输入模型名称")

        if test_errors:
            for error in test_errors:
                st.error(error)
        else:
            with st.spinner(tr("Testing connection...")):
                try:
                    success, message = test_openai_compatible_vision_model(
                        api_key=st_vision_api_key,
                        base_url=st_vision_base_url,
                        model_name=st_vision_model_name,
                        tr=tr
                    )

                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                except Exception as e:
                    st.error(f"测试连接时发生错误: {str(e)}")
                    logger.error(f"OpenAI 兼容 视频分析模型连接测试失败: {str(e)}")

    # 验证和保存配置
    validation_errors = []
    config_changed = False

    # 验证模型名称
    if st_vision_model_name:
        # 这里的验证逻辑可能需要微调，因为我们现在是自动组合的
        is_valid, error_msg = validate_openai_compatible_model_name(st_vision_model_name, "视频分析")
        if is_valid:
            config.app["vision_openai_model_name"] = st_vision_model_name
            st.session_state["vision_openai_model_name"] = st_vision_model_name
            config_changed = True
        else:
            validation_errors.append(error_msg)

    # 验证 API 密钥
    if st_vision_api_key:
        is_valid, error_msg = validate_api_key(st_vision_api_key, "视频分析")
        if is_valid:
            config.app["vision_openai_api_key"] = st_vision_api_key
            st.session_state["vision_openai_api_key"] = st_vision_api_key
            config_changed = True
        else:
            validation_errors.append(error_msg)

    # 验证 Base URL（可选）
    if st_vision_base_url:
        is_valid, error_msg = validate_base_url(st_vision_base_url, "视频分析")
        if is_valid:
            config.app["vision_openai_base_url"] = st_vision_base_url
            st.session_state["vision_openai_base_url"] = st_vision_base_url
            config_changed = True
        else:
            validation_errors.append(error_msg)

    # 显示验证错误
    show_config_validation_errors(validation_errors)

    # 保存配置
    if config_changed and not validation_errors:
        try:
            config.save_config()
            # 清除缓存，确保下次使用新配置
            UnifiedLLMService.clear_cache()
            if st_vision_api_key or st_vision_base_url or st_vision_model_name:
                st.success(f"视频分析模型配置已保存（OpenAI 兼容）")
        except Exception as e:
            st.error(f"保存配置失败: {str(e)}")
            logger.error(f"保存视频分析配置失败: {str(e)}")


def test_text_model_connection(api_key, base_url, model_name, provider, tr):
    """测试文本模型连接
    
    Args:
        api_key: API密钥
        base_url: 基础URL
        model_name: 模型名称
        provider: 提供商名称
    
    Returns:
        bool: 连接是否成功
        str: 测试结果消息
    """
    import requests
    logger.debug(f"大模型连通性测试: {base_url} 模型: {model_name} apikey: {api_key}")

    try:
        # 构建统一的测试请求（遵循OpenAI格式）
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 特殊处理Gemini
        if provider.lower() == 'gemini':
            # 原生Gemini API测试
            try:
                # 构建请求数据
                request_data = {
                    "contents": [{
                        "parts": [{"text": "直接回复我文本'当前网络可用'"}]
                    }]
                }

                # 构建请求URL
                api_base_url = base_url
                url = f"{api_base_url}/models/{model_name}:generateContent"

                # 发送请求
                response = requests.post(
                    url,
                    json=request_data,
                    headers={
                        "x-goog-api-key": api_key,
                        "Content-Type": "application/json"
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    return True, tr("原生Gemini模型连接成功")
                else:
                    return False, f"{tr('原生Gemini模型连接失败')}: HTTP {response.status_code}"
            except Exception as e:
                return False, f"{tr('原生Gemini模型连接失败')}: {str(e)}"

        elif provider.lower() == 'gemini(openai)':
            # OpenAI兼容的Gemini代理测试
            test_url = f"{base_url.rstrip('/')}/chat/completions"
            test_data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "直接回复我文本'当前网络可用'"}
                ],
                "stream": False
            }

            response = requests.post(test_url, headers=headers, json=test_data, timeout=10)
            if response.status_code == 200:
                return True, tr("OpenAI兼容Gemini代理连接成功")
            else:
                return False, f"{tr('OpenAI兼容Gemini代理连接失败')}: HTTP {response.status_code}"
        else:
            test_url = f"{base_url.rstrip('/')}/chat/completions"

            # 构建测试消息
            test_data = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "直接回复我文本'当前网络可用'"}
                ],
                "stream": False
            }

            # 发送测试请求
            response = requests.post(
                test_url,
                headers=headers,
                json=test_data,
            )
            # logger.debug(model_name)
            # logger.debug(api_key)
            # logger.debug(test_url)
            if response.status_code == 200:
                return True, tr("Text model is available")
            else:
                return False, f"{tr('Text model is not available')}: HTTP {response.status_code}"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"{tr('Connection failed')}: {str(e)}"


def render_text_llm_settings(tr):
    """渲染文案生成模型设置（OpenAI 兼容 统一配置）"""
    st.subheader(tr("Text Generation Model Settings"))

    # 固定使用 OpenAI 兼容 提供商
    config.app["text_llm_provider"] = DEFAULT_TEXT_LLM_PROVIDER

    # 获取已保存的配置
    full_text_model_name = config.app.get("text_openai_model_name") or DEFAULT_TEXT_OPENAI_MODEL_NAME
    text_api_key = config.app.get("text_openai_api_key", "")
    text_base_url = config.app.get("text_openai_base_url", DEFAULT_OPENAI_COMPATIBLE_BASE_URL)

    # 固定 provider 为 openai，模型输入框保留完整模型名称
    current_provider, current_model = get_openai_compatible_ui_values(
        full_text_model_name,
        DEFAULT_TEXT_OPENAI_MODEL_NAME,
        provider=DEFAULT_TEXT_LLM_PROVIDER,
    )

    # 定义支持的 provider 列表
    OPENAI_COMPATIBLE_PROVIDERS = ["openai"]

    # 渲染配置输入框
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_provider = st.selectbox(
            tr("Text Model Provider"),
            options=OPENAI_COMPATIBLE_PROVIDERS,
            index=OPENAI_COMPATIBLE_PROVIDERS.index(current_provider) if current_provider in OPENAI_COMPATIBLE_PROVIDERS else 0,
            key="text_provider_select"
        )
    
    with col2:
        model_name_input = st.text_input(
            tr("Text Model Name"),
            value=current_model,
            help="输入完整模型名称\n\n"
                 "常用示例:\n"
                 "• Pro/zai-org/GLM-5\n"
                 "• deepseek/deepseek-chat\n"
                 "• gpt-4o\n"
                 "• deepseek-ai/DeepSeek-R1 (SiliconFlow)\n\n"
                 "支持常见 OpenAI 兼容网关（如 OpenAI/DeepSeek/OpenRouter/SiliconFlow）",
            key="text_model_input"
        )

    # 组合完整的模型名称
    st_text_model_name = normalize_openai_compatible_model_name(model_name_input)

    st_text_api_key = st.text_input(
        tr("Text API Key"),
        value=text_api_key,
        type="password",
        help="对应 provider 的 API 密钥\n\n"
             "获取地址:\n"
             "• DeepSeek: https://platform.deepseek.com/api_keys\n"
             "• Gemini: https://makersuite.google.com/app/apikey\n"
             "• OpenAI: https://platform.openai.com/api-keys\n"
             "• Qwen: https://bailian.console.aliyun.com/\n"
             "• SiliconFlow: https://cloud.siliconflow.cn/account/ak\n"
             "• Moonshot: https://platform.moonshot.cn/console/api-keys"
    )

    text_base_help, text_base_required, text_placeholder = build_base_url_help(
        selected_provider, "文案生成模型"
    )
    st_text_base_url = st.text_input(
        tr("Text Base URL"),
        value=text_base_url,
        help=text_base_help,
        placeholder=text_placeholder or None
    )
    if text_base_required and not st_text_base_url:
        info_example = text_placeholder or "https://your-openai-compatible-endpoint/v1"
        st.info(f"请在上方填写 OpenAI 兼容网关地址，例如：{info_example}")

    # 添加测试连接按钮
    if st.button(tr("Test Connection"), key="test_text_connection"):
        test_errors = []
        if not st_text_api_key:
            test_errors.append("请先输入 API 密钥")
        if not model_name_input:
            test_errors.append("请先输入模型名称")

        if test_errors:
            for error in test_errors:
                st.error(error)
        else:
            with st.spinner(tr("Testing connection...")):
                try:
                    success, message = test_openai_compatible_text_model(
                        api_key=st_text_api_key,
                        base_url=st_text_base_url,
                        model_name=st_text_model_name,
                        tr=tr
                    )

                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                except Exception as e:
                    st.error(f"测试连接时发生错误: {str(e)}")
                    logger.error(f"OpenAI 兼容 文案生成模型连接测试失败: {str(e)}")

    # 验证和保存配置
    text_validation_errors = []
    text_config_changed = False

    # 验证模型名称
    if st_text_model_name:
        is_valid, error_msg = validate_openai_compatible_model_name(st_text_model_name, "文案生成")
        if is_valid:
            config.app["text_openai_model_name"] = st_text_model_name
            st.session_state["text_openai_model_name"] = st_text_model_name
            text_config_changed = True
        else:
            text_validation_errors.append(error_msg)

    # 验证 API 密钥
    if st_text_api_key:
        is_valid, error_msg = validate_api_key(st_text_api_key, "文案生成")
        if is_valid:
            config.app["text_openai_api_key"] = st_text_api_key
            st.session_state["text_openai_api_key"] = st_text_api_key
            text_config_changed = True
        else:
            text_validation_errors.append(error_msg)

    # 验证 Base URL（可选）
    if st_text_base_url:
        is_valid, error_msg = validate_base_url(st_text_base_url, "文案生成")
        if is_valid:
            config.app["text_openai_base_url"] = st_text_base_url
            st.session_state["text_openai_base_url"] = st_text_base_url
            text_config_changed = True
        else:
            text_validation_errors.append(error_msg)

    # 显示验证错误
    show_config_validation_errors(text_validation_errors)

    # 保存配置
    if text_config_changed and not text_validation_errors:
        try:
            config.save_config()
            # 清除缓存，确保下次使用新配置
            UnifiedLLMService.clear_cache()
            if st_text_api_key or st_text_base_url or st_text_model_name:
                st.success(f"文案生成模型配置已保存（OpenAI 兼容）")
        except Exception as e:
            st.error(f"保存配置失败: {str(e)}")
            logger.error(f"保存文案生成配置失败: {str(e)}")

    # # Cloudflare 特殊配置
    # if text_provider == 'cloudflare':
    #     st_account_id = st.text_input(
    #         tr("Account ID"),
    #         value=config.app.get(f"text_{text_provider}_account_id", "")
    #     )
    #     if st_account_id:
    #         config.app[f"text_{text_provider}_account_id"] = st_account_id

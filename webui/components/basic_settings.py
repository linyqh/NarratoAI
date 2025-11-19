import traceback

import streamlit as st
import os
from app.config import config
from app.utils import utils
from loguru import logger
from app.services.llm.unified_service import UnifiedLLMService


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


def validate_litellm_model_name(model_name: str, model_type: str) -> tuple[bool, str]:
    """验证 LiteLLM 模型名称格式
    
    Args:
        model_name: 模型名称，应为 provider/model 格式
        model_type: 模型类型（如"视频分析"、"文案生成"）
        
    Returns:
        (是否有效, 错误消息)
    """
    if not model_name or not model_name.strip():
        return False, f"{model_type} 模型名称不能为空"
    
    model_name = model_name.strip()
    
    # LiteLLM 推荐格式：provider/model（如 gemini/gemini-2.0-flash-lite）
    # 但也支持直接的模型名称（如 gpt-4o，LiteLLM 会自动推断 provider）
    
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
        # 直接模型名称也是有效的（LiteLLM 会自动推断）
        # 但给出警告建议使用完整格式
        logger.debug(f"{model_type} 模型名称未包含 provider 前缀，LiteLLM 将自动推断")
    
    # 基本长度检查
    if len(model_name) < 3:
        return False, f"{model_type} 模型名称过短"
    
    if len(model_name) > 200:
        return False, f"{model_type} 模型名称过长"
    
    return True, ""


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
    # config.proxy["enabled"] = proxy_enabled

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
        # config.proxy["http"] = ""
        # config.proxy["https"] = ""


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




def test_litellm_vision_model(api_key: str, base_url: str, model_name: str, tr) -> tuple[bool, str]:
    """测试 LiteLLM 视觉模型连接
    
    Args:
        api_key: API 密钥
        base_url: 基础 URL（可选）
        model_name: 模型名称（LiteLLM 格式：provider/model）
        tr: 翻译函数
        
    Returns:
        (连接是否成功, 测试结果消息)
    """
    try:
        import litellm
        import os
        import base64
        import io
        from PIL import Image
        
        logger.debug(f"LiteLLM 视觉模型连通性测试: model={model_name}, api_key={api_key[:10]}..., base_url={base_url}")
        
        # 提取 provider 名称
        provider = model_name.split("/")[0] if "/" in model_name else "unknown"
        
        # 设置 API key 到环境变量
        env_key_mapping = {
            "gemini": "GEMINI_API_KEY",
            "google": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "qwen": "QWEN_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
        }
        env_var = env_key_mapping.get(provider.lower(), f"{provider.upper()}_API_KEY")
        old_key = os.environ.get(env_var)
        os.environ[env_var] = api_key
        
        # SiliconFlow 特殊处理：使用 OpenAI 兼容模式
        test_model_name = model_name
        if provider.lower() == "siliconflow":
            # 替换 provider 为 openai
            if "/" in model_name:
                test_model_name = f"openai/{model_name.split('/', 1)[1]}"
            else:
                test_model_name = f"openai/{model_name}"
            
            # 确保设置了 base_url
            if not base_url:
                base_url = "https://api.siliconflow.cn/v1"
            
            # 设置 OPENAI_API_KEY (SiliconFlow 使用 OpenAI 协议)
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_API_BASE"] = base_url
        
        try:
            # 创建测试图片（64x64 白色像素，避免某些模型对极小图片的限制）
            test_image = Image.new('RGB', (64, 64), color='white')
            img_buffer = io.BytesIO()
            test_image.save(img_buffer, format='JPEG')
            img_bytes = img_buffer.getvalue()
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            
            # 构建测试请求
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "请直接回复'连接成功'"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }]
            
            # 准备参数
            completion_kwargs = {
                "model": test_model_name,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 50
            }
            
            if base_url:
                completion_kwargs["api_base"] = base_url
            
            # 调用 LiteLLM（同步调用用于测试）
            response = litellm.completion(**completion_kwargs)
            
            if response and response.choices and len(response.choices) > 0:
                return True, f"LiteLLM 视觉模型连接成功 ({model_name})"
            else:
                return False, f"LiteLLM 视觉模型返回空响应"
                
        finally:
            # 恢复原始环境变量
            if old_key:
                os.environ[env_var] = old_key
            else:
                os.environ.pop(env_var, None)
            
            # 清理临时设置的 OpenAI 环境变量
            if provider.lower() == "siliconflow":
                 os.environ.pop("OPENAI_API_KEY", None)
                 os.environ.pop("OPENAI_API_BASE", None)
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"LiteLLM 视觉模型测试失败: {error_msg}")
        
        # 提供更友好的错误信息
        if "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return False, f"认证失败，请检查 API Key 是否正确"
        elif "not found" in error_msg.lower() or "404" in error_msg:
            return False, f"模型不存在，请检查模型名称是否正确"
        elif "rate limit" in error_msg.lower():
            return False, f"超出速率限制，请稍后重试"
        else:
            return False, f"连接失败: {error_msg}"


def test_litellm_text_model(api_key: str, base_url: str, model_name: str, tr) -> tuple[bool, str]:
    """测试 LiteLLM 文本模型连接
    
    Args:
        api_key: API 密钥
        base_url: 基础 URL（可选）
        model_name: 模型名称（LiteLLM 格式：provider/model）
        tr: 翻译函数
        
    Returns:
        (连接是否成功, 测试结果消息)
    """
    try:
        import litellm
        import os
        
        logger.debug(f"LiteLLM 文本模型连通性测试: model={model_name}, api_key={api_key[:10]}..., base_url={base_url}")
        
        # 提取 provider 名称
        provider = model_name.split("/")[0] if "/" in model_name else "unknown"
        
        # 设置 API key 到环境变量
        env_key_mapping = {
            "gemini": "GEMINI_API_KEY",
            "google": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "qwen": "QWEN_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "siliconflow": "SILICONFLOW_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
        }
        env_var = env_key_mapping.get(provider.lower(), f"{provider.upper()}_API_KEY")
        old_key = os.environ.get(env_var)
        os.environ[env_var] = api_key
        
        # SiliconFlow 特殊处理：使用 OpenAI 兼容模式
        test_model_name = model_name
        if provider.lower() == "siliconflow":
            # 替换 provider 为 openai
            if "/" in model_name:
                test_model_name = f"openai/{model_name.split('/', 1)[1]}"
            else:
                test_model_name = f"openai/{model_name}"
            
            # 确保设置了 base_url
            if not base_url:
                base_url = "https://api.siliconflow.cn/v1"
            
            # 设置 OPENAI_API_KEY (SiliconFlow 使用 OpenAI 协议)
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_API_BASE"] = base_url
        
        try:
            # 构建测试请求
            messages = [
                {"role": "user", "content": "请直接回复'连接成功'"}
            ]
            
            # 准备参数
            completion_kwargs = {
                "model": test_model_name,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 20
            }
            
            if base_url:
                completion_kwargs["api_base"] = base_url
            
            # 调用 LiteLLM（同步调用用于测试）
            response = litellm.completion(**completion_kwargs)
            
            if response and response.choices and len(response.choices) > 0:
                return True, f"LiteLLM 文本模型连接成功 ({model_name})"
            else:
                return False, f"LiteLLM 文本模型返回空响应"
                
        finally:
            # 恢复原始环境变量
            if old_key:
                os.environ[env_var] = old_key
            else:
                os.environ.pop(env_var, None)
            
            # 清理临时设置的 OpenAI 环境变量
            if provider.lower() == "siliconflow":
                 os.environ.pop("OPENAI_API_KEY", None)
                 os.environ.pop("OPENAI_API_BASE", None)
                
    except Exception as e:
        error_msg = str(e)
        logger.error(f"LiteLLM 文本模型测试失败: {error_msg}")
        
        # 提供更友好的错误信息
        if "authentication" in error_msg.lower() or "api_key" in error_msg.lower():
            return False, f"认证失败，请检查 API Key 是否正确"
        elif "not found" in error_msg.lower() or "404" in error_msg:
            return False, f"模型不存在，请检查模型名称是否正确"
        elif "rate limit" in error_msg.lower():
            return False, f"超出速率限制，请稍后重试"
        else:
            return False, f"连接失败: {error_msg}"

def render_vision_llm_settings(tr):
    """渲染视频分析模型设置（LiteLLM 统一配置）"""
    st.subheader(tr("Vision Model Settings"))

    # 固定使用 LiteLLM 提供商
    config.app["vision_llm_provider"] = "litellm"

    # 获取已保存的 LiteLLM 配置
    full_vision_model_name = config.app.get("vision_litellm_model_name", "gemini/gemini-2.0-flash-lite")
    vision_api_key = config.app.get("vision_litellm_api_key", "")
    vision_base_url = config.app.get("vision_litellm_base_url", "")

    # 解析 provider 和 model
    default_provider = "gemini"
    default_model = "gemini-2.0-flash-lite"
    
    if "/" in full_vision_model_name:
        parts = full_vision_model_name.split("/", 1)
        current_provider = parts[0]
        current_model = parts[1]
    else:
        current_provider = default_provider
        current_model = full_vision_model_name

    # 定义支持的 provider 列表
    LITELLM_PROVIDERS = [
        "openai", "gemini", "deepseek", "qwen", "siliconflow", "moonshot", 
        "anthropic", "azure", "ollama", "vertex_ai", "mistral", "codestral", 
        "volcengine", "groq", "cohere", "together_ai", "fireworks_ai", 
        "openrouter", "replicate", "huggingface", "xai", "deepgram", "vllm", 
        "bedrock", "cloudflare"
    ]
    
    # 如果当前 provider 不在列表中，添加到列表头部
    if current_provider not in LITELLM_PROVIDERS:
        LITELLM_PROVIDERS.insert(0, current_provider)

    # 渲染配置输入框
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_provider = st.selectbox(
            tr("Vision Model Provider"),
            options=LITELLM_PROVIDERS,
            index=LITELLM_PROVIDERS.index(current_provider) if current_provider in LITELLM_PROVIDERS else 0,
            key="vision_provider_select"
        )
    
    with col2:
        model_name_input = st.text_input(
            tr("Vision Model Name"),
            value=current_model,
            help="输入模型名称（不包含 provider 前缀）\n\n"
                 "常用示例:\n"
                 "• gemini-2.0-flash-lite\n"
                 "• gpt-4o\n"
                 "• qwen-vl-max\n"
                 "• Qwen/Qwen2.5-VL-32B-Instruct (SiliconFlow)\n\n"
                 "支持 100+ providers，详见: https://docs.litellm.ai/docs/providers",
            key="vision_model_input"
        )

    # 组合完整的模型名称
    st_vision_model_name = f"{selected_provider}/{model_name_input}" if selected_provider and model_name_input else ""

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

    st_vision_base_url = st.text_input(
        tr("Vision Base URL"),
        value=vision_base_url,
        help="自定义 API 端点（可选）找不到供应商才需要填自定义 url"
    )

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
                    success, message = test_litellm_vision_model(
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
                    logger.error(f"LiteLLM 视频分析模型连接测试失败: {str(e)}")

    # 验证和保存配置
    validation_errors = []
    config_changed = False

    # 验证模型名称
    if st_vision_model_name:
        # 这里的验证逻辑可能需要微调，因为我们现在是自动组合的
        is_valid, error_msg = validate_litellm_model_name(st_vision_model_name, "视频分析")
        if is_valid:
            config.app["vision_litellm_model_name"] = st_vision_model_name
            st.session_state["vision_litellm_model_name"] = st_vision_model_name
            config_changed = True
        else:
            validation_errors.append(error_msg)

    # 验证 API 密钥
    if st_vision_api_key:
        is_valid, error_msg = validate_api_key(st_vision_api_key, "视频分析")
        if is_valid:
            config.app["vision_litellm_api_key"] = st_vision_api_key
            st.session_state["vision_litellm_api_key"] = st_vision_api_key
            config_changed = True
        else:
            validation_errors.append(error_msg)

    # 验证 Base URL（可选）
    if st_vision_base_url:
        is_valid, error_msg = validate_base_url(st_vision_base_url, "视频分析")
        if is_valid:
            config.app["vision_litellm_base_url"] = st_vision_base_url
            st.session_state["vision_litellm_base_url"] = st_vision_base_url
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
                st.success(f"视频分析模型配置已保存（LiteLLM）")
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
    """渲染文案生成模型设置（LiteLLM 统一配置）"""
    st.subheader(tr("Text Generation Model Settings"))

    # 固定使用 LiteLLM 提供商
    config.app["text_llm_provider"] = "litellm"

    # 获取已保存的 LiteLLM 配置
    full_text_model_name = config.app.get("text_litellm_model_name", "deepseek/deepseek-chat")
    text_api_key = config.app.get("text_litellm_api_key", "")
    text_base_url = config.app.get("text_litellm_base_url", "")

    # 解析 provider 和 model
    default_provider = "deepseek"
    default_model = "deepseek-chat"
    
    if "/" in full_text_model_name:
        parts = full_text_model_name.split("/", 1)
        current_provider = parts[0]
        current_model = parts[1]
    else:
        current_provider = default_provider
        current_model = full_text_model_name

    # 定义支持的 provider 列表
    LITELLM_PROVIDERS = [
        "openai", "gemini", "deepseek", "qwen", "siliconflow", "moonshot", 
        "anthropic", "azure", "ollama", "vertex_ai", "mistral", "codestral", 
        "volcengine", "groq", "cohere", "together_ai", "fireworks_ai", 
        "openrouter", "replicate", "huggingface", "xai", "deepgram", "vllm", 
        "bedrock", "cloudflare"
    ]
    
    # 如果当前 provider 不在列表中，添加到列表头部
    if current_provider not in LITELLM_PROVIDERS:
        LITELLM_PROVIDERS.insert(0, current_provider)

    # 渲染配置输入框
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_provider = st.selectbox(
            tr("Text Model Provider"),
            options=LITELLM_PROVIDERS,
            index=LITELLM_PROVIDERS.index(current_provider) if current_provider in LITELLM_PROVIDERS else 0,
            key="text_provider_select"
        )
    
    with col2:
        model_name_input = st.text_input(
            tr("Text Model Name"),
            value=current_model,
            help="输入模型名称（不包含 provider 前缀）\n\n"
                 "常用示例:\n"
                 "• deepseek-chat\n"
                 "• gpt-4o\n"
                 "• gemini-2.0-flash\n"
                 "• deepseek-ai/DeepSeek-R1 (SiliconFlow)\n\n"
                 "支持 100+ providers，详见: https://docs.litellm.ai/docs/providers",
            key="text_model_input"
        )

    # 组合完整的模型名称
    st_text_model_name = f"{selected_provider}/{model_name_input}" if selected_provider and model_name_input else ""

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

    st_text_base_url = st.text_input(
        tr("Text Base URL"),
        value=text_base_url,
        help="自定义 API 端点（可选）找不到供应商才需要填自定义 url"
    )

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
                    success, message = test_litellm_text_model(
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
                    logger.error(f"LiteLLM 文案生成模型连接测试失败: {str(e)}")

    # 验证和保存配置
    text_validation_errors = []
    text_config_changed = False

    # 验证模型名称
    if st_text_model_name:
        is_valid, error_msg = validate_litellm_model_name(st_text_model_name, "文案生成")
        if is_valid:
            config.app["text_litellm_model_name"] = st_text_model_name
            st.session_state["text_litellm_model_name"] = st_text_model_name
            text_config_changed = True
        else:
            text_validation_errors.append(error_msg)

    # 验证 API 密钥
    if st_text_api_key:
        is_valid, error_msg = validate_api_key(st_text_api_key, "文案生成")
        if is_valid:
            config.app["text_litellm_api_key"] = st_text_api_key
            st.session_state["text_litellm_api_key"] = st_text_api_key
            text_config_changed = True
        else:
            text_validation_errors.append(error_msg)

    # 验证 Base URL（可选）
    if st_text_base_url:
        is_valid, error_msg = validate_base_url(st_text_base_url, "文案生成")
        if is_valid:
            config.app["text_litellm_base_url"] = st_text_base_url
            st.session_state["text_litellm_base_url"] = st_text_base_url
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
                st.success(f"文案生成模型配置已保存（LiteLLM）")
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

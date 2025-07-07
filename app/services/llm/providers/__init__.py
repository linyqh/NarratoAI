"""
大模型服务提供商实现

包含各种大模型服务提供商的具体实现
"""

from .gemini_provider import GeminiVisionProvider, GeminiTextProvider
from .gemini_openai_provider import GeminiOpenAIVisionProvider, GeminiOpenAITextProvider
from .openai_provider import OpenAITextProvider
from .qwen_provider import QwenVisionProvider, QwenTextProvider
from .deepseek_provider import DeepSeekTextProvider
from .siliconflow_provider import SiliconflowVisionProvider, SiliconflowTextProvider

# 自动注册所有提供商
from ..manager import LLMServiceManager

def register_all_providers():
    """注册所有提供商"""
    # 注册视觉模型提供商
    LLMServiceManager.register_vision_provider('gemini', GeminiVisionProvider)
    LLMServiceManager.register_vision_provider('gemini(openai)', GeminiOpenAIVisionProvider)
    LLMServiceManager.register_vision_provider('qwenvl', QwenVisionProvider)
    LLMServiceManager.register_vision_provider('siliconflow', SiliconflowVisionProvider)

    # 注册文本模型提供商
    LLMServiceManager.register_text_provider('gemini', GeminiTextProvider)
    LLMServiceManager.register_text_provider('gemini(openai)', GeminiOpenAITextProvider)
    LLMServiceManager.register_text_provider('openai', OpenAITextProvider)
    LLMServiceManager.register_text_provider('qwen', QwenTextProvider)
    LLMServiceManager.register_text_provider('deepseek', DeepSeekTextProvider)
    LLMServiceManager.register_text_provider('siliconflow', SiliconflowTextProvider)

# 自动注册
register_all_providers()

__all__ = [
    'GeminiVisionProvider',
    'GeminiTextProvider', 
    'GeminiOpenAIVisionProvider',
    'GeminiOpenAITextProvider',
    'OpenAITextProvider',
    'QwenVisionProvider',
    'QwenTextProvider',
    'DeepSeekTextProvider',
    'SiliconflowVisionProvider',
    'SiliconflowTextProvider'
]

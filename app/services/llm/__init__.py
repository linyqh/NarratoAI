"""
NarratoAI 大模型服务模块

统一的大模型服务抽象层，支持多供应商切换和严格的输出格式验证
包含视觉模型和文本生成模型的统一接口

主要组件:
- BaseLLMProvider: 大模型服务提供商基类
- VisionModelProvider: 视觉模型提供商基类
- TextModelProvider: 文本模型提供商基类
- LLMServiceManager: 大模型服务管理器
- OutputValidator: 输出格式验证器

支持的供应商:
视觉模型: Gemini, QwenVL, Siliconflow
文本模型: OpenAI, DeepSeek, Gemini, Qwen, Moonshot, Siliconflow
"""

from .manager import LLMServiceManager
from .base import BaseLLMProvider, VisionModelProvider, TextModelProvider
from .validators import OutputValidator, ValidationError
from .exceptions import LLMServiceError, ProviderNotFoundError, ConfigurationError

# 提供商注册由 webui.py:main() 显式调用（见 LLM 提供商注册机制重构）
# 这样更可靠，错误也更容易调试

__all__ = [
    'LLMServiceManager',
    'BaseLLMProvider', 
    'VisionModelProvider',
    'TextModelProvider',
    'OutputValidator',
    'ValidationError',
    'LLMServiceError',
    'ProviderNotFoundError', 
    'ConfigurationError'
]

# 版本信息
__version__ = '1.0.0'

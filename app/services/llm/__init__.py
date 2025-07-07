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

# 确保提供商在模块导入时被注册
def _ensure_providers_registered():
    """确保所有提供商都已注册"""
    try:
        # 导入providers模块会自动执行注册
        from . import providers
        from loguru import logger
        logger.debug("LLM服务提供商注册完成")
    except Exception as e:
        from loguru import logger
        logger.error(f"LLM服务提供商注册失败: {str(e)}")

# 自动注册提供商
_ensure_providers_registered()

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

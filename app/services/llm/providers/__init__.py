"""
大模型服务提供商实现

包含各种大模型服务提供商的具体实现
"""

# 不在模块顶部导入 provider 类，避免循环依赖
# 所有导入都在 register_all_providers() 函数内部进行


def register_all_providers():
    """
    注册所有提供商

    当前实现：注册 OpenAI 兼容统一接口，并可选注册 TwelveLabs Pegasus 视频理解。
    """
    # 在函数内部导入，避免循环依赖
    from ..manager import LLMServiceManager
    from loguru import logger

    # 只导入 OpenAI 兼容 provider
    from ..openai_compatible_provider import (
        OpenAICompatibleVisionProvider,
        OpenAICompatibleTextProvider,
    )

    logger.info("🔧 开始注册 LLM 提供商...")

    # ===== 注册 OpenAI 兼容统一接口 =====
    LLMServiceManager.register_vision_provider('openai', OpenAICompatibleVisionProvider)
    LLMServiceManager.register_text_provider('openai', OpenAICompatibleTextProvider)

    logger.info("✅ OpenAI 兼容提供商注册完成")

    # ===== 注册 TwelveLabs Pegasus 视频理解（可选视觉提供商）=====
    # 仅当用户将 vision_llm_provider 设为 "twelvelabs" 时启用；默认行为保持不变。
    from ..twelvelabs_provider import TwelveLabsVisionProvider

    LLMServiceManager.register_vision_provider('twelvelabs', TwelveLabsVisionProvider)

    logger.info("✅ TwelveLabs Pegasus 视觉提供商注册完成")


# 导出注册函数
__all__ = [
    'register_all_providers',
]

# 注意: Provider 类不再从此模块导出，因为它们只在注册函数内部使用
# 这样做是为了避免循环依赖问题，所有 provider 类的导入都延迟到注册时进行

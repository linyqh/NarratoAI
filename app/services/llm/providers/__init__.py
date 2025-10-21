"""
大模型服务提供商实现

包含各种大模型服务提供商的具体实现
推荐使用 LiteLLM 统一接口（支持 100+ providers）
"""

# 不在模块顶部导入 provider 类，避免循环依赖
# 所有导入都在 register_all_providers() 函数内部进行


def register_all_providers():
    """
    注册所有提供商

    v0.8.0 变更：只注册 LiteLLM 统一接口
    - 移除了旧的单独 provider 实现 (gemini, openai, qwen, deepseek, siliconflow)
    - LiteLLM 支持 100+ providers，无需单独实现
    """
    # 在函数内部导入，避免循环依赖
    from ..manager import LLMServiceManager
    from loguru import logger

    # 只导入 LiteLLM provider
    from ..litellm_provider import LiteLLMVisionProvider, LiteLLMTextProvider

    logger.info("🔧 开始注册 LLM 提供商...")

    # ===== 注册 LiteLLM 统一接口 =====
    # LiteLLM 支持 100+ providers（OpenAI, Gemini, Qwen, DeepSeek, SiliconFlow, 等）
    LLMServiceManager.register_vision_provider('litellm', LiteLLMVisionProvider)
    LLMServiceManager.register_text_provider('litellm', LiteLLMTextProvider)

    logger.info("✅ LiteLLM 提供商注册完成（支持 100+ providers）")


# 导出注册函数
__all__ = [
    'register_all_providers',
]

# 注意: Provider 类不再从此模块导出，因为它们只在注册函数内部使用
# 这样做是为了避免循环依赖问题，所有 provider 类的导入都延迟到注册时进行

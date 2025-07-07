#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : __init__.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 统一提示词管理模块
"""

from .manager import PromptManager
from .base import BasePrompt, VisionPrompt, TextPrompt, ParameterizedPrompt
from .registry import PromptRegistry
from .template import TemplateRenderer
from .validators import PromptOutputValidator
from .exceptions import (
    PromptError,
    PromptNotFoundError,
    PromptValidationError,
    TemplateRenderError
)

# 版本信息
__version__ = "1.0.0"
__author__ = "viccy同学"

# 导出的公共接口
__all__ = [
    # 核心管理器
    "PromptManager",
    
    # 基础类
    "BasePrompt",
    "VisionPrompt", 
    "TextPrompt",
    "ParameterizedPrompt",
    
    # 工具类
    "PromptRegistry",
    "TemplateRenderer",
    "PromptOutputValidator",
    
    # 异常类
    "PromptError",
    "PromptNotFoundError",
    "PromptValidationError",
    "TemplateRenderError",
    
    # 版本信息
    "__version__",
    "__author__"
]

# 模块初始化
def initialize_prompts():
    """初始化提示词模块，注册所有提示词"""
    from . import documentary
    from . import short_drama_editing  
    from . import short_drama_narration
    
    # 注册各模块的提示词
    documentary.register_prompts()
    short_drama_editing.register_prompts()
    short_drama_narration.register_prompts()

# 自动初始化
initialize_prompts()

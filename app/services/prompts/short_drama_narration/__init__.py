#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : __init__.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧解说提示词模块
"""

from .plot_analysis import PlotAnalysisPrompt
from .script_generation import ScriptGenerationPrompt
from ..manager import PromptManager


def register_prompts():
    """注册短剧解说相关的提示词"""
    
    # 注册剧情分析提示词
    plot_analysis_prompt = PlotAnalysisPrompt()
    PromptManager.register_prompt(plot_analysis_prompt, is_default=True)
    
    # 注册解说脚本生成提示词
    script_generation_prompt = ScriptGenerationPrompt()
    PromptManager.register_prompt(script_generation_prompt, is_default=True)


__all__ = [
    "PlotAnalysisPrompt",
    "ScriptGenerationPrompt",
    "register_prompts"
]

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : __init__.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧混剪提示词模块
"""

from .subtitle_analysis import SubtitleAnalysisPrompt
from .plot_extraction import PlotExtractionPrompt
from ..manager import PromptManager


def register_prompts():
    """注册短剧混剪相关的提示词"""
    
    # 注册字幕分析提示词
    subtitle_analysis_prompt = SubtitleAnalysisPrompt()
    PromptManager.register_prompt(subtitle_analysis_prompt, is_default=True)
    
    # 注册爆点提取提示词
    plot_extraction_prompt = PlotExtractionPrompt()
    PromptManager.register_prompt(plot_extraction_prompt, is_default=True)


__all__ = [
    "SubtitleAnalysisPrompt",
    "PlotExtractionPrompt", 
    "register_prompts"
]

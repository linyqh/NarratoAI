#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : __init__.py
@Description: 影视解说提示词模块
"""

from .plot_analysis import PlotAnalysisPrompt
from .narration_copy import NarrationCopyPrompt
from .segment_planning import SegmentPlanningPrompt
from .script_generation import ScriptGenerationPrompt
from .script_matching import ScriptMatchingPrompt
from .script_repair import ScriptRepairPrompt
from ..manager import PromptManager


def register_prompts():
    """注册影视解说相关的提示词"""
    plot_analysis_prompt = PlotAnalysisPrompt()
    PromptManager.register_prompt(plot_analysis_prompt, is_default=True)

    narration_copy_prompt = NarrationCopyPrompt()
    PromptManager.register_prompt(narration_copy_prompt, is_default=True)

    segment_planning_prompt = SegmentPlanningPrompt()
    PromptManager.register_prompt(segment_planning_prompt, is_default=True)

    script_generation_prompt = ScriptGenerationPrompt()
    PromptManager.register_prompt(script_generation_prompt, is_default=True)

    script_matching_prompt = ScriptMatchingPrompt()
    PromptManager.register_prompt(script_matching_prompt, is_default=True)

    script_repair_prompt = ScriptRepairPrompt()
    PromptManager.register_prompt(script_repair_prompt, is_default=True)


__all__ = [
    "PlotAnalysisPrompt",
    "NarrationCopyPrompt",
    "SegmentPlanningPrompt",
    "ScriptGenerationPrompt",
    "ScriptMatchingPrompt",
    "ScriptRepairPrompt",
    "register_prompts",
]

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : subtitle_analysis.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧字幕分析提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class SubtitleAnalysisPrompt(TextPrompt):
    """短剧字幕分析提示词"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="subtitle_analysis",
            category="short_drama_editing",
            version="v1.0",
            description="分析短剧字幕内容，提取剧情梗概和关键情节点",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "字幕分析", "剧情梗概", "情节提取"],
            parameters=["subtitle_content", "custom_clips"]
        )
        super().__init__(metadata)
        
        self._system_prompt = "你是一名短剧编剧和内容分析师，擅长从字幕中提取剧情要点和关键情节。"
        
    def get_template(self) -> str:
        return """请仔细分析以下短剧字幕内容，提取剧情梗概和关键情节点。

字幕内容：
${subtitle_content}

分析要求：
1. 提取整体剧情梗概，概括主要故事线和核心冲突
2. 识别 ${custom_clips} 个最具吸引力的关键情节点（爆点）
3. 每个情节点要包含具体的时间段和详细描述
4. 关注剧情的转折点、冲突高潮、情感爆发等关键时刻
5. 确保选择的情节点具有强烈的戏剧张力和观看价值

请按照以下JSON格式输出分析结果：

{
  "summary": "整体剧情梗概，简要概括主要故事线、角色关系和核心冲突",
  "plot_titles": [
    "情节点1标题",
    "情节点2标题",
    "情节点3标题"
  ],
  "analysis_details": {
    "main_characters": ["主要角色1", "主要角色2"],
    "story_theme": "故事主题",
    "conflict_type": "冲突类型（如：爱情、复仇、家庭等）",
    "emotional_peaks": ["情感高潮点1", "情感高潮点2"]
  }
}

重要要求：
1. 必须输出有效的JSON格式，不能包含注释或其他文字
2. 剧情梗概要简洁明了，突出核心看点
3. 情节点标题要吸引人，体现戏剧冲突
4. 严禁虚构不存在的剧情内容
5. 分析要客观准确，基于字幕实际内容"""

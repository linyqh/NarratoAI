#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : plot_extraction.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧爆点提取提示词
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class PlotExtractionPrompt(TextPrompt):
    """短剧爆点提取提示词"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="plot_extraction",
            category="short_drama_editing",
            version="v1.0",
            description="根据剧情梗概和字幕内容，精确定位关键剧情的时间段",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "爆点定位", "时间戳", "剧情提取"],
            parameters=["subtitle_content", "plot_summary", "plot_titles"]
        )
        super().__init__(metadata)
        
        self._system_prompt = "你是一名短剧编剧，非常擅长根据字幕中分析视频中关键剧情出现的具体时间段。"
        
    def get_template(self) -> str:
        return """请仔细阅读剧情梗概和爆点内容，然后在字幕中找出每个爆点发生的具体时间段和爆点前后的详细剧情。

剧情梗概：
${plot_summary}

需要定位的爆点内容：
${plot_titles}

字幕内容：
${subtitle_content}

分析要求：
1. 为每个爆点找到对应的具体时间段
2. 时间段要准确反映该爆点的完整发展过程
3. 提供爆点前后的详细剧情描述
4. 确保时间戳格式正确且存在于字幕中
5. 选择最具戏剧张力的时间段

请返回一个JSON对象，包含一个名为"plot_points"的数组，数组中包含多个对象，每个对象都要包含以下字段：

{
  "plot_points": [
    {
      "timestamp": "时间段，格式为xx:xx:xx,xxx-xx:xx:xx,xxx",
      "title": "关键剧情的主题",
      "picture": "关键剧情前后的详细剧情描述，包括人物对话、动作、情感变化等"
    }
  ]
}

重要要求：
1. 请确保返回的是合法的JSON格式
2. 时间戳必须严格按照字幕中的格式
3. 剧情描述要详细具体，包含关键对话和动作
4. 每个爆点的时间段要合理，不能过短或过长
5. 严禁虚构不存在的时间戳或剧情内容
6. 只输出JSON内容，不要添加任何说明文字"""

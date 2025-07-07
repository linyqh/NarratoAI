#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : script_generation.py
@Author : AI Assistant
@Date   : 2025/1/7
@Description: 短剧解说脚本生成提示词
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptGenerationPrompt(ParameterizedPrompt):
    """短剧解说脚本生成提示词"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="script_generation",
            category="short_drama_narration",
            version="v1.0",
            description="根据剧情分析生成短剧解说脚本，包含解说文案和原声片段",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "解说脚本", "文案生成", "原声片段"],
            parameters=["drama_name", "plot_analysis"]
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis"])
        
        self._system_prompt = "你是一位专业的短视频解说脚本撰写专家。你必须严格按照JSON格式输出，不能包含任何其他文字、说明或代码块标记。"
        
    def get_template(self) -> str:
        return """我是一个影视解说up主，需要为我的粉丝讲解短剧《${drama_name}》的剧情，目前正在解说剧情，希望能让粉丝通过我的解说了解剧情，并且产生继续观看的兴趣，请生成一篇解说脚本，包含解说文案，以及穿插原声的片段，下面<plot>中的内容是短剧的剧情概述：

<plot>
${plot_analysis}
</plot>

请严格按照以下JSON格式输出，不要添加任何其他文字、说明或代码块标记：

{{
  "items": [
    {{
        "_id": 1,
        "timestamp": "00:00:05,390-00:00:10,430",
        "picture": "剧情描述或者备注",
        "narration": "解说文案，如果片段为穿插的原片片段，可以直接使用 '播放原片+_id' 进行占位",
        "OST": 0
    }}
  ]
}}

重要要求：
1. 必须输出有效的JSON格式，不能包含注释
2. OST字段必须是数字：0表示解说片段，1表示原片片段
3. _id必须是递增的数字
4. 只输出JSON内容，不要输出任何说明文字
5. 不要使用代码块标记（如```json）
6. 解说文案使用简体中文
7. 严禁虚构剧情，所有内容只能从<plot>中摘取
8. 严禁虚构时间戳，所有时间戳只能从<plot>中摘取
9. 解说文案要生动有趣，能够吸引观众继续观看
10. 合理安排解说片段和原片片段的比例，保持节奏感"""

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

{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:05,390-00:00:10,430",
        "picture": "剧情描述或者备注",
        "narration": "解说文案，如果片段为穿插的原片片段，可以直接使用 '播放原片+_id' 进行占位",
        "OST": 0
    }
  ]
}

重要要求：
1. 只输出 json 内容，不要输出其他任何说明性的文字
2. 解说文案必须遵循“起-承-转-合”的线性时间链
3. 解说文案需包含角色微表情、动作细节、场景氛围的描写，每段80-150字
4. 通过细节关联普遍情感（如遗憾、和解、成长），避免直白抒情
5. 所有细节严格源自<plot>，可对角色行为进行合理心理推导但不虚构剧情
6. 时间戳从<plot>摘取，可根据解说内容拆分原时间片段（如将10秒拆分为两个5秒）
7. 解说与原片穿插比例控制在7:3，关键情绪点保留原片原声
8. 严禁跳脱剧情发展顺序，所有描述必须符合“先发生A，再发生B，A导致B”的逻辑
9. 强化流程感，让观众清晰感知剧情推进的先后顺序"""

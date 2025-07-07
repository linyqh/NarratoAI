#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : frame_analysis.py
@Author : AI Assistant
@Date   : 2025/1/7
@Description: 纪录片视频帧分析提示词
"""

from ..base import VisionPrompt, PromptMetadata, ModelType, OutputFormat


class FrameAnalysisPrompt(VisionPrompt):
    """纪录片视频帧分析提示词"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="frame_analysis",
            category="documentary",
            version="v1.0",
            description="分析纪录片视频关键帧，提取画面内容和场景描述",
            model_type=ModelType.VISION,
            output_format=OutputFormat.JSON,
            tags=["纪录片", "视频分析", "关键帧", "画面描述"],
            parameters=["video_theme", "custom_instructions"]
        )
        super().__init__(metadata)
        
        self._system_prompt = "你是一名专业的视频内容分析师，擅长分析纪录片视频帧内容，提取关键信息和场景描述。"
        
    def get_template(self) -> str:
        return """请仔细分析这些视频关键帧图片，我需要你提供详细的画面分析。

视频主题：${video_theme}

分析要求：
1. 按时间顺序分析每一帧画面
2. 详细描述画面中的主要内容、人物、物体、环境
3. 注意画面的构图、色彩、光线等视觉元素
4. 识别画面中的关键动作或变化
5. 提供准确的时间戳信息

${custom_instructions}

请按照以下JSON格式输出分析结果：

{{
  "analysis": [
    {{
      "timestamp": "00:00:05,390",
      "picture": "详细的画面描述，包括场景、人物、物体、动作等",
      "scene_type": "场景类型（如：建造、准备、完成等）",
      "key_elements": ["关键元素1", "关键元素2"],
      "visual_quality": "画面质量描述（构图、光线、色彩等）"
    }}
  ],
  "summary": "整体视频内容概述",
  "total_frames": "分析的帧数"
}}

重要要求：
1. 只输出JSON格式，不要添加任何其他文字或代码块标记
2. 画面描述要详细准确，为后续解说文案生成提供充分信息
3. 时间戳必须准确对应视频帧
4. 严禁虚构不存在的内容"""

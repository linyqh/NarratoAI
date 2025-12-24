#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧混剪-画面匹配
@File   : plot_extraction.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧爆点提取提示词 - 优化版本v2.0
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class PlotExtractionPrompt(TextPrompt):
    """短剧爆点提取提示词 - 优化版本"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="plot_extraction",
            category="short_drama_editing",
            version="v2.0",
            description="根据剧情梗概和字幕内容，精确定位关键剧情的时间段，确保片段连贯可剪辑",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "爆点定位", "时间戳", "剧情提取", "连贯性", "过渡片段"],
            parameters=["subtitle_content", "plot_summary", "plot_titles"]
        )
        super().__init__(metadata)
        
        self._system_prompt = "你是一名专业短剧剪辑师，精通视频叙事节奏和剧情连贯性，擅长选择能够流畅衔接的视频片段。"
        
    def get_template(self) -> str:
        return """# 短剧混剪时间段定位任务

## 任务目标
为每个关键情节点精确定位时间段，确保最终剪辑出的视频**剧情连贯、逻辑清晰**。

## 输入信息

### 剧情梗概
<plot_summary>
${plot_summary}
</plot_summary>

### 需要定位的情节点（按剧情发展顺序）
<plot_titles>
${plot_titles}
</plot_titles>

### 完整字幕内容
<subtitles>
${subtitle_content}
</subtitles>

## 时间段选择原则

### 1. 连贯性原则（最重要）
**目标：观众看完剪辑后能理解完整故事**

- **包含必要上下文**：每个片段要包含理解该情节所需的前置信息
- **自然的开始点**：片段开头应该是一个自然的场景切入点
- **完整的结束点**：片段结尾应该是一个自然的收尾或转折点
- **衔接考虑**：考虑与前后片段的衔接是否流畅

### 2. 时间段技术规范（绝对不能违反）

**时间戳规则**：
- 格式必须为：`xx:xx:xx,xxx-xx:xx:xx,xxx`
- 必须与字幕中的时间戳精确匹配
- **严禁时间段重叠**：任意两个片段的时间不能有交集
- **严格按时间顺序**：后一个片段的开始时间必须大于前一个片段的结束时间

**时长控制**：
- 单个片段建议时长：10-60秒
- 过短（<5秒）：信息不完整，观众无法理解
- 过长（>90秒）：节奏拖沓，失去混剪意义

### 3. 内容完整性原则

每个片段必须包含：
- **情节的起因**：为什么会发生这件事
- **情节的经过**：具体发生了什么
- **情节的结果/转折**：导致了什么后果

### 4. 过渡片段策略

如果两个关键情节之间跳跃太大，需要：
- 适当延长前一个片段的结尾
- 或适当提前后一个片段的开始
- 确保观众能理解剧情是如何发展到下一个阶段的

## 输出格式

请严格按照以下JSON格式输出：

{
  "plot_points": [
    {
      "sequence": 1,
      "timestamp": "00:01:23,456-00:02:15,789",
      "title": "情节标题",
      "narrative_function": "开端/发展/高潮/结局",
      "picture": "详细的画面和剧情描述，包括：场景环境、人物状态、关键对话、动作行为、情感表现",
      "context_before": "这个片段之前发生了什么（简述）",
      "context_after": "这个片段之后会发生什么（简述）",
      "transition_note": "与下一个片段的衔接说明"
    }
  ],
  "editing_notes": {
    "total_duration": "所有片段的总时长估算",
    "pacing_suggestion": "节奏建议（如：开头可稍慢，高潮处加快）",
    "potential_gaps": ["可能存在的剧情跳跃点及建议处理方式"]
  }
}

## 质量检查清单

输出前请逐项检查：

**时间戳检查**：
- [ ] 所有时间戳都存在于原始字幕中
- [ ] 时间段之间没有重叠
- [ ] 时间段按顺序排列（后一个开始 > 前一个结束）

**连贯性检查**：
- [ ] 第一个片段是否交代了必要的背景？
- [ ] 相邻片段之间的剧情跳跃是否可以理解？
- [ ] 最后一个片段是否给出了某种结局或悬念？

**完整性检查**：
- [ ] 每个片段是否包含完整的小情节（起因-经过-结果）？
- [ ] 观众只看这些片段能否理解整个故事的主线？

## 重要限制

1. **严禁虚构时间戳**：所有时间必须来自字幕
2. **严禁时间重叠**：这会导致剪辑出现重复画面
3. **严禁打乱顺序**：必须按剧情发展的时间线排列
4. **只输出JSON**：不要添加任何说明文字"""

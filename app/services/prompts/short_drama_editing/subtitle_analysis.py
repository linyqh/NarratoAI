#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧混剪-剧情分析
@File   : subtitle_analysis.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧字幕分析提示词 - 优化版本v2.0
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class SubtitleAnalysisPrompt(TextPrompt):
    """短剧字幕分析提示词 - 优化版本"""
    
    def __init__(self):
        metadata = PromptMetadata(
            name="subtitle_analysis",
            category="short_drama_editing",
            version="v2.0",
            description="分析短剧字幕内容，提取完整叙事结构和关键情节点，确保剧情连贯性",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "字幕分析", "剧情梗概", "情节提取", "叙事结构", "连贯性"],
            parameters=["subtitle_content", "custom_clips"]
        )
        super().__init__(metadata)
        
        self._system_prompt = "你是一名资深短剧编剧和剪辑师，精通叙事结构和剧情节奏把控，擅长从字幕中提取能够形成完整故事线的关键情节。"
        
    def get_template(self) -> str:
        return """# 短剧混剪剧情分析任务

## 任务目标
分析短剧字幕，提取能够组成**连贯完整故事**的关键情节点。最终混剪视频必须让观众能够理解剧情发展脉络。

## 字幕内容
<subtitles>
${subtitle_content}
</subtitles>

## 分析要求

### 1. 叙事结构分析（必须完成）
按照经典叙事结构识别剧情阶段：
- **开端（Setup）**：人物出场、背景交代、初始状态
- **发展（Rising Action）**：冲突引入、矛盾升级
- **高潮（Climax）**：核心冲突爆发、情感顶点
- **结局（Resolution）**：冲突解决、结果呈现

### 2. 关键情节点选择原则
需要选择 ${custom_clips} 个情节点，必须遵循：

**连贯性原则（最重要）**：
- 情节点必须能串联成完整故事线
- 相邻情节点之间要有逻辑关联
- 观众看完后能理解"发生了什么"

**覆盖性原则**：
- 必须包含开端（至少1个）：交代人物和背景
- 必须包含发展（至少1-2个）：展示冲突升级
- 必须包含高潮（至少1个）：最具张力的时刻
- 建议包含结局（如有）：给观众交代

**戏剧性原则**：
- 优先选择情感强烈的时刻
- 优先选择冲突明显的场景
- 优先选择有视觉冲击力的画面

### 3. 情节点排序要求
- **严格按照剧情发展的时间顺序排列**
- 确保因果关系清晰：先有A才有B
- 避免时间线跳跃造成的理解障碍

## 输出格式

请严格按照以下JSON格式输出，不要添加任何其他文字：

{
  "summary": "整体剧情梗概（100-200字），包含主要人物、核心冲突、发展脉络和结局",
  "narrative_structure": {
    "setup": "开端阶段概述：人物和背景",
    "rising_action": "发展阶段概述：冲突如何升级",
    "climax": "高潮阶段概述：核心冲突点",
    "resolution": "结局阶段概述：如何收尾（如有）"
  },
  "plot_titles": [
    "[开端] 情节点1标题 - 简要说明其叙事功能",
    "[发展] 情节点2标题 - 简要说明其叙事功能",
    "[高潮] 情节点3标题 - 简要说明其叙事功能"
  ],
  "plot_connections": [
    "情节1→情节2的逻辑关联说明",
    "情节2→情节3的逻辑关联说明"
  ],
  "analysis_details": {
    "main_characters": ["主要角色1（身份/特点）", "主要角色2（身份/特点）"],
    "core_conflict": "核心冲突是什么",
    "story_theme": "故事主题",
    "emotional_arc": "情感变化曲线（如：平静→震惊→愤怒→释然）"
  }
}

## 质量检查清单
输出前请自检：
1. ✓ 情节点是否覆盖了故事的起承转合？
2. ✓ 相邻情节点之间是否有明确的逻辑关联？
3. ✓ 观众只看这些片段能否理解整个故事？
4. ✓ 情节点是否按时间顺序排列？
5. ✓ 是否避免了孤立的"爆点"而忽略上下文？

## 重要限制
1. 严禁虚构不存在的剧情内容
2. 必须基于字幕实际内容分析
3. 只输出JSON，不要任何说明文字"""

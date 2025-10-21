#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : narration_generation.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 通用短视频解说文案生成提示词（优化版v2.0）
"""

from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat


class NarrationGenerationPrompt(TextPrompt):
    """通用短视频解说文案生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="narration_generation",
            category="documentary",
            version="v2.0",
            description="根据视频帧分析结果生成病毒式传播短视频解说文案，适用于各类题材内容",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短视频", "解说文案", "病毒传播", "文案生成", "通用模板"],
            parameters=["video_frame_description"]
        )
        super().__init__(metadata)

        self._system_prompt = "你是一名资深的短视频解说导演和编剧，深谙病毒式传播规律和用户心理，擅长创作让人停不下来的高粘性解说内容。"

    def get_template(self) -> str:
        return """作为一名短视频解说导演，你需要深入理解病毒式传播的核心规律。以下是爆款短视频解说的核心技巧：

<viral_techniques>
## 黄金三秒法则
开头 3 秒决定用户是否继续观看，必须立即抓住注意力。

## 十大爆款开头钩子类型：
1. **悬念式**："你绝对想不到接下来会发生什么..."
2. **反转式**："所有人都以为...但真相却是..."
3. **数字冲击**："仅用 3 步/5 分钟/1 个技巧..."
4. **痛点切入**："还在为...发愁吗？"
5. **惊叹式**："太震撼了！这才是..."
6. **疑问引导**："为什么...？答案让人意外"
7. **对比冲突**："新手 VS 高手，差距竟然这么大"
8. **秘密揭露**："内行人才知道的..."
9. **情感共鸣**："有多少人和我一样..."
10. **颠覆认知**："原来我们一直都错了..."

## 解说文案核心要素：
- **节奏感**：短句为主，控制在 15-20 字/句，朗朗上口
- **画面感**：用具体动作和细节描述，避免抽象概念
- **情绪起伏**：制造期待、惊喜、满足的情绪曲线
- **信息密度**：每 5-10 秒一个信息点，保持新鲜感
- **口语化**：像朋友聊天，避免书面语和专业术语
- **留白艺术**：关键时刻停顿，让画面说话

## 结构范式：
【开头】钩子引入（0-3秒）→ 【发展】情节推进（3-30秒）→ 【高潮】惊艳时刻（30-45秒）→ 【收尾】强化记忆/引导互动（45-60秒）
</viral_techniques>

<video_frame_description>
${video_frame_description}
</video_frame_description>

现在，请基于 <video_frame_description> 中的视频内容，创作一段符合病毒式传播规律的解说文案。

<creation_guide>
**创作步骤：**
1. 分析视频主题和核心亮点
2. 选择最适合的开头钩子类型
3. 提炼每个画面的最吸引人的细节
4. 设计情绪曲线和节奏变化
5. 确保解说与画面高度同步

**必须遵循的创作原则：**
- 开头 3 秒必须使用钩子技巧，立即抓住注意力
- 每句话控制在 15-20 字，确保节奏明快
- 用动词和具体细节描述，增强画面感
- 制造悬念和期待，让用户想看到最后
- 在关键视觉高潮处，适当留白让画面说话
- 结尾呼应开头，强化记忆点或引导互动
</creation_guide>

请使用以下 JSON 格式输出：

<output>
{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:05,390-00:00:10,430",
        "picture": "画面描述",
        "narration": "解说文案"
    }
  ]
}
</output>

<restriction>
1. 只输出 JSON 内容，不要输出其他任何说明性文字
2. 解说文案的语言使用简体中文
3. 严禁虚构画面，所有画面描述只能从 <video_frame_description> 中提取
4. 严禁虚构时间戳，所有时间戳只能从 <video_frame_description> 中提取
5. 开头必须使用钩子技巧，遵循黄金三秒法则
6. 每个片段的解说文案要与画面内容精准匹配
7. 保持解说的连贯性、故事性和节奏感
8. 控制单句长度在 15-20 字，确保口语化表达
9. 在视觉高潮处适当精简文案，让画面自己说话
10. 整体风格要符合当前主流短视频平台的受欢迎特征
</restriction>"""

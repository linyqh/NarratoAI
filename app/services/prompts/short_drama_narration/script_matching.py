#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧解说-文案画面匹配
@File   : script_matching.py
@Description: 将用户审核后的解说文案匹配到字幕时间戳并生成最终剪辑脚本
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptMatchingPrompt(ParameterizedPrompt):
    """短剧解说文案画面匹配提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_matching",
            category="short_drama_narration",
            version="v1.0",
            description="将审核后的解说文案按叙事节奏拆分，并匹配到字幕时间戳生成最终剪辑JSON",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "画面匹配", "剪辑脚本", "时间戳", "用户文案"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "narration_copy",
                "narration_language",
                "original_sound_ratio",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=["drama_name", "subtitle_content", "narration_copy"],
        )

        self._system_prompt = (
            "你是一位懂叙事节奏的短剧剪辑师。你必须严格输出JSON，"
            "核心任务是把用户审核后的解说文案逐句匹配到最合适的原视频字幕时间戳。"
        )

    def get_template(self) -> str:
        return """# 短剧解说文案画面匹配任务

## 目标
用户已经审核并修改了解说文案。请根据这份文案和原始字幕，生成最终可剪辑 JSON 脚本。

## 剧名
${drama_name}

## 剧情理解材料
<plot>
${plot_analysis}
</plot>

## 用户审核后的解说文案
<narration_copy>
${narration_copy}
</narration_copy>

## 原始字幕（含视频编号和局部时间戳）
<subtitles>
${subtitle_content}
</subtitles>

## 输出语言
<narration_language>
${narration_language}
</narration_language>

## 用户选择的短剧类型
<drama_genre>
${drama_genre}
</drama_genre>

## 用户选择的原片占比
<original_sound_ratio>
${original_sound_ratio}%
</original_sound_ratio>

## 匹配流程
1. 先按句号、问号、感叹号、省略号切分解说文案，得到候选解说句。
2. 逗号只在明显分割两个动作、场景、观点或描述对象时切分；不要切出没有独立意义的碎片。
3. 不要求每个候选句都单独输出为 OST=0；可以合并、压缩相邻候选句作为剧情桥段，但不能改变用户文案的核心意思。
4. 为每个解说片段寻找最匹配的原始字幕画面，优先选择能表达该句核心含义的画面。
5. 使用公式估算所需画面时长：所需秒数 = 解说字数 / 5。匹配画面时长尽量接近，误差优先控制在 ±0.5 秒。
6. 如果一句解说太长，必须拆成多个 OST=0 片段，分别匹配不同或连续画面。
7. timestamp 必须使用对应 video_id 内部局部时间戳，不得换算为多个视频拼接后的累计时间。
8. 同一 video_id 内时间段不得交叉或重叠。
9. 第一段必须是 OST=0 解说钩子，不能直接播放原片。
10. OST=1 原声片段的总时长占比要尽量接近用户选择的 ${original_sound_ratio}%。这里按最终 items 的 timestamp 总时长估算，不按片段数量估算。
11. 不要自行判断或改写短剧类型；画面匹配和 picture 描述要服务用户选择的 ${drama_genre} 叙事重点。

## 原片占比规则
- ${original_sound_ratio}% = 0% 时，不要输出 OST=1，全部使用解说承接。
- ${original_sound_ratio}% 在 10%-30% 时，只保留关键对白、反转、情绪爆发或爽点原声。
- ${original_sound_ratio}% 在 40%-60% 时，解说负责串联因果，原片负责承载关键场面和对白。
- ${original_sound_ratio}% 在 70%-90% 时，以原片对白和表演为主，解说只做开场钩子、转场桥和必要补充。
- 如果原片占比与“第一段必须 OST=0”冲突，优先保证第一段是 OST=0，然后在后续片段提高 OST=1 时长占比。
- 选择高原片占比时，可以把用户文案合并成更少的 OST=0 桥段，不要为了逐句使用文案而压低原片占比。

## 字段规则
- _id：从 1 开始连续递增。
- video_id：来自字幕分段标题，例如“视频 2”就填 2。
- video_name：对应视频文件名，必须从字幕分段标题提取。
- timestamp：格式为 "HH:MM:SS,mmm-HH:MM:SS,mmm"。
- picture：描述匹配画面中人物、动作、情绪和场景。
- narration：OST=0 时填写用户文案片段；OST=1 时填写“播放原片+_id”。
- OST：解说片段填 0，原声片段填 1。

## 输出格式
只输出严格 JSON：

{
  "items": [
    {
      "_id": 1,
      "video_id": 1,
      "video_name": "1.mp4",
      "timestamp": "00:00:01,000-00:00:06,000",
      "picture": "主角站在门口，震惊地看着屋内混乱的场面",
      "narration": "一个刚立功的兵王，回家的第一天就发现家里四百万被亲爹输光。",
      "OST": 0
    }
  ]
}

现在请基于用户审核后的解说文案生成最终剪辑脚本。"""

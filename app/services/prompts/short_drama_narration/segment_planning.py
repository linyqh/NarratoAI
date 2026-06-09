#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧解说-片段规划
@File   : segment_planning.py
@Description: 短剧解说脚本片段规划提示词
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class SegmentPlanningPrompt(ParameterizedPrompt):
    """短剧解说片段规划提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="segment_planning",
            category="short_drama_narration",
            version="v1.1",
            description="基于剧情理解和原始字幕规划可剪辑片段，优先保证叙事连续性、跨视频承接和原声解说节奏",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "解说脚本", "片段规划", "时间戳", "多视频", "原声"],
            parameters=["drama_name", "drama_genre", "plot_analysis", "subtitle_content", "narration_language"],
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis", "subtitle_content"])

        self._system_prompt = (
            "你是一位短剧解说剪辑规划师。你的任务是从字幕中选择可剪辑片段，"
            "必须严格输出JSON，不能写解说文案，不能输出Markdown或额外说明。"
        )

    def get_template(self) -> str:
        return """# 短剧解说片段规划任务

## 目标
为短剧《${drama_name}》规划一组可直接剪辑的视频片段。你只负责选片段和标注用途，不写最终解说台词。

## 剧情理解材料
<plot>
${plot_analysis}
</plot>

## 原始字幕（含视频编号和局部时间戳）
<subtitles>
${subtitle_content}
</subtitles>

## 解说台词目标语言
<narration_language>
${narration_language}
</narration_language>

## 用户选择的短剧类型
<drama_genre>
${drama_genre}
</drama_genre>

## 叙事规划目标
你不是在挑精彩片段合集，而是在规划一条观众能顺着看懂的短剧解说故事线。必须先想清楚“人物困境 -> 冲突触发 -> 关系变化 -> 新阻力 -> 悬念”的因果链，再选片段。

## 爆款开头钩子规则
第一段必须是 OST=0 解说开场，不要直接播放原片。开头参考“高能反转 + 情绪冲突 + 悬念钩子”的公式：
- 先给人物一个强身份或强处境：兵王、单亲妈妈、被赶出家门的女人、被全家看不起的赘婿。
- 再给一个反差冲突：刚立功就被迫退役、刚回家就发现钱被输光、刚结婚就遇到孩子/婆婆阻挠。
- 最后抛出悬念：真正的噩梦才开始、他要讨回的不是钱、这场婚姻真正难的不是相爱。
- 不要照抄示例，要基于字幕事实改写成当前剧情自己的钩子。

## 规划规则
1. 只能使用原始字幕中真实存在的视频编号、视频文件名和时间范围。
2. timestamp 必须是对应 video_id 内部的局部时间戳，禁止换算成多个视频拼接后的累计时间。
3. 同一个 video_id 内的片段不得交叉或重叠；尽量按故事顺序排列。
4. 每个片段必须推动主线、制造情绪点、承接原声或保留关键对白。
5. OST=1 表示保留原声，适合关键对白、情绪爆发、身份揭露、反转和爽点；OST=0 表示后续需要配解说。
6. 原声片段单段优先控制在 3-8 秒；解说片段可以更长，但必须能从字幕范围中定位。
7. 短剧类型由用户手动选择为 ${drama_genre}，不得自行改判；选片段时优先服务该类型的主要看点。
8. 禁止连续 3 个或更多 OST=1；每 1-2 个原声片段后必须安排 OST=0 解说片段承接剧情。
9. 跨 video_id 切换前后必须至少有一个 OST=0 片段作为剧情桥段，解释为什么从上一场转到下一场。
10. 每个 OST=0 片段必须承担明确叙事功能：开场钩子、人物介绍、因果过渡、冲突升级、关系转折、阻力解释、结尾悬念。
11. 不要跳过关键因果：例如从求婚直接跳到孩子/婆婆阻挠，中间必须用 OST=0 解释“婚姻真正的难题变成家庭接纳”。
12. 结尾优先选择能留下后续阻力或新矛盾的片段，不要只停在原声对白堆叠上。
13. 解说画面必须给足时长：按“解说字数 / 5 = 所需视频秒数”预估，短画面不要承载长解说。
14. OST=0 片段如果需要讲清多层信息，应选择更长的连续画面，或拆成多个 OST=0 片段分别承接。

## 输出格式
只输出严格 JSON：

{
  "segments": [
    {
      "_id": 1,
      "video_id": 1,
      "video_name": "1.mp4",
      "timestamp": "00:00:01,000-00:00:05,500",
      "OST": 0,
      "story_role": "开场钩子",
      "intent": "女主被羞辱，制造逆袭期待",
      "transition": "从灾后恢复现场切入女主处境，引出她为什么敢和领导硬刚"
    }
  ]
}

现在请规划短剧《${drama_name}》的解说片段。"""

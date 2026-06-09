#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 影视解说-片段规划
@File   : segment_planning.py
@Description: 影视解说脚本片段规划提示词
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class SegmentPlanningPrompt(ParameterizedPrompt):
    """影视解说片段规划提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="segment_planning",
            category="film_tv_narration",
            version="v1.0",
            description="基于剧情理解和原始字幕规划可剪辑片段，优先保证影视叙事连续性和原声解说节奏",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["影视", "解说脚本", "片段规划", "时间戳", "多视频", "原声"],
            parameters=["drama_name", "drama_genre", "plot_analysis", "subtitle_content", "narration_language"],
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis", "subtitle_content"])

        self._system_prompt = (
            "你是一位影视解说剪辑规划师。你的任务是从字幕中选择可剪辑片段，"
            "必须严格输出JSON，不能写解说文案，不能输出Markdown或额外说明。"
        )

    def get_template(self) -> str:
        return """# 影视解说片段规划任务

## 目标
为影视作品《${drama_name}》规划一组可直接剪辑的视频片段。你只负责选片段和标注用途，不写最终解说台词。

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

## 用户选择的影视类型
<drama_genre>
${drama_genre}
</drama_genre>

## 叙事规划目标
你不是在挑精彩片段合集，而是在规划一条观众能顺着看懂的影视解说故事线。必须先想清楚“人物处境 -> 事件触发 -> 关系或信息变化 -> 新危机 -> 悬念”的因果链，再选片段。

## 开场钩子规则
第一段必须是 OST=0 解说开场，不要直接播放原片。开头参考“人物困境 + 反常信息 + 悬念问题”的公式：
- 先给人物一个明确压力：被误解、被追捕、被迫选择、失去重要之人、发现异常线索。
- 再给一个反常信息：熟人背叛、证据失效、规则被打破、危险提前出现。
- 最后抛出问题：谁在说谎、真相藏在哪里、这次选择会付出什么代价。
- 不要照抄示例，要基于字幕事实改写成当前作品自己的钩子。

## 规划规则
1. 只能使用原始字幕中真实存在的视频编号、视频文件名和时间范围。
2. timestamp 必须是对应 video_id 内部的局部时间戳，禁止换算成多个视频拼接后的累计时间。
3. 同一个 video_id 内的片段不得交叉或重叠；尽量按故事顺序排列。
4. 严禁选择片头、片尾、演职员表、版权声明、平台水印展示、下集预告、花絮、赞助口播、商品露出、贴片广告、中插广告、片中广告或任何与主线剧情无关的推广片段；这些内容绝对不能进入 segments。
5. 如果字幕或画面文字出现“广告”“赞助”“推广”“片头”“片尾”“预告”“下集”“扫码”“购买”“会员”“关注”等明显非剧情信号，必须整段跳过，不得用作 OST=0 或 OST=1。
6. 每个片段必须推动主线、解释人物动机、制造情绪转折、承接原声或保留关键对白。
7. OST=1 表示保留原声，适合关键对白、情绪爆发、真相揭露、名场面和反转；OST=0 表示后续需要配解说。
8. 原声片段单段优先控制在 3-10 秒；解说片段可以更长，但必须能从字幕范围中定位。
9. 影视类型由用户手动选择为 ${drama_genre}，不得自行改判；选片段时优先服务该类型的主要看点。
10. 禁止连续 3 个或更多 OST=1；每 1-2 个原声片段后必须安排 OST=0 解说片段承接剧情。
11. 跨 video_id 切换前后必须至少有一个 OST=0 片段作为剧情桥段，解释为什么从上一场转到下一场。
12. 每个 OST=0 片段必须承担明确叙事功能：开场钩子、人物介绍、因果过渡、信息解释、情绪转折、冲突升级、结尾悬念。
13. 不要跳过关键因果；关系变化、线索发现、危机升级必须有画面或解说桥段承接。
14. 结尾优先选择能留下新问题、新危险或人物选择的片段，不要只停在原声对白堆叠上。
15. 解说画面必须给足时长：按“解说字数 / 5 = 所需视频秒数”预估，短画面不要承载长解说。

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
      "intent": "点出主角困境和反常线索，制造继续观看的疑问",
      "transition": "从当前场景切入人物压力，引出下一段关键对白"
    }
  ]
}

现在请规划影视作品《${drama_name}》的解说片段。"""

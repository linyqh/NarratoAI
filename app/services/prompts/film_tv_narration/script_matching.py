#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 影视解说-文案画面匹配
@File   : script_matching.py
@Description: 将用户审核后的影视解说文案匹配到字幕时间戳并生成最终剪辑脚本
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptMatchingPrompt(ParameterizedPrompt):
    """影视解说文案画面匹配提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_matching",
            category="film_tv_narration",
            version="v1.0",
            description="将审核后的影视解说文案按叙事节奏拆分，并匹配到字幕时间戳生成最终剪辑JSON",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["影视", "画面匹配", "剪辑脚本", "时间戳", "用户文案"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "narration_copy",
                "narration_language",
                "original_sound_ratio",
                "visual_evidence",
                "highlight_candidates",
                "core_window",
                "context_window",
                "segment_role",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=["drama_name", "subtitle_content", "narration_copy"],
        )

        self._system_prompt = (
            "你是一位懂影视叙事节奏的剪辑师。你必须严格输出JSON，"
            "核心任务是把用户审核后的解说文案逐句匹配到最合适的原视频字幕时间戳。"
        )

    def get_template(self) -> str:
        return """# 影视解说文案画面匹配任务

## 目标
用户已经审核并修改了解说文案。请根据这份文案和原始字幕，生成最终可剪辑 JSON 脚本。

## 作品名
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

## 视觉证据（仅可用于确认画面事实）
<visual_evidence>
${visual_evidence}
</visual_evidence>

## 原片高光候选（仅作 OST=1 优先级依据）
<highlight_candidates>
${highlight_candidates}
</highlight_candidates>

## 当前计划段（必须遵守）
<segment>
核心可输出时间范围：${core_window}
上下文时间范围：${context_window}
叙事职责：${segment_role}
</segment>

## 输出语言
<narration_language>
${narration_language}
</narration_language>

## 用户选择的影视类型
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
4. 严禁把解说文案匹配到片头、片尾、演职员表、版权声明、平台水印展示、下集预告、花絮、赞助口播、商品露出、贴片广告、中插广告、片中广告或任何与主线剧情无关的推广片段；这些内容绝对不能进入最终 items。
5. 如果字幕或画面文字出现“广告”“赞助”“推广”“片头”“片尾”“预告”“下集”“扫码”“购买”“会员”“关注”等明显非剧情信号，必须跳过对应时间段，不得用作 OST=0 或 OST=1。
6. 为每个解说片段寻找最匹配的原始字幕画面，优先选择能表达该句核心含义、人物状态或信息转折的画面。
7. 使用公式估算所需画面时长：所需秒数 = 解说字数 / 5。匹配画面时长尽量接近，误差优先控制在 ±0.5 秒。
8. 如果一句解说太长，必须拆成多个 OST=0 片段，分别匹配不同或连续画面。
9. timestamp 必须使用对应 video_id 内部局部时间戳，不得换算为多个视频拼接后的累计时间。
10. 同一 video_id 内时间段不得交叉或重叠。
11. 第一段必须是 OST=0 解说钩子，不能直接播放原片。
12. OST=1 原声片段的总时长占比要尽量接近用户选择的 ${original_sound_ratio}%。这里按最终 items 的 timestamp 总时长估算，不按片段数量估算。OST=0 在渲染时可能按 TTS 时长拉长，因此不要只用很短的 OST=1 片段凑比例。
13. 不要自行判断或改写影视类型；画面匹配和 picture 描述要服务用户选择的 ${drama_genre} 叙事重点。
14. 有视觉证据时，picture 必须优先使用同一时间范围内可见的动作、人物、场景和道具。视觉证据不能确认的细节不得写入 picture。
15. 字幕与视觉证据冲突时，不得静默丢弃：把时间段、字幕主张、视觉观察和严重度写入 evidence_conflicts；相关具体断言不得写入 items。
16. 当“核心可输出时间范围”为有效时间段时，只能使用其中的 timestamp 生成 items；上下文时间范围只用于理解承接，不能输出为剪辑片段。
17. 每个 item 必须填写 narrative_role：承载普通剧情为 "story"；承担跨时间、地点、人物、目标或因果跳跃解释的 OST=0 解说片段为 "bridge"。桥接不能只靠原声或画面暗示。

## 原片占比规则
- ${original_sound_ratio}% = 0% 时，不要输出 OST=1，全部使用解说承接。
- 原片高光候选是表演、画面或视觉节奏比继续解说更值得观众直接体验的时间段，可包括剧情反转、关键选择、动作/追逐、情绪表演、喜剧反应、悬疑线索、仪式画面和视觉奇观；无对白片段同样可以成为 OST=1。不得仅凭视觉证据声称存在音乐、环境音或音效。
- 字幕中的关键对白可独立作为 OST=1 依据，但不能把字幕之外的声音价值归因给视觉高光候选。
- 优先从“原片高光候选”中选择 OST=1。视觉证据可以独立支持无对白的动作、表演、反应和视觉奇观；只有涉及对白或声音的主张才必须有相应证据。候选不可靠、与叙事无关或与用户文案冲突时可以不选。
- 当 ${original_sound_ratio}% 大于 0 且高光候选可用时，至少保留 3 段分散在故事不同节点的高光 OST=1（短成片可按时长减少），不要把原声全部集中在解释性对白。
- ${original_sound_ratio}% 在 10%-30% 时，优先保留高价值高光及关键对白，而非仅按对白密度挑选。
- ${original_sound_ratio}% 在 40%-60% 时，解说负责串联因果，原片负责承载高光场面、声音和对白。
- ${original_sound_ratio}% 在 70%-90% 时，以原片对白和表演为主，解说只做开场钩子、转场桥和必要补充。
- 如果原片占比与“第一段必须 OST=0”冲突，优先保证第一段是 OST=0，然后在后续片段提高 OST=1 时长占比。
- 选择高原片占比时，可以把用户文案合并成更少的 OST=0 桥段，不要为了逐句使用文案而压低原片占比。

## 字段规则
- _id：从 1 开始连续递增。
- video_id：来自字幕分段标题，例如“视频 2”就填 2。
- video_name：对应视频文件名，必须从字幕分段标题提取。
- timestamp：格式为 "HH:MM:SS,mmm-HH:MM:SS,mmm"。
- picture：描述匹配画面中人物、动作、情绪、场景和关键道具。
- narration：OST=0 时填写用户文案片段；OST=1 时填写“播放原片+_id”。
- OST：解说片段填 0，原声片段填 1。
- narrative_role："story" 或 "bridge"。

## 输出格式
只输出严格 JSON：

{
  "items": [
    {
      "_id": 1,
      "video_id": 1,
      "video_name": "1.mp4",
      "timestamp": "00:00:01,000-00:00:06,000",
      "picture": "主角站在走廊尽头，回头看向紧闭的房门",
      "narration": "他以为自己终于逃出了那间房，可真正的危险，其实才刚刚醒来。",
      "OST": 0,
      "narrative_role": "story"
    }
  ],
  "evidence_conflicts": [
    {
      "video_name": "1.mp4",
      "time_range": "00:01:00,000-00:01:05,000",
      "subtitle_claim": "字幕所支持的具体主张",
      "visual_observation": "同一时段画面可确认的观察",
      "severity": "low|medium|high",
      "status": "unresolved",
      "related_script_item_ids": [],
      "related_candidate_ids": []
    }
  ]
}

现在请基于用户审核后的解说文案生成最终剪辑脚本。"""

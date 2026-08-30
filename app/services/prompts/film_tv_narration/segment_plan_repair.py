#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""Single-pass targeted repair prompt for rejected Fusion Segment Plans."""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class SegmentPlanRepairPrompt(ParameterizedPrompt):
    """Repair structural or continuity findings without replanning the film."""

    def __init__(self):
        metadata = PromptMetadata(
            name="segment_plan_repair",
            category="film_tv_narration",
            version="v1.0",
            description="根据结构或连续性诊断定向修复影视解说分段计划",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["影视", "叙事连续性", "分段计划", "修复"],
            parameters=[
                "plan_payload", "continuity_findings", "subtitle_content",
                "visual_evidence", "highlight_candidates",
            ],
        )
        super().__init__(metadata, required_parameters=["plan_payload", "continuity_findings"])
        self._system_prompt = (
            "你是影视分段计划修复师。只修复给定计划中的结构或连续性诊断问题，"
            "严格输出 JSON，不能输出 Markdown 或说明。"
        )

    def get_template(self) -> str:
        return """# Fusion Segment Plan 单次定向修复

以下计划未通过确定性结构或连续性校验。只进行这一次修复；不得重新规划无关段落，也不得改变 narration 的总句子覆盖范围或成功段的核心范围。结构诊断要求拆分或合并问题段时，可以调整受影响段及必要相邻段的 segment_id、句子边界和 Core Window，但必须保持连续、完整、无重叠。

## 被拒绝的计划
<plan>
${plan_payload}
</plan>

## 必须修复的结构或连续性诊断
<findings>
${continuity_findings}
</findings>

## 相关字幕证据
<subtitles>
${subtitle_content}
</subtitles>

## 相关视觉证据（仅能支持可见画面事实）
<visual_evidence>
${visual_evidence}
</visual_evidence>

## 高光候选（只可辅助选择，不能替代必要铺垫或后果）
<highlight_candidates>
${highlight_candidates}
</highlight_candidates>

## 修复规则
1. 仅依据给出的字幕和可见视觉事实；不能从画面推断对白、声音、动机或画外事件。
2. 为缺失的 Story Beat 字段补齐 active_subject、entering_state、trigger_event、exiting_state。
3. 时间正向跳跃超过 150 秒时，在前一段写 bridge_to_next=true 和具体 bridge_reason，说明时间、地点、人物状态、目标或因果交接。
4. 时间倒退必须在倒退段填写 narrative_mode=flashback、flashforward、montage 或 recap，并给出能让观众理解跳转的 narration_cue。
5. 除第一段外，补齐 handoff_from_previous 的 actor、place、goal、cause、state；每项只能是 continuous 或 changed。任一项 changed 时，上一段必须有明确 bridge_to_next=true 和 bridge_reason。
6. 每段通常覆盖 3-8 句。超出范围时必须拆分/合并，或仅在真实叙事边界无法安全拆分时填写具体、可审计且由现有计划和证据支持的 exception_reason；禁止使用“系统要求”“为了通过校验”等虚假理由。
7. 修复后必须从第 1 句开始、顺序且完整覆盖全部 narration 句子，不得遗漏、重复或制造重叠 Core Window。
8. 原样输出完整 {"segments":[...]} JSON，不包含其他键或文字。
"""

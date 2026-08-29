#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""Single-pass targeted repair prompt for rejected Fusion Segment Plans."""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class SegmentPlanRepairPrompt(ParameterizedPrompt):
    """Repair continuity fields without turning the plan into a fresh full-film match."""

    def __init__(self):
        metadata = PromptMetadata(
            name="segment_plan_repair",
            category="film_tv_narration",
            version="v1.0",
            description="根据连续性诊断定向修复影视解说分段计划",
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
            "你是影视叙事连续性修复师。只修复给定计划中的诊断问题，"
            "严格输出 JSON，不能输出 Markdown 或说明。"
        )

    def get_template(self) -> str:
        return """# Fusion Segment Plan 单次定向修复

以下计划未通过确定性连续性校验。只进行这一次修复；不得重新规划无关段落，也不得改变 narration 的句子覆盖范围、segment_id 或成功段的核心范围，除非修复诊断本身必须调整相邻段的桥接字段。

## 被拒绝的计划
<plan>
${plan_payload}
</plan>

## 必须修复的连续性诊断
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
5. 保留每段 3-8 句限制及已有 exception_reason；不要制造重叠 Core Window。
6. 原样输出完整 {"segments":[...]} JSON，不包含其他键或文字。
"""

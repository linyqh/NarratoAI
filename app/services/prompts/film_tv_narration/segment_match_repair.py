#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""Bounded repair prompt for one affected Segment Match."""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class SegmentMatchRepairPrompt(ParameterizedPrompt):
    def __init__(self):
        metadata = PromptMetadata(
            name="segment_match_repair",
            category="film_tv_narration",
            version="v1.0",
            description="使用受影响证据窗口修复单个影视解说匹配段",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["影视", "叙事连续性", "定向修复"],
            parameters=[
                "drama_name", "drama_genre", "plot_analysis", "previous_script",
                "continuity_finding", "subtitle_content", "visual_evidence",
                "highlight_candidates", "core_window", "narration_language",
            ],
        )
        super().__init__(metadata, required_parameters=["previous_script", "continuity_finding"])
        self._system_prompt = (
            "你是影视解说剪辑的连续性修复师。仅输出严格 JSON，不能输出 Markdown 或说明。"
        )

    def get_template(self) -> str:
        return """# 单个 Segment Match 的一次定向修复

只修复此受影响段，保留其他 Segment Match。不重写用户已审核的解说文案，也不要使用下面 Evidence Window 以外的事实。

<previous_script>
${previous_script}
</previous_script>

<continuity_finding>
${continuity_finding}
</continuity_finding>

<subtitles>
${subtitle_content}
</subtitles>

<visual_evidence>
${visual_evidence}
</visual_evidence>

<highlight_candidates>
${highlight_candidates}
</highlight_candidates>

核心可输出时间范围：${core_window}

规则：所有 timestamp 必须落在核心范围内。需要跨越跳跃时，输出一个 OST=0、带 narration 的桥接 item，并将 narrative_role 填为 "bridge"；其他 item 填 "story"。Visual Evidence 只可支持画面可见事实，不得推断声音、对白、动机或画外事件。

只输出：
{"items":[{"video_id":1,"video_name":"1.mp4","timestamp":"00:00:00,000-00:00:05,000","picture":"可见画面","narration":"桥接解说","OST":0,"narrative_role":"bridge"}],"evidence_conflicts":[]}
"""

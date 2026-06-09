#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧解说-脚本修复
@File   : script_repair.py
@Description: 短剧解说脚本校验失败后的JSON修复提示词
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptRepairPrompt(ParameterizedPrompt):
    """短剧解说脚本修复提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_repair",
            category="short_drama_narration",
            version="v1.0",
            description="根据确定性校验错误修复短剧解说脚本JSON，优先修正时间戳、视频来源和格式问题",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "解说脚本", "JSON修复", "时间戳校验", "多视频"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "invalid_script",
                "validation_errors",
                "narration_language",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=["drama_name", "subtitle_content", "invalid_script", "validation_errors"],
        )

        self._system_prompt = (
            "你是一位短剧解说脚本JSON修复器。你只能根据校验错误修复JSON，"
            "必须输出严格JSON，不能输出解释、Markdown或代码块。"
        )

    def get_template(self) -> str:
        return """# 短剧解说脚本修复任务

## 修复目标
下面的短剧《${drama_name}》解说脚本未通过剪辑校验。请只根据校验错误和字幕内容修复它，输出一个完整可剪辑的 JSON。

## 剧情理解材料
<plot>
${plot_analysis}
</plot>

## 校验错误
<validation_errors>
${validation_errors}
</validation_errors>

## 当前无效脚本
<invalid_script>
${invalid_script}
</invalid_script>

## 可用字幕窗口
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

## 修复规则
1. 只输出 JSON，不要任何解释、标题、Markdown 或代码块。
2. 输出根对象必须是 {"items": [...]}。
3. 每个 item 必须包含 _id、video_id、video_name、timestamp、picture、narration、OST。
4. video_id、video_name 和 timestamp 必须来自对应字幕窗口；不得把不同视频的同名时间戳混用。
5. 同一 video_id 内片段不得交叉或重叠。
6. OST=1 的 narration 必须是“播放原片+序号”；OST=0 的 narration 必须使用 ${narration_language}。
7. 禁止连续 3 个或更多 OST=1；必须插入或改写 OST=0 解说片段承接剧情。
8. 跨 video_id 切换前后不能都是 OST=1；必须至少有一个 OST=0 片段解释场景和剧情为什么切换。
9. OST=0 narration 要补足因果承接，不要只概括当前画面。
10. 第一段必须是 OST=0 解说钩子，按“高能反转 + 情绪冲突 + 悬念钩子”写，不要直接播放原片。
11. OST=0 文案必须匹配画面时长，按“解说字数 / 5 = 所需视频秒数”估算；过密时要缩短文案、延长时间戳或拆成多个片段。
12. 不要自行改判短剧类型；如需改写 narration，必须按用户选择的 ${drama_genre} 保持表达重点。
13. 尽量保留原脚本中没有错误的片段；无法修复的片段可以删除，但剩余片段必须重新按 1 开始编号。

请输出修复后的完整 JSON。"""

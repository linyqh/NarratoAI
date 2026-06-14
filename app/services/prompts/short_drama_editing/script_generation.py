#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧混剪-剪辑脚本生成
@File   : script_generation.py
@Description: 基于剧情理解和字幕直接生成短剧混剪脚本
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptGenerationPrompt(ParameterizedPrompt):
    """短剧混剪脚本生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_generation",
            category="short_drama_editing",
            version="v1.0",
            description="基于剧情理解和原始字幕直接生成短剧混剪脚本，不生成解说文案",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "混剪", "剪辑脚本", "时间戳", "多视频", "原声"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "custom_clips",
            ],
        )
        super().__init__(
            metadata,
            required_parameters=["plot_analysis", "subtitle_content", "custom_clips"],
        )

        self._system_prompt = (
            "你是一名专业短剧混剪剪辑师。你必须严格输出JSON，"
            "只从字幕中选择真实存在的可剪辑原声片段，不生成解说文案。"
        )

    def get_template(self) -> str:
        return """# 短剧混剪脚本生成任务

## 目标
根据剧情理解和原始字幕，为短剧《${drama_name}》生成一份可直接裁剪的混剪 JSON 脚本。

短剧混剪与短剧解说的区别：
- 不生成解说文案。
- 不需要用户审核旁白。
- 直接从剧情理解中选择能串成故事线的原片片段。
- 每个片段默认保留原声，OST 必须为 1。

## 用户选择的短剧类型
<drama_genre>
${drama_genre}
</drama_genre>

## 需要生成的片段数量
<custom_clips>
${custom_clips}
</custom_clips>

## 剧情理解材料
<plot>
${plot_analysis}
</plot>

## 原始字幕（含视频编号和局部时间戳）
<subtitles>
${subtitle_content}
</subtitles>

## 选择原则
1. 选择 ${custom_clips} 个片段，尽量形成“开端 -> 冲突升级 -> 高潮/反转 -> 悬念或阶段结果”的完整观看路径。
2. 只能使用原始字幕中真实存在的视频编号、视频文件名和时间范围。
3. timestamp 必须是对应 video_id 内部的局部时间戳，格式为 "HH:MM:SS,mmm-HH:MM:SS,mmm"。
4. 同一个 video_id 内的片段不得交叉或重叠；整体顺序要服务剧情理解，单个视频内尽量按时间顺序。
5. 优先选择关键对白、身份揭露、情绪爆发、反转、冲突升级和能看懂前因后果的片段。
6. 单个片段建议 5-45 秒；不要只截 1-2 秒的孤立金句，也不要截过长的流水账。
7. 如果两个关键剧情之间跳跃太大，优先选择包含上下文的连续时间段，而不是硬切爆点。
8. picture 要描述画面中人物、动作、情绪、场景和该片段的剧情作用。
9. narration 字段必须写成“播放原片+_id”，例如 _id 为 3 时写“播放原片3”。
10. OST 必须为 1，表示保留原片原声。

## 字段规则
- _id：从 1 开始连续递增。
- video_id：来自字幕分段标题，例如“视频 2”就填 2；单视频填 1。
- video_name：对应视频文件名，必须从字幕分段标题提取；单视频也要填写。
- timestamp：必须来自对应视频字幕时间轴。
- picture：非空字符串。
- narration：固定为“播放原片+_id”。
- OST：固定为 1。

## 输出格式
只输出严格 JSON：

{
  "items": [
    {
      "_id": 1,
      "video_id": 1,
      "video_name": "1.mp4",
      "timestamp": "00:00:01,000-00:00:12,500",
      "picture": "女主被当众羞辱仍然强撑，冲突正式爆发，为后续逆袭埋下情绪钩子",
      "narration": "播放原片1",
      "OST": 1
    }
  ]
}

现在请生成短剧混剪脚本。"""

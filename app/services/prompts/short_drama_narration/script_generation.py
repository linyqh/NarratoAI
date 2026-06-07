#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 短剧解说-文案画面匹配
@File   : script_generation.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 短剧解说脚本生成提示词 - 优化版本
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptGenerationPrompt(ParameterizedPrompt):
    """短剧解说脚本生成提示词 - 优化版本"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_generation",
            category="short_drama_narration",
            version="v2.1",
            description="基于已规划片段生成高质量短剧解说脚本，重点补足剧情承接、因果解释和观众理解路径",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["短剧", "解说脚本", "文案生成", "原声片段", "黄金开场", "爽点放大", "个性吐槽", "悬念预埋"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "segment_plan",
                "narration_language",
            ]
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis", "segment_plan"])
        
        self._system_prompt = (
            "你是一位短剧解说文案写手。你必须严格按照JSON格式输出，"
            "只能补充picture和narration，不能改动上游片段规划中的_id、video_id、video_name、timestamp和OST。"
        )
        
    def get_template(self) -> str:
        return """# 短剧解说脚本文案生成任务

## 任务目标
为短剧《${drama_name}》生成最终可剪辑解说脚本。片段已经由上游规划完成，你只能补充 picture 和 narration，不能改变片段来源和时间戳。

## 输入材料

### 剧情概述
<plot>
${plot_analysis}
</plot>

### 已规划片段（必须逐项照抄结构字段）
<segment_plan>
${segment_plan}
</segment_plan>

### 原始字幕（含视频编号和精确时间戳）
<subtitles>
${subtitle_content}
</subtitles>

### 解说台词语言
<narration_language>
${narration_language}
</narration_language>

### 用户选择的短剧类型
<drama_genre>
${drama_genre}
</drama_genre>

字幕可能来自多个视频文件。每个字幕分段标题会以“视频 1: 文件名”“视频 2: 文件名”等形式标识来源。
生成脚本时必须把每个片段绑定到对应视频来源，时间戳表示该视频文件内部的局部时间，不是把多个视频拼接后的全局时间。
所有 OST=0 的 narration 字段必须使用上方指定的解说台词语言输出；不要因为原始字幕是其他语言就切回字幕原语言。
OST=1 的原声片段 narration 字段必须继续使用“播放原片+序号”格式，不要翻译这个固定标记。

## 绝对绑定规则
1. 输出 items 数量、顺序和 _id 必须与 segment_plan 完全一致。
2. 每个 item 的 _id、video_id、video_name、timestamp、OST 必须逐字复制 segment_plan，不得新增、删除、合并、拆分或改动。
3. 你只能补充 picture 和 narration 两个字段。
4. OST=1 的 narration 必须写成“播放原片+_id”，例如 _id 为 5 时写“播放原片5”。
5. OST=0 的 narration 必须使用 ${narration_language}，并严格基于剧情和字幕，不虚构字幕外的具体事件。

## 叙事连续性要求
- 你必须把每个 OST=0 当成“观众理解剧情的桥”，不能只概括当前画面。
- 每个 OST=0 narration 要尽量回答：上一段发生了什么、为什么会发展到这一段、这一段带来什么新矛盾。
- 跨 video_id 或跨时间大跳跃时，OST=0 必须明确补出承接句，例如“可这段婚姻真正难的不是相爱，而是两个孩子和婆婆都还没接纳她”。
- 原声片段前后的 OST=0 要解释原声的重要性，避免观众只看到对白片段合集。
- 如果 segment_plan 中有 story_role、intent、transition 字段，必须利用它们组织 narration，但不要把这些字段输出到最终 JSON。
- 结尾 OST=0 要留下后续阻力或悬念；如果结尾是 OST=1，则前一个 OST=0 必须提前点出这段原声会把矛盾推向哪里。

## 开头钩子要求
- 第一段必须是 OST=0 解说钩子，不能直接播放原片。
- 开头用“高能反转 + 情绪冲突 + 悬念钩子”：强身份/强处境 + 致命反差 + 后续悬念。
- 写法示例方向：一个刚立功的兵王，下一秒却被迫脱下军装；他回家的第一天，家里的钱和尊严都被赌桌吞了。
- 示例只用于理解公式，必须基于当前字幕事实原创，不要夸大到字幕没有的情节。

## 解说密度与画面节奏
- OST=0 文案必须能被当前 timestamp 的画面承载，按“解说字数 / 5 = 所需视频秒数”估算。
- 如果画面只有 6 秒，就不要写 80 字；应压缩到约 30 字，或依赖 segment_plan 选择更长画面。
- 优先短句，单句只表达一个信息点；不要把人物介绍、前因、反转和悬念全塞进一个短画面。
- 长信息要拆成多段，每段只承担一个叙事功能，让画面节奏跟上解说。

## 用户选择类型文案规则
短剧类型由用户手动选择为 ${drama_genre}，不得自行改判。必须按对应方向写：
- 霸总/甜宠：突出误会、身份差、暧昧拉扯、守护感和情绪反差。
- 逆袭/复仇：突出羞辱、反击、打脸、身份揭露和爽点升级。
- 家庭伦理：突出亲情撕扯、秘密、委屈、选择和道德冲突。
- 古装/权谋：突出身份、局势、算计、立场和反转。
- 悬疑/犯罪：突出线索、危机、动机和未揭开的疑问。
- 都市情感：突出关系裂痕、现实压力、误会和情绪拉扯。
- 年代/乡村：突出家庭处境、人情压力、生活困境和命运转折。
- 自定义类型：严格服从用户填写的类型方向。

## 文案质量要求
- 开场片段要有强钩子，直接点出冲突、悬念或情绪爆点。
- 每段解说优先 25-90 字，具体长度必须服从画面时长；短画面宁可少说，不要密集灌信息。
- 可以使用“没想到”“可下一秒”“而这时”“真正的问题来了”等短剧转折语，但不要堆砌。
- picture 要描述画面和人物状态，便于后期识别素材。
- 少用孤立信息句，多用承接句；不要让观众感觉剧情突然跳场。
- 不要解释规则，不要输出 Markdown，不要输出代码块。

## 输出格式

请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：

{
  "items": [
    {
        "_id": 1,
        "video_id": 1,
        "video_name": "1.mp4",
        "timestamp": "00:00:01,000-00:00:05,500",
        "picture": "女主角林小雨慌张地道歉，男主角沈墨轩冷漠地看着她",
        "narration": "一个普通女孩的命运即将因为一杯咖啡彻底改变！她撞到的这个男人，竟然是...",
        "OST": 0
    },
    {
        "_id": 2,
        "video_id": 1,
        "video_name": "1.mp4",
        "timestamp": "00:00:05,500-00:00:08,000",
        "picture": "沈墨轩质问林小雨，语气冷厉威严",
        "narration": "播放原片2",
        "OST": 1
    },
    {
        "_id": 3,
        "video_id": 2,
        "video_name": "2.mp4",
        "timestamp": "00:00:08,000-00:00:12,000",
        "picture": "林小雨惊慌失措，沈墨轩眼中闪过一丝兴趣",
        "narration": "霸道总裁的经典开场！一杯咖啡引发的爱情故事就这样开始了...",
        "OST": 0
    }
  ]
}

现在请基于以上要求，为短剧《${drama_name}》创作解说脚本："""

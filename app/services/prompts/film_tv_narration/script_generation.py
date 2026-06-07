#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 影视解说-文案画面匹配
@File   : script_generation.py
@Description: 影视解说脚本生成提示词
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class ScriptGenerationPrompt(ParameterizedPrompt):
    """影视解说脚本生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="script_generation",
            category="film_tv_narration",
            version="v1.0",
            description="基于已规划片段生成高质量影视解说脚本，重点补足人物动机、信息承接和剧情因果",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            tags=["影视", "解说脚本", "文案生成", "原声片段", "悬念", "名场面"],
            parameters=[
                "drama_name",
                "drama_genre",
                "plot_analysis",
                "subtitle_content",
                "segment_plan",
                "narration_language",
            ],
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis", "segment_plan"])

        self._system_prompt = (
            "你是一位影视解说文案写手。你必须严格按照JSON格式输出，"
            "只能补充picture和narration，不能改动上游片段规划中的_id、video_id、video_name、timestamp和OST。"
        )

    def get_template(self) -> str:
        return """# 影视解说脚本文案生成任务

## 任务目标
为影视作品《${drama_name}》生成最终可剪辑解说脚本。片段已经由上游规划完成，你只能补充 picture 和 narration，不能改变片段来源和时间戳。

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

### 用户选择的影视类型
<drama_genre>
${drama_genre}
</drama_genre>

字幕可能来自多个视频文件。每个字幕分段标题会以“视频 1: 文件名”“视频 2: 文件名”等形式标识来源。
生成脚本时必须把每个片段绑定到对应视频来源，时间戳表示该视频文件内部的局部时间，不是把多个视频拼接后的全局时间。
所有 OST=0 的 narration 字段必须使用上方指定的解说台词语言输出；不要因为原始字幕是其他语言就切回字幕原语言。
OST=1 的原声片段 narration 字段必须继续使用“播放原片+序号”格式，不要翻译这个固定标记。

## 绝对绑定规则
0. 最高优先级：如果 segment_plan 中混入片头、片尾、演职员表、版权声明、平台水印展示、下集预告、花絮、赞助口播、商品露出、贴片广告、中插广告、片中广告或任何与主线剧情无关的推广片段，必须直接删除这些片段，绝对不能输出到最终 items；此规则高于下面所有“照抄 segment_plan”的绑定规则。
1. 除被第 0 条删除的片头、片尾和广告片段外，输出 items 数量、顺序和 _id 必须与 segment_plan 完全一致。
2. 除被第 0 条删除的片头、片尾和广告片段外，每个 item 的 _id、video_id、video_name、timestamp、OST 必须逐字复制 segment_plan，不得新增、合并、拆分或改动。
3. 你只能补充 picture 和 narration 两个字段。
4. OST=1 的 narration 必须写成“播放原片+_id”，例如 _id 为 5 时写“播放原片5”。
5. OST=0 的 narration 必须使用 ${narration_language}，并严格基于剧情和字幕，不虚构字幕外的具体事件。

## 叙事连续性要求
- 你必须把每个 OST=0 当成“观众理解剧情的桥”，不能只概括当前画面。
- 每个 OST=0 narration 要尽量回答：上一段发生了什么、人物为什么这么做、这一段带来什么新信息或新危机。
- 跨 video_id 或跨时间大跳跃时，OST=0 必须明确补出承接句，例如“真正危险的不是这场争吵，而是他终于发现证据指向了身边人”。
- 原声片段前后的 OST=0 要解释原声的重要性，避免观众只看到对白片段合集。
- 如果 segment_plan 中有 story_role、intent、transition 字段，必须利用它们组织 narration，但不要把这些字段输出到最终 JSON。
- 结尾 OST=0 要留下后续阻力、真相疑问或人物选择；如果结尾是 OST=1，则前一个 OST=0 必须提前点出这段原声会把矛盾推向哪里。

## 开头钩子要求
- 第一段必须是 OST=0 解说钩子，不能直接播放原片。
- 开头用“人物困境 + 反常信息 + 悬念问题”：主角压力 + 异常线索/关系突变 + 后续疑问。
- 写法示例方向：他以为这只是一次普通问询，可一句话之后，所有证据都指向了他最信任的人。
- 示例只用于理解公式，必须基于当前字幕事实原创，不要夸大到字幕没有的情节。

## 解说密度与画面节奏
- OST=0 文案必须能被当前 timestamp 的画面承载，按“解说字数 / 5 = 所需视频秒数”估算。
- 如果画面只有 6 秒，就不要写 80 字；应压缩到约 30 字，或依赖 segment_plan 选择更长画面。
- 优先短句，单句只表达一个信息点；不要把人物介绍、前因、反转和悬念全塞进一个短画面。
- 长信息要拆成多段，每段只承担一个叙事功能，让画面节奏跟上解说。

## 用户选择类型文案规则
影视类型由用户手动选择为 ${drama_genre}，不得自行改判。必须按对应方向写：
- 剧情/情感：突出人物选择、关系裂痕、命运压力和情绪余波。
- 悬疑/犯罪：突出线索、疑点、动机、误导和未揭开的真相。
- 动作/冒险：突出目标、危险升级、身体对抗和关键抉择。
- 喜剧/轻松：突出误会、反差、节奏包袱和人物可爱处。
- 科幻/奇幻：突出设定规则、未知威胁、世界观反差和代价。
- 历史/战争：突出时代处境、阵营选择、牺牲和局势变化。
- 恐怖/惊悚：突出异常细节、压迫感、未知危险和心理悬念。
- 自定义类型：严格服从用户填写的类型方向。

## 文案质量要求
- 开场片段要有强钩子，直接点出冲突、疑点或人物困境。
- 最终剪辑脚本不得包含片头、片尾或任何广告片段；如果字幕内容明显属于非剧情推广，不要把它包装成剧情解说。
- 每段解说优先 25-90 字，具体长度必须服从画面时长；短画面宁可少说，不要密集灌信息。
- 可以使用“可真正的问题是”“而他还不知道”“这句话背后”“危险已经开始靠近”等影视解说转折语，但不要堆砌。
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
        "picture": "男主站在审讯室门口，神情紧张地看向桌上的证据袋",
        "narration": "他以为这只是一次普通问询，可桌上的证据却把所有矛头指向了自己。",
        "OST": 0
    },
    {
        "_id": 2,
        "video_id": 1,
        "video_name": "1.mp4",
        "timestamp": "00:00:05,500-00:00:08,000",
        "picture": "警官低声质问，男主沉默不语",
        "narration": "播放原片2",
        "OST": 1
    }
  ]
}

现在请基于以上要求，为影视作品《${drama_name}》创作解说脚本："""

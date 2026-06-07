#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: 影视解说-解说文案
@File   : narration_copy.py
@Description: 生成可供用户审核修改的影视解说正文
"""

from ..base import ParameterizedPrompt, PromptMetadata, ModelType, OutputFormat


class NarrationCopyPrompt(ParameterizedPrompt):
    """影视解说正文生成提示词"""

    def __init__(self):
        metadata = PromptMetadata(
            name="narration_copy",
            category="film_tv_narration",
            version="v1.0",
            description="基于剧情理解和字幕生成可审核修改的影视解说正文，不绑定时间戳",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.TEXT,
            tags=["影视", "解说文案", "电影解说", "剧情承接", "用户审核"],
            parameters=["drama_name", "drama_genre", "plot_analysis", "subtitle_content", "narration_language"],
        )
        super().__init__(metadata, required_parameters=["drama_name", "plot_analysis", "subtitle_content"])

        self._system_prompt = (
            "你是一位影视解说文案创作者。你只输出可供用户审核修改的解说正文，"
            "不要输出JSON、时间戳、编号、标题、解释或Markdown。"
        )

    def get_template(self) -> str:
        return """# 影视解说正文创作任务

## 目标
为影视作品《${drama_name}》创作一份可直接给用户审核修改的解说文案正文。此阶段不做画面匹配，不输出时间戳。

## 剧情理解材料
<plot>
${plot_analysis}
</plot>

## 原始字幕
<subtitles>
${subtitle_content}
</subtitles>

## 输出语言
<narration_language>
${narration_language}
</narration_language>

## 用户选择的影视类型
<drama_genre>
${drama_genre}
</drama_genre>

## 类型写作规则
必须按用户选择的影视类型调整表达重点，不要自行改判类型：
- 剧情/情感：突出人物选择、关系裂痕、命运压力和情绪余波。
- 悬疑/犯罪：突出线索、疑点、动机、误导和未揭开的真相。
- 动作/冒险：突出目标、危险升级、身体对抗和关键抉择。
- 喜剧/轻松：突出误会、反差、节奏包袱和人物可爱处。
- 科幻/奇幻：突出设定规则、未知威胁、世界观反差和代价。
- 历史/战争：突出时代处境、阵营选择、牺牲和局势变化。
- 恐怖/惊悚：突出异常细节、压迫感、未知危险和心理悬念。
- 自定义类型：严格服从用户填写的类型方向。

## 开头钩子公式
开头必须使用“人物困境 + 反常信息 + 悬念问题”：
1. 先点出主角或关键人物正在面对什么压力。
2. 再抛出一个违背常识、关系突变或危险升级的信息。
3. 最后留下观众想继续看的问题：他为什么这样做、谁在撒谎、这场选择会把所有人推向哪里。

## 写作规则
1. 必须使用 ${narration_language}。
2. 严格基于剧情理解和字幕事实，不编造核心情节、身份、结局。
3. 先写清楚人物动机和因果链，再写情绪金句；不要只堆形容词。
4. 每句话只表达一个信息点，适合后续按句匹配画面。
5. 句子尽量短，单句优先 15-35 字；信息复杂时拆成多句。
6. 每 2-3 句要有明确承接，让观众知道为什么从上一幕来到下一幕。
7. 总长度控制在 350-750 字；短素材取下限，长素材取上限。
8. 不要使用编号、项目符号、章节标题或括号说明。

## 输出要求
只输出解说正文。不要输出 JSON、时间戳、代码块或任何解释。"""

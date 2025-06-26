#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : 生成介绍文案
@Author : 小林同学
@Date   : 2025/5/8 上午11:33 
'''

import json
import os
import traceback
from openai import OpenAI
from loguru import logger


def parse_frame_analysis_to_markdown(json_file_path):
    """
    解析视频帧分析JSON文件并转换为Markdown格式
    
    :param json_file_path: JSON文件路径
    :return: Markdown格式的字符串
    """
    # 检查文件是否存在
    if not os.path.exists(json_file_path):
        return f"错误: 文件 {json_file_path} 不存在"
    
    try:
        # 读取JSON文件
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        # 初始化Markdown字符串
        markdown = ""
        
        # 获取总结和帧观察数据
        summaries = data.get('overall_activity_summaries', [])
        frame_observations = data.get('frame_observations', [])
        
        # 按批次组织数据
        batch_frames = {}
        for frame in frame_observations:
            batch_index = frame.get('batch_index')
            if batch_index not in batch_frames:
                batch_frames[batch_index] = []
            batch_frames[batch_index].append(frame)
        
        # 生成Markdown内容
        for i, summary in enumerate(summaries, 1):
            batch_index = summary.get('batch_index')
            time_range = summary.get('time_range', '')
            batch_summary = summary.get('summary', '')
            
            markdown += f"## 片段 {i}\n"
            markdown += f"- 时间范围：{time_range}\n"
            
            # 添加片段描述
            markdown += f"- 片段描述：{batch_summary}\n" if batch_summary else f"- 片段描述：\n"
            
            markdown += "- 详细描述：\n"
            
            # 添加该批次的帧观察详情
            frames = batch_frames.get(batch_index, [])
            for frame in frames:
                timestamp = frame.get('timestamp', '')
                observation = frame.get('observation', '')
                
                # 直接使用原始文本，不进行分割
                markdown += f"  - {timestamp}: {observation}\n" if observation else f"  - {timestamp}: \n"
            
            markdown += "\n"
        
        return markdown
    
    except Exception as e:
        return f"处理JSON文件时出错: {traceback.format_exc()}"


def generate_narration(markdown_content, api_key, base_url, model,custom_prompt,video_theme):
    """
    调用OpenAI API根据视频帧分析的Markdown内容生成解说文案
    
    :param markdown_content: Markdown格式的视频帧分析内容
    :param api_key: OpenAI API密钥
    :param base_url: API基础URL，如果使用非官方API
    :param model: 使用的模型名称
    :return: 生成的解说文案
    """
    try:
        # 构建提示词
        prompt = """
<video_frame_description>
%s
</video_frame_description>

<video_theme>
%s
</video_theme>
<custom_prompt>
%s
</custom_prompt>
我正在尝试做这个内容的解说纪录片视频，我需要你以 <video_frame_description> </video_frame_description> 中的内容为解说目标，
<video_theme></video_theme>为主题，<custom_prompt></custom_prompt>为特点和要求
根据我刚才提供给你的要求，以及你总结的特点，帮我生成一段关于这个视频的解说文案，文案需要符合平台受欢迎的解说风格，请使用 json 格式进行输出；使用 <output> 中的输出格式，注意格式必须标准：

<output>
{
  "items": [
    {
        "_id": 1, # 唯一递增id
        "timestamp": "00:00:05,390-00:00:10,430",
        "picture": "画面描述",
        "narration": "解说文案",
    }
}
</output>

<restriction>
1. 只输出 json 内容，不要输出其他任何说明性的文字
2. 解说文案的语言使用 简体中文
3. 严禁虚构画面，所有画面只能从 <video_frame_description> 中摘取
4. 尽量分段概括整个视频
</restriction>
""" % (markdown_content,video_theme,custom_prompt)

        # 使用OpenAI SDK初始化客户端
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        if model not in ["deepseek-reasoner"]:
            print(f"使用模型: 普通")
            # deepseek-reasoner 不支持 json 输出
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一名专业的短视频解说文案撰写专家。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=1.5,
                response_format={"type": "json_object"},
            )
            # 提取生成的文案
            if response.choices and len(response.choices) > 0:
                narration_script = response.choices[0].message.content
                # 打印消耗的tokens
                logger.debug(f"消耗的tokens: {response.usage.total_tokens}")
                return narration_script
            else:
                return "生成解说文案失败: 未获取到有效响应"
        else:
            # 不支持 json 输出，需要多一步处理 ```json ``` 的步骤
            print(f"使用模型: 特别")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一名专业的短视频解说文案撰写专家。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=1.5,
            )
            # 提取生成的文案
            if response.choices and len(response.choices) > 0:
                narration_script = response.choices[0].message.content
                # 打印消耗的tokens
                logger.debug(f"文案消耗的tokens: {response.usage.total_tokens}")
                # 清理 narration_script 字符串前后的 ```json ``` 字符串
                narration_script = narration_script.replace("```json", "").replace("```", "")
                return narration_script
            else:
                return "生成解说文案失败: 未获取到有效响应"
    
    except Exception as e:
        return f"调用API生成解说文案时出错: {traceback.format_exc()}"
        

if __name__ == '__main__':
    text_provider = 'openai'
    text_api_key = "sk-xxx"
    text_model = "deepseek-reasoner"
    text_base_url = "https://api.deepseek.com"
    video_frame_description_path = "/Users/apple/Desktop/home/NarratoAI/storage/temp/analysis/frame_analysis_20250508_1139.json"

    # 测试新的JSON文件
    test_file_path = "/Users/apple/Desktop/home/NarratoAI/storage/temp/analysis/frame_analysis_20250508_2258.json"
    markdown_output = parse_frame_analysis_to_markdown(test_file_path)
    # print(markdown_output)
    
    # 输出到文件以便检查格式
    output_file = "/Users/apple/Desktop/home/NarratoAI/storage/temp/家里家外1-5.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_output)
    # print(f"\n已将Markdown输出保存到: {output_file}")
    
    # # 生成解说文案
    # narration = generate_narration(
    #     markdown_output,
    #     text_api_key,
    #     base_url=text_base_url,
    #     model=text_model
    # )
    #
    # # 保存解说文案
    # print(narration)
    # print(type(narration))
    # narration_file = "/Users/apple/Desktop/home/NarratoAI/storage/temp/final_narration_script.json"
    # with open(narration_file, 'w', encoding='utf-8') as f:
    #     f.write(narration)
    # print(f"\n已将解说文案保存到: {narration_file}")

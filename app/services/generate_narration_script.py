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
            
            # 处理可能过长的文本行，保证格式对齐
            batch_summary_lines = [batch_summary[i:i+80] for i in range(0, len(batch_summary), 80)]
            
            markdown += f"## 片段 {i}\n"
            markdown += f"- 时间范围：{time_range}\n"
            
            # 添加片段描述，处理长文本
            markdown += f"- 片段描述：{batch_summary_lines[0]}\n" if batch_summary_lines else f"- 片段描述：\n"
            for line in batch_summary_lines[1:]:
                markdown += f"  {line}\n"
            
            markdown += "- 详细描述：\n"
            
            # 添加该批次的帧观察详情
            frames = batch_frames.get(batch_index, [])
            for frame in frames:
                timestamp = frame.get('timestamp', '')
                observation = frame.get('observation', '')
                
                # 处理可能过长的观察文本，并确保observation不为空
                observation_lines = [observation[i:i+80] for i in range(0, len(observation), 80)] if observation else [""]
                markdown += f"  - {timestamp}: {observation_lines[0] if observation_lines else ''}\n"
                for line in observation_lines[1:]:
                    markdown += f"    {line}\n"
            
            markdown += "\n"
        
        return markdown
    
    except Exception as e:
        return f"处理JSON文件时出错: {traceback.format_exc()}"


if __name__ == '__main__':
    video_frame_description_path = "/Users/apple/Desktop/home/NarratoAI/storage/temp/analysis/frame_analysis_20250508_1139.json"
    
    # 测试新的JSON文件
    test_file_path = "/Users/apple/Desktop/home/NarratoAI/storage/temp/analysis/frame_analysis_20250508_1458.json"
    markdown_output = parse_frame_analysis_to_markdown(test_file_path)
    print(markdown_output)
    
    # 输出到文件以便检查格式
    output_file = "/Users/apple/Desktop/home/NarratoAI/storage/temp/narration_script.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_output)
    print(f"\n已将Markdown输出保存到: {output_file}")

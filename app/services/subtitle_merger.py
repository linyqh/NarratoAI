#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : subtitle_merger
@Author : viccy
@Date   : 2025/5/6 下午4:00 
'''

import re
import os
from datetime import datetime, timedelta


def parse_time(time_str):
    """解析时间字符串为timedelta对象"""
    hours, minutes, seconds_ms = time_str.split(':')
    seconds, milliseconds = seconds_ms.split(',')
    
    td = timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        milliseconds=int(milliseconds)
    )
    return td


def format_time(td):
    """将timedelta对象格式化为SRT时间字符串"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = td.microseconds // 1000
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def extract_time_range_from_filename(filename):
    """从文件名中提取时间范围"""
    pattern = r'subtitle_(\d{2})_(\d{2})_(\d{2})-(\d{2})_(\d{2})_(\d{2})'
    match = re.search(pattern, filename)
    
    if not match:
        return None, None
    
    start_h, start_m, start_s, end_h, end_m, end_s = map(int, match.groups())
    
    start_time = timedelta(hours=start_h, minutes=start_m, seconds=start_s)
    end_time = timedelta(hours=end_h, minutes=end_m, seconds=end_s)
    
    return start_time, end_time


def merge_subtitle_files(subtitle_files, output_file=None):
    """
    合并多个SRT字幕文件
    
    参数:
        subtitle_files: 包含SRT文件路径的列表
        output_file: 输出文件的路径，如果为None则自动生成
    
    返回:
        合并后的字幕文件路径
    """
    # 按文件名中的开始时间排序
    sorted_files = sorted(subtitle_files, 
                          key=lambda x: extract_time_range_from_filename(x)[0])
    
    merged_subtitles = []
    subtitle_index = 1
    
    for file_path in sorted_files:
        # 从文件名获取起始时间偏移
        offset_time, _ = extract_time_range_from_filename(file_path)
        
        if offset_time is None:
            print(f"警告: 无法从文件名 {os.path.basename(file_path)} 中提取时间范围，跳过该文件")
            continue
        
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # 解析字幕文件
        subtitle_blocks = re.split(r'\n\s*\n', content.strip())
        
        for block in subtitle_blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:  # 确保块有足够的行数
                continue
                
            # 解析时间轴行
            time_line = lines[1]
            time_parts = time_line.split(' --> ')
            if len(time_parts) != 2:
                continue
                
            start_time = parse_time(time_parts[0])
            end_time = parse_time(time_parts[1])
            
            # 应用时间偏移
            adjusted_start_time = start_time + offset_time
            adjusted_end_time = end_time + offset_time
            
            # 重建字幕块
            adjusted_time_line = f"{format_time(adjusted_start_time)} --> {format_time(adjusted_end_time)}"
            text_lines = lines[2:]
            
            new_block = [
                str(subtitle_index),
                adjusted_time_line,
                *text_lines
            ]
            
            merged_subtitles.append('\n'.join(new_block))
            subtitle_index += 1
    
    # 合并所有字幕块
    merged_content = '\n\n'.join(merged_subtitles)
    
    # 确定输出文件路径
    if output_file is None:
        # 自动生成输出文件名
        first_file_path = sorted_files[0]
        last_file_path = sorted_files[-1]
        _, first_end = extract_time_range_from_filename(first_file_path)
        _, last_end = extract_time_range_from_filename(last_file_path)
        
        dir_path = os.path.dirname(first_file_path)
        first_start_str = os.path.basename(first_file_path).split('-')[0].replace('subtitle_', '')
        last_end_h, last_end_m, last_end_s = int(last_end.seconds // 3600), int((last_end.seconds % 3600) // 60), int(last_end.seconds % 60)
        last_end_str = f"{last_end_h:02d}_{last_end_m:02d}_{last_end_s:02d}"
        
        output_file = os.path.join(dir_path, f"merged_subtitle_{first_start_str}-{last_end_str}.srt")
    
    # 写入合并后的内容
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(merged_content)
    
    return output_file


if __name__ == '__main__':
    subtitle_files = [
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_00_00-00_01_15.srt",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_01_15-00_04_40.srt",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_04_58-00_05_45.srt",
        "/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_05_45-00_06_00.srt",
    ]
    
    output_file = merge_subtitle_files(subtitle_files)
    print(f"字幕文件已合并至: {output_file}")

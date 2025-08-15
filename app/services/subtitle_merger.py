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


def parse_edited_time_range(time_range_str):
    """从editedTimeRange字符串中提取时间范围"""
    if not time_range_str:
        return None, None
    
    parts = time_range_str.split('-')
    if len(parts) != 2:
        return None, None
    
    start_time_str, end_time_str = parts
    
    # 将HH:MM:SS格式转换为timedelta
    start_h, start_m, start_s = map(int, start_time_str.split(':'))
    end_h, end_m, end_s = map(int, end_time_str.split(':'))
    
    start_time = timedelta(hours=start_h, minutes=start_m, seconds=start_s)
    end_time = timedelta(hours=end_h, minutes=end_m, seconds=end_s)
    
    return start_time, end_time


def merge_subtitle_files(subtitle_items, output_file=None):
    """
    合并多个SRT字幕文件

    参数:
        subtitle_items: 字典列表，每个字典包含subtitle文件路径和editedTimeRange
        output_file: 输出文件的路径，如果为None则自动生成

    返回:
        合并后的字幕文件路径，如果没有有效字幕则返回None
    """
    # 按照editedTimeRange的开始时间排序
    sorted_items = sorted(subtitle_items,
                         key=lambda x: parse_edited_time_range(x.get('editedTimeRange', ''))[0] or timedelta())

    merged_subtitles = []
    subtitle_index = 1
    valid_items_count = 0

    for item in sorted_items:
        if not item.get('subtitle') or not os.path.exists(item.get('subtitle')):
            print(f"跳过项目 {item.get('_id')}：字幕文件不存在或路径为空")
            continue

        # 从editedTimeRange获取起始时间偏移
        offset_time, _ = parse_edited_time_range(item.get('editedTimeRange', ''))

        if offset_time is None:
            print(f"警告: 无法从项目 {item.get('_id')} 的editedTimeRange中提取时间范围，跳过该项")
            continue

        try:
            with open(item['subtitle'], 'r', encoding='utf-8') as file:
                content = file.read().strip()

            # 检查文件内容是否为空
            if not content:
                print(f"跳过项目 {item.get('_id')}：字幕文件内容为空")
                continue

            valid_items_count += 1

            # 解析字幕文件
            subtitle_blocks = re.split(r'\n\s*\n', content)

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
        except Exception as e:
            print(f"处理项目 {item.get('_id')} 的字幕文件时出错: {str(e)}")
            continue

    # 检查是否有有效的字幕内容
    if not merged_subtitles:
        print(f"警告: 没有找到有效的字幕内容，共检查了 {len(subtitle_items)} 个项目，其中 {valid_items_count} 个有有效文件")
        return None

    # 确定输出文件路径
    if output_file is None:
        # 找到第一个有效的字幕文件来确定目录
        valid_item = None
        for item in sorted_items:
            if item.get('subtitle') and os.path.exists(item.get('subtitle')):
                valid_item = item
                break

        if not valid_item:
            print("错误: 无法确定输出目录，没有找到有效的字幕文件")
            return None

        dir_path = os.path.dirname(valid_item['subtitle'])
        first_start = parse_edited_time_range(sorted_items[0]['editedTimeRange'])[0]
        last_end = parse_edited_time_range(sorted_items[-1]['editedTimeRange'])[1]

        if first_start and last_end:
            first_start_h, first_start_m, first_start_s = int(first_start.seconds // 3600), int((first_start.seconds % 3600) // 60), int(first_start.seconds % 60)
            last_end_h, last_end_m, last_end_s = int(last_end.seconds // 3600), int((last_end.seconds % 3600) // 60), int(last_end.seconds % 60)

            first_start_str = f"{first_start_h:02d}_{first_start_m:02d}_{first_start_s:02d}"
            last_end_str = f"{last_end_h:02d}_{last_end_m:02d}_{last_end_s:02d}"

            output_file = os.path.join(dir_path, f"merged_subtitle_{first_start_str}-{last_end_str}.srt")
        else:
            output_file = os.path.join(dir_path, f"merged_subtitle.srt")

    # 合并所有字幕块
    merged_content = '\n\n'.join(merged_subtitles)

    # 写入合并后的内容
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(merged_content)
        print(f"字幕文件合并成功: {output_file}，包含 {len(merged_subtitles)} 个字幕条目")
        return output_file
    except Exception as e:
        print(f"写入字幕文件失败: {str(e)}")
        return None


if __name__ == '__main__':
    # 测试数据
    test_data = [
        {'picture': '【解说】好的，各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！', 
         'timestamp': '00:00:00-00:01:15', 
         'narration': '好的各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！上集片尾那个巨大的悬念，这一集就立刻揭晓了！范闲假死归来，他面临的第一个，也是最大的难关，就是如何面对他最敬爱的，同时也是最可怕的那个人——庆帝！', 
         'OST': 0, 
         '_id': 1, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_00_00-00_01_15.mp3', 
         'subtitle': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_00_00-00_01_15.srt', 
         'sourceTimeRange': '00:00:00-00:00:26', 
         'duration': 26, 
         'editedTimeRange': '00:00:00-00:00:26'
        },
        {'picture': '【解说】上一集我们看到，范闲在北齐遭遇了惊天变故，生死不明！', 
         'timestamp': '00:01:15-00:04:40', 
         'narration': '但我们都知道，他绝不可能就这么轻易退场！第二集一开场，范闲就已经秘密回到了京都。他的生死传闻，可不像我们想象中那样只是小范围流传，而是…', 
         'OST': 0, 
         '_id': 2, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_01_15-00_04_40.mp3', 
         'subtitle': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_01_15-00_04_40.srt', 
         'sourceTimeRange': '00:01:15-00:01:29', 
         'duration': 14, 
         'editedTimeRange': '00:00:26-00:00:40'
        },
        {'picture': '【解说】"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。', 
         'timestamp': '00:04:58-00:05:45', 
         'narration': '"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。但范闲是谁啊？他偏要反其道而行之！他竟然决定，直接去见庆帝！冒着天大的风险，用"假死"这个事实去赌庆帝的态度！', 
         'OST': 0, 
         '_id': 4, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_04_58-00_05_45.mp3', 
         'subtitle': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_04_58-00_05_45.srt', 
         'sourceTimeRange': '00:04:58-00:05:20', 
         'duration': 22, 
         'editedTimeRange': '00:00:57-00:01:19'
        },
        {'picture': '【解说】但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！', 
         'timestamp': '00:05:45-00:06:00', 
         'narration': '但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！', 
         'OST': 0, 
         '_id': 5, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_05_45-00_06_00.mp3', 
         'subtitle': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_05_45-00_06_00.srt', 
         'sourceTimeRange': '00:05:45-00:05:53', 
         'duration': 8, 
         'editedTimeRange': '00:01:19-00:01:27'
        }
    ]
    
    output_file = merge_subtitle_files(test_data)
    print(f"字幕文件已合并至: {output_file}")

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : update_script
@Author : Viccy同学
@Date   : 2025/5/6 下午11:00 
'''

import re
import os
from typing import Dict, List, Any, Tuple, Union


def extract_timestamp_from_video_path(video_path: str) -> str:
    """
    从视频文件路径中提取时间戳
    
    Args:
        video_path: 视频文件路径
    
    Returns:
        提取出的时间戳，格式为 'HH:MM:SS-HH:MM:SS' 或 'HH:MM:SS,sss-HH:MM:SS,sss'
    """
    # 使用正则表达式从文件名中提取时间戳
    filename = os.path.basename(video_path)
    
    # 匹配新格式: vid_00-00-00-000@00-00-20-250.mp4
    match_new = re.search(r'vid_(\d{2})-(\d{2})-(\d{2})-(\d{3})@(\d{2})-(\d{2})-(\d{2})-(\d{3})\.mp4', filename)
    if match_new:
        # 提取并格式化时间戳（包含毫秒）
        start_h, start_m, start_s, start_ms = match_new.group(1), match_new.group(2), match_new.group(3), match_new.group(4)
        end_h, end_m, end_s, end_ms = match_new.group(5), match_new.group(6), match_new.group(7), match_new.group(8)
        return f"{start_h}:{start_m}:{start_s},{start_ms}-{end_h}:{end_m}:{end_s},{end_ms}"
    
    # 匹配旧格式: vid-00-00-00-00-00-00.mp4
    match_old = re.search(r'vid-(\d{2}-\d{2}-\d{2})-(\d{2}-\d{2}-\d{2})\.mp4', filename)
    if match_old:
        # 提取并格式化时间戳
        start_time = match_old.group(1).replace('-', ':')
        end_time = match_old.group(2).replace('-', ':')
        return f"{start_time}-{end_time}"

    return ""


def calculate_duration(timestamp: str) -> float:
    """
    计算时间戳范围的持续时间（秒）
    
    Args:
        timestamp: 格式为 'HH:MM:SS-HH:MM:SS' 或 'HH:MM:SS,sss-HH:MM:SS,sss' 的时间戳
    
    Returns:
        持续时间（秒）
    """
    try:
        start_time, end_time = timestamp.split('-')

        # 处理毫秒部分
        if ',' in start_time:
            start_parts = start_time.split(',')
            start_time_parts = start_parts[0].split(':')
            start_ms = float('0.' + start_parts[1]) if len(start_parts) > 1 else 0
            start_h, start_m, start_s = map(int, start_time_parts)
        else:
            start_h, start_m, start_s = map(int, start_time.split(':'))
            start_ms = 0

        if ',' in end_time:
            end_parts = end_time.split(',')
            end_time_parts = end_parts[0].split(':')
            end_ms = float('0.' + end_parts[1]) if len(end_parts) > 1 else 0
            end_h, end_m, end_s = map(int, end_time_parts)
        else:
            end_h, end_m, end_s = map(int, end_time.split(':'))
            end_ms = 0

        # 转换为秒
        start_seconds = start_h * 3600 + start_m * 60 + start_s + start_ms
        end_seconds = end_h * 3600 + end_m * 60 + end_s + end_ms

        # 计算时间差（秒）
        return round(end_seconds - start_seconds, 2)
    except (ValueError, AttributeError):
        return 0.0


def update_script_timestamps(
    script_list: List[Dict[str, Any]], 
    video_result: Dict[Union[str, int], str], 
    audio_result: Dict[Union[str, int], str] = None,
    subtitle_result: Dict[Union[str, int], str] = None,
    calculate_edited_timerange: bool = True
) -> List[Dict[str, Any]]:
    """
    根据 video_result 中的视频文件更新 script_list 中的时间戳，添加持续时间，
    并根据 audio_result 添加音频路径，根据 subtitle_result 添加字幕路径
    
    Args:
        script_list: 原始脚本列表
        video_result: 视频结果字典，键为原时间戳或_id，值为视频文件路径
        audio_result: 音频结果字典，键为原时间戳或_id，值为音频文件路径
        subtitle_result: 字幕结果字典，键为原时间戳或_id，值为字幕文件路径
        calculate_edited_timerange: 是否计算并添加成品视频中的时间范围
    
    Returns:
        更新后的脚本列表
    """
    # 创建副本，避免修改原始数据
    updated_script = []

    # 建立ID和时间戳到视频路径和新时间戳的映射
    id_timestamp_mapping = {}
    for key, video_path in video_result.items():
        new_timestamp = extract_timestamp_from_video_path(video_path)
        if new_timestamp:
            id_timestamp_mapping[key] = {
                'new_timestamp': new_timestamp,
                'video_path': video_path
            }

    # 计算累积时长，用于生成成品视频中的时间范围
    accumulated_duration = 0.0
    
    # 更新脚本中的时间戳
    for item in script_list:
        item_copy = item.copy()
        item_id = item_copy.get('_id')
        orig_timestamp = item_copy.get('timestamp', '')

        # 初始化音频和字幕路径为空字符串
        item_copy['audio'] = ""
        item_copy['subtitle'] = ""
        item_copy['video'] = ""  # 初始化视频路径为空字符串

        # 如果提供了音频结果字典且ID存在于音频结果中，直接使用对应的音频路径
        if audio_result:
            if item_id and item_id in audio_result:
                item_copy['audio'] = audio_result[item_id]
            elif orig_timestamp in audio_result:
                item_copy['audio'] = audio_result[orig_timestamp]

        # 如果提供了字幕结果字典且ID存在于字幕结果中，直接使用对应的字幕路径
        if subtitle_result:
            if item_id and item_id in subtitle_result:
                item_copy['subtitle'] = subtitle_result[item_id]
            elif orig_timestamp in subtitle_result:
                item_copy['subtitle'] = subtitle_result[orig_timestamp]

        # 添加视频路径
        if item_id and item_id in video_result:
            item_copy['video'] = video_result[item_id]
        elif orig_timestamp in video_result:
            item_copy['video'] = video_result[orig_timestamp]

        # 更新时间戳和计算持续时间
        current_duration = 0.0
        if item_id and item_id in id_timestamp_mapping:
            # 根据ID找到对应的新时间戳
            item_copy['sourceTimeRange'] = id_timestamp_mapping[item_id]['new_timestamp']
            current_duration = calculate_duration(item_copy['sourceTimeRange'])
            item_copy['duration'] = current_duration
        elif orig_timestamp in id_timestamp_mapping:
            # 根据原始时间戳找到对应的新时间戳
            item_copy['sourceTimeRange'] = id_timestamp_mapping[orig_timestamp]['new_timestamp']
            current_duration = calculate_duration(item_copy['sourceTimeRange'])
            item_copy['duration'] = current_duration
        elif orig_timestamp:
            # 对于未更新的时间戳，也计算并添加持续时间
            item_copy['sourceTimeRange'] = orig_timestamp
            current_duration = calculate_duration(orig_timestamp)
            item_copy['duration'] = current_duration
            
        # 计算片段在成品视频中的时间范围
        if calculate_edited_timerange and current_duration > 0:
            start_time_seconds = accumulated_duration
            end_time_seconds = accumulated_duration + current_duration
            
            # 将秒数转换为 HH:MM:SS 格式
            start_h = int(start_time_seconds // 3600)
            start_m = int((start_time_seconds % 3600) // 60)
            start_s = int(start_time_seconds % 60)
            
            end_h = int(end_time_seconds // 3600)
            end_m = int((end_time_seconds % 3600) // 60)
            end_s = int(end_time_seconds % 60)
            
            item_copy['editedTimeRange'] = f"{start_h:02d}:{start_m:02d}:{start_s:02d}-{end_h:02d}:{end_m:02d}:{end_s:02d}"
            
            # 更新累积时长
            accumulated_duration = end_time_seconds

        updated_script.append(item_copy)

    return updated_script


if __name__ == '__main__':
    list_script = [
        {
            'picture': '【解说】好的，各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！',
            'timestamp': '00:00:00,001-00:01:15,001',
            'narration': '好的各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！上集片尾那个巨大的悬念，这一集就立刻揭晓了！范闲假死归来，他面临的第一个，也是最大的难关，就是如何面对他最敬爱的，同时也是最可怕的那个人——庆帝！',
            'OST': 0,
            '_id': 1
        },
        {
            'picture': '【解说】上一集我们看到，范闲在北齐遭遇了惊天变故，生死不明！',
            'timestamp': '00:01:15,001-00:04:40,001',
            'narration': '但我们都知道，他绝不可能就这么轻易退场！第二集一开场，范闲就已经秘密回到了京都。他的生死传闻，可不像我们想象中那样只是小范围流传，而是…',
            'OST': 0,
            '_id': 2
        },
        {
            'picture': '画面切到王启年小心翼翼地向范闲汇报。',
            'timestamp': '00:04:41,001-00:04:58,001',
            'narration': '我发现大人的死讯不光是在民间,在官场上也它传开了,所以呢,所以啊,可不是什么好事,将来您跟陛下怎么交代,这可是欺君之罪',
            'OST': 1,
            '_id': 3
        },
        {
            'picture': '【解说】"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。',
            'timestamp': '00:04:58,001-00:05:45,001',
            'narration': '"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。但范闲是谁啊？他偏要反其道而行之！他竟然决定，直接去见庆帝！冒着天大的风险，用"假死"这个事实去赌庆帝的态度！',
            'OST': 0,
            '_id': 4
        },
        {
            'picture': '【解说】但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！',
            'timestamp': '00:05:45,001-00:06:00,001',
            'narration': '但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！',
            'OST': 0,
            '_id': 5
        },
        {
            'picture': '画面切换到范闲蒙面闯入皇宫，被侍卫包围的场景。',
            'timestamp': '00:06:00,001-00:06:03,001',
            'narration': '抓刺客',
            'OST': 1,
            '_id': 6
        }]
    video_res = {
        1: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/fc3db5844d1ba7d7d838be52c0dac1bd/vid_00-00-00-000@00-00-20-250.mp4',
        2: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/fc3db5844d1ba7d7d838be52c0dac1bd/vid_00-00-30-000@00-00-48-950.mp4',
        4: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/fc3db5844d1ba7d7d838be52c0dac1bd/vid_00-01-00-000@00-01-15-688.mp4',
        5: '/Users/apple/Desktop/home/NarratoAI/storage/temp/clip_video/fc3db5844d1ba7d7d838be52c0dac1bd/vid_00-01-30-000@00-01-49-512.mp4'}
    audio_res = {
        1: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_00_00-00_01_15.mp3',
        2: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_01_15-00_04_40.mp3',
        4: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_04_58-00_05_45.mp3',
        5: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_05_45-00_06_00.mp3'}
    sub_res = {
        1: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_00_00-00_01_15.srt',
        2: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_01_15-00_04_40.srt',
        4: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_04_58-00_05_45.srt',
        5: '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/subtitle_00_05_45-00_06_00.srt'}
    
    # 更新并打印结果
    updated_list_script = update_script_timestamps(list_script, video_res, audio_res, sub_res)
    for item in updated_list_script:
        print(
            f"ID: {item['_id']} | Picture: {item['picture'][:20]}... | Timestamp: {item['timestamp']} | " +
            f"SourceTimeRange: {item['sourceTimeRange']} | EditedTimeRange: {item.get('editedTimeRange', '')} | " +
            f"Duration: {item['duration']} 秒 | Audio: {item['audio']} | Video: {item['video']} | Subtitle: {item['subtitle']}")

# 公共方法
import json
import requests  # 新增
from typing import List, Dict


def load_srt(file_path: str) -> List[Dict]:
    """加载并解析SRT文件

    Args:
        file_path: SRT文件路径

    Returns:
        字幕内容列表
    """
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        content = f.read().strip()

    # 按空行分割字幕块
    subtitle_blocks = content.split('\n\n')
    subtitles = []

    for block in subtitle_blocks:
        lines = block.split('\n')
        if len(lines) >= 3:  # 确保块包含足够的行
            try:
                number = int(lines[0].strip())
                timestamp = lines[1]
                text = ' '.join(lines[2:])

                # 解析时间戳
                start_time, end_time = timestamp.split(' --> ')

                subtitles.append({
                    'number': number,
                    'timestamp': timestamp,
                    'text': text,
                    'start_time': start_time,
                    'end_time': end_time
                })
            except ValueError as e:
                print(f"Warning: 跳过无效的字幕块: {e}")
                continue

    return subtitles

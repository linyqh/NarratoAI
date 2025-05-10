"""
合并生成最终脚本
"""
import os
import json
from typing import List, Dict, Tuple


def merge_script(
        plot_points: List[Dict],
        output_path: str
):
    """合并生成最终脚本

    Args:
        plot_points: 校对后的剧情点
        output_path: 输出文件路径，如果提供则保存到文件

    Returns:
        str: 最终合并的脚本
    """
    def parse_timestamp(ts: str) -> Tuple[float, float]:
        """解析时间戳，返回开始和结束时间（秒）"""
        start, end = ts.split('-')

        def parse_time(time_str: str) -> float:
            time_str = time_str.strip()
            if ',' in time_str:
                time_parts, ms_parts = time_str.split(',')
                ms = float(ms_parts) / 1000
            else:
                time_parts = time_str
                ms = 0

            hours, minutes, seconds = map(int, time_parts.split(':'))
            return hours * 3600 + minutes * 60 + seconds + ms

        return parse_time(start), parse_time(end)

    def format_timestamp(seconds: float) -> str:
        """将秒数转换为时间戳格式 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    # 创建包含所有信息的临时列表
    final_script = []

    # 处理原生画面条目
    number = 1
    for plot_point in plot_points:
        start, end = parse_timestamp(plot_point["timestamp"])
        script_item = {
            "_id": number,
            "timestamp": plot_point["timestamp"],
            "picture": plot_point["picture"],
            "narration": f"播放原生_{os.urandom(4).hex()}",
            "OST": 1,  # OST=0 仅保留解说 OST=2 保留解说和原声
        }
        final_script.append(script_item)
        number += 1

    # 保存结果
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, ensure_ascii=False, indent=4)

    print(f"脚本生成完成：{output_path}")
    return final_script

"""
合并生成最终脚本
"""
import os
import json
from typing import Dict, List


def merge_script(
        plot_points: List[Dict],
        output_path: str,
        video_paths=None,
):
    """合并生成最终脚本

    Args:
        plot_points: 校对后的剧情点
        output_path: 输出文件路径，如果提供则保存到文件

    Returns:
        str: 最终合并的脚本
    """
    if isinstance(video_paths, str):
        video_paths = [video_paths]
    video_paths = [path for path in (video_paths or []) if isinstance(path, str) and path.strip()]

    # 创建包含所有信息的临时列表
    final_script = []

    # 处理原生画面条目
    number = 1
    for plot_point in plot_points:
        script_item = {
            "_id": number,
            "timestamp": plot_point["timestamp"],
            "picture": plot_point["picture"],
            "narration": f"播放原片{number}",
            "OST": 1,  # OST=0 仅保留解说 OST=2 保留解说和原声
        }
        if video_paths:
            script_item["video_id"] = 1
            script_item["video_name"] = os.path.basename(video_paths[0])
        final_script.append(script_item)
        number += 1

    # 保存结果
    if not output_path or not str(output_path).strip():
        raise ValueError("output_path不能为空")

    output_path = str(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_script, f, ensure_ascii=False, indent=4)

    print(f"脚本生成完成：{output_path}")
    return final_script

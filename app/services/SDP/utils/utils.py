# 公共方法
import json
import requests  # 新增
import pysrt
from loguru import logger
from typing import List, Dict


def load_srt(file_path: str) -> List[Dict]:
    """加载并解析SRT文件（使用 pysrt 库，支持多种编码和格式）

    Args:
        file_path: SRT文件路径

    Returns:
        字幕内容列表，格式：
        [
            {
                'number': int,           # 字幕序号
                'timestamp': str,        # "00:00:01,000 --> 00:00:03,000"
                'text': str,             # 字幕文本
                'start_time': str,       # "00:00:01,000"
                'end_time': str          # "00:00:03,000"
            },
            ...
        ]

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件编码不支持或格式错误
    """
    # 编码自动检测：依次尝试常见编码
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']
    subs = None
    detected_encoding = None

    for encoding in encodings:
        try:
            subs = pysrt.open(file_path, encoding=encoding)
            detected_encoding = encoding
            logger.info(f"成功加载字幕文件 {file_path}，编码：{encoding}，共 {len(subs)} 条")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.warning(f"使用编码 {encoding} 加载失败: {e}")
            continue

    if subs is None:
        # 所有编码都失败
        raise ValueError(
            f"无法读取字幕文件 {file_path}，"
            f"请检查文件编码（支持 UTF-8、GBK、GB2312）"
        )

    # 检查是否为空
    if not subs:
        logger.warning(f"字幕文件 {file_path} 解析后无有效内容")
        return []

    # 转换为原格式（向后兼容）
    subtitles = []
    for sub in subs:
        # 合并多行文本为单行（某些 SRT 文件会有换行）
        text = sub.text.replace('\n', ' ').strip()

        # 跳过空字幕
        if not text:
            continue

        subtitles.append({
            'number': sub.index,
            'timestamp': f"{sub.start} --> {sub.end}",
            'text': text,
            'start_time': str(sub.start),
            'end_time': str(sub.end)
        })

    logger.info(f"成功解析 {len(subtitles)} 条有效字幕")
    return subtitles

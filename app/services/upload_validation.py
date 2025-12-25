#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : upload_validation.py
@Author : AI Assistant
@Date   : 2025/12/25
@Desc   : 统一的文件上传验证工具，用于短剧混剪和短剧解说功能
"""

import os
from typing import Optional, Tuple


class InputValidationError(ValueError):
    """当必需的用户输入（路径/内容）缺失或无效时抛出"""
    pass


def ensure_existing_file(
    file_path: str,
    *,
    label: str = "文件",
    allowed_exts: Optional[Tuple[str, ...]] = None,
) -> str:
    """
    验证文件路径是否存在且有效

    Args:
        file_path: 待验证的文件路径
        label: 文件类型标签（用于错误提示）
        allowed_exts: 允许的文件扩展名元组（如 ('.srt', '.txt')）

    Returns:
        str: 规范化后的绝对路径

    Raises:
        InputValidationError: 文件路径无效、文件不存在或格式不支持
    """
    if not file_path or not str(file_path).strip():
        raise InputValidationError(f"{label}不能为空，请先上传{label}")

    normalized = os.path.abspath(str(file_path))

    if not os.path.exists(normalized):
        raise InputValidationError(f"{label}文件不存在: {normalized}")

    if not os.path.isfile(normalized):
        raise InputValidationError(f"{label}不是有效文件: {normalized}")

    if allowed_exts:
        ext = os.path.splitext(normalized)[1].lower()
        allowed = tuple(e.lower() for e in allowed_exts)
        if ext not in allowed:
            raise InputValidationError(
                f"{label}格式不支持: {ext}，仅支持: {', '.join(allowed_exts)}"
            )

    return normalized


def resolve_subtitle_input(
    *,
    subtitle_content: Optional[str] = None,
    subtitle_file_path: Optional[str] = None,
    srt_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    解析字幕输入源，确保只有一个有效来源

    Args:
        subtitle_content: 字幕文本内容
        subtitle_file_path: 字幕文件路径（推荐）
        srt_path: 字幕文件路径（向后兼容SDP旧参数）

    Returns:
        Tuple[Optional[str], Optional[str]]: (字幕内容, 字幕文件路径)
        - 返回 (content, None) 表示使用内容输入
        - 返回 (None, file_path) 表示使用文件路径输入

    Raises:
        InputValidationError: 未提供输入或同时提供多个输入
    """
    file_path = subtitle_file_path or srt_path

    has_content = subtitle_content is not None and bool(str(subtitle_content).strip())
    has_file = file_path is not None and bool(str(file_path).strip())

    if has_content and has_file:
        raise InputValidationError("只能提供字幕内容或字幕文件路径之一")

    if not has_content and not has_file:
        raise InputValidationError("必须提供字幕内容或字幕文件路径")

    if has_content:
        content = str(subtitle_content)
        if not content.strip():
            raise InputValidationError("字幕内容为空")
        return content, None

    resolved_path = ensure_existing_file(
        str(file_path),
        label="字幕",
        allowed_exts=(".srt",),
    )
    return None, resolved_path

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : validators.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 提示词输出验证器
"""

import json
import re
from typing import Dict, Any, List, Optional, Union
from loguru import logger

from .base import OutputFormat
from .exceptions import PromptValidationError


class PromptOutputValidator:
    """提示词输出验证器"""
    
    @staticmethod
    def validate_json(output: str, schema: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        验证JSON输出
        
        Args:
            output: 输出字符串
            schema: JSON schema（可选）
            
        Returns:
            解析后的JSON对象
        """
        try:
            # 清理输出（移除可能的代码块标记）
            cleaned_output = PromptOutputValidator._clean_json_output(output)
            
            # 解析JSON
            parsed = json.loads(cleaned_output)
            
            # Schema验证（如果提供）
            if schema:
                PromptOutputValidator._validate_json_schema(parsed, schema)
                
            return parsed
            
        except json.JSONDecodeError as e:
            raise PromptValidationError(f"JSON格式错误: {str(e)}")
        except Exception as e:
            raise PromptValidationError(f"JSON验证失败: {str(e)}")
            
    @staticmethod
    def validate_narration_script(output: Union[str, Dict]) -> Dict[str, Any]:
        """
        验证解说文案输出格式
        
        Args:
            output: 输出内容（字符串或字典）
            
        Returns:
            验证后的解说文案数据
        """
        # 如果是字符串，先解析为JSON
        if isinstance(output, str):
            data = PromptOutputValidator.validate_json(output)
        else:
            data = output
            
        # 验证必需字段
        if "items" not in data:
            raise PromptValidationError("解说文案缺少 'items' 字段")
            
        items = data["items"]
        if not isinstance(items, list):
            raise PromptValidationError("'items' 字段必须是数组")
            
        if not items:
            raise PromptValidationError("解说文案不能为空")
            
        # 验证每个item
        for i, item in enumerate(items):
            PromptOutputValidator._validate_narration_item(item, i)
            
        logger.debug(f"解说文案验证通过，包含 {len(items)} 个片段")
        return data
        
    @staticmethod
    def validate_plot_analysis(output: Union[str, Dict]) -> Dict[str, Any]:
        """
        验证剧情分析输出格式
        
        Args:
            output: 输出内容
            
        Returns:
            验证后的剧情分析数据
        """
        if isinstance(output, str):
            data = PromptOutputValidator.validate_json(output)
        else:
            data = output
            
        # 验证剧情分析必需字段
        required_fields = ["summary", "plot_points"]
        for field in required_fields:
            if field not in data:
                raise PromptValidationError(f"剧情分析缺少 '{field}' 字段")
                
        # 验证plot_points
        plot_points = data["plot_points"]
        if not isinstance(plot_points, list):
            raise PromptValidationError("'plot_points' 字段必须是数组")
            
        for i, point in enumerate(plot_points):
            PromptOutputValidator._validate_plot_point(point, i)
            
        logger.debug(f"剧情分析验证通过，包含 {len(plot_points)} 个情节点")
        return data
        
    @staticmethod
    def _clean_json_output(output: str) -> str:
        """清理JSON输出"""
        # 移除可能的代码块标记
        output = re.sub(r'^```json\s*', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```\s*$', '', output, flags=re.MULTILINE)
        
        # 移除前后空白
        output = output.strip()
        
        # 尝试提取JSON部分（如果有其他文本）
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            output = json_match.group(0)
            
        return output
        
    @staticmethod
    def _validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """验证JSON Schema"""
        # 简单的schema验证实现
        for field, field_type in schema.items():
            if field not in data:
                raise PromptValidationError(f"缺少必需字段: {field}")
                
            if not isinstance(data[field], field_type):
                raise PromptValidationError(
                    f"字段 '{field}' 类型错误，期望: {field_type.__name__}，实际: {type(data[field]).__name__}"
                )
                
    @staticmethod
    def _validate_narration_item(item: Dict[str, Any], index: int) -> None:
        """验证解说文案项目"""
        required_fields = ["_id", "timestamp", "picture", "narration"]
        
        for field in required_fields:
            if field not in item:
                raise PromptValidationError(f"第 {index + 1} 个片段缺少 '{field}' 字段")
                
        # 验证_id
        if not isinstance(item["_id"], int) or item["_id"] <= 0:
            raise PromptValidationError(f"第 {index + 1} 个片段的 '_id' 必须是正整数")
            
        # 验证timestamp格式
        timestamp = item["timestamp"]
        if not isinstance(timestamp, str):
            raise PromptValidationError(f"第 {index + 1} 个片段的 'timestamp' 必须是字符串")
            
        # 验证时间戳格式 (HH:MM:SS,mmm-HH:MM:SS,mmm)
        timestamp_pattern = r'^\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}$'
        if not re.match(timestamp_pattern, timestamp):
            raise PromptValidationError(
                f"第 {index + 1} 个片段的时间戳格式错误，应为 'HH:MM:SS,mmm-HH:MM:SS,mmm'"
            )
            
        # 验证文本字段不为空
        for field in ["picture", "narration"]:
            if not isinstance(item[field], str) or not item[field].strip():
                raise PromptValidationError(f"第 {index + 1} 个片段的 '{field}' 不能为空")
                
        # 验证OST字段（如果存在）
        if "OST" in item:
            if not isinstance(item["OST"], int) or item["OST"] not in [0, 1, 2]:
                raise PromptValidationError(
                    f"第 {index + 1} 个片段的 'OST' 必须是 0、1 或 2"
                )
                
    @staticmethod
    def _validate_plot_point(point: Dict[str, Any], index: int) -> None:
        """验证剧情点"""
        required_fields = ["timestamp", "title", "picture"]
        
        for field in required_fields:
            if field not in point:
                raise PromptValidationError(f"第 {index + 1} 个剧情点缺少 '{field}' 字段")
                
        # 验证字段类型和内容
        for field in required_fields:
            if not isinstance(point[field], str) or not point[field].strip():
                raise PromptValidationError(f"第 {index + 1} 个剧情点的 '{field}' 不能为空")
                
        # 验证时间戳格式
        timestamp = point["timestamp"]
        # 支持多种时间戳格式
        patterns = [
            r'^\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}$',  # HH:MM:SS,mmm-HH:MM:SS,mmm
            r'^\d{2}:\d{2}:\d{2}-\d{2}:\d{2}:\d{2}$',              # HH:MM:SS-HH:MM:SS
        ]
        
        if not any(re.match(pattern, timestamp) for pattern in patterns):
            raise PromptValidationError(
                f"第 {index + 1} 个剧情点的时间戳格式错误"
            )
            
    @staticmethod
    def validate_by_format(output: str, format_type: OutputFormat, schema: Dict[str, Any] = None) -> Any:
        """
        根据格式类型验证输出
        
        Args:
            output: 输出内容
            format_type: 输出格式类型
            schema: 验证schema（可选）
            
        Returns:
            验证后的数据
        """
        if format_type == OutputFormat.JSON:
            return PromptOutputValidator.validate_json(output, schema)
        elif format_type == OutputFormat.TEXT:
            return output.strip()
        elif format_type == OutputFormat.MARKDOWN:
            return output.strip()
        elif format_type == OutputFormat.STRUCTURED:
            # 结构化数据需要根据具体类型处理
            return PromptOutputValidator.validate_json(output, schema)
        else:
            raise PromptValidationError(f"不支持的输出格式: {format_type}")


# 便捷函数
def validate_json_output(output: str, schema: Dict[str, Any] = None) -> Dict[str, Any]:
    """验证JSON输出的便捷函数"""
    return PromptOutputValidator.validate_json(output, schema)


def validate_narration_output(output: Union[str, Dict]) -> Dict[str, Any]:
    """验证解说文案输出的便捷函数"""
    return PromptOutputValidator.validate_narration_script(output)

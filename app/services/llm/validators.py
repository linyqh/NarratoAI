"""
输出格式验证器

提供严格的输出格式验证机制，确保大模型输出符合预期格式
"""

import json
import re
from typing import Any, Dict, List, Optional, Union
from loguru import logger

from .exceptions import ValidationError


class OutputValidator:
    """输出格式验证器"""
    
    @staticmethod
    def validate_json_output(output: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        验证JSON输出格式
        
        Args:
            output: 待验证的输出字符串
            schema: JSON Schema (可选)
            
        Returns:
            解析后的JSON对象
            
        Raises:
            ValidationError: 验证失败时抛出
        """
        try:
            # 清理输出字符串，移除可能的markdown代码块标记
            cleaned_output = OutputValidator._clean_json_output(output)
            
            # 解析JSON
            parsed_json = json.loads(cleaned_output)
            
            # 如果提供了schema，进行schema验证
            if schema:
                OutputValidator._validate_json_schema(parsed_json, schema)
            
            return parsed_json
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {str(e)}")
            logger.error(f"原始输出: {output}")
            raise ValidationError(f"JSON格式无效: {str(e)}", "json_parse", output)
        except Exception as e:
            logger.error(f"JSON验证失败: {str(e)}")
            raise ValidationError(f"JSON验证失败: {str(e)}", "json_validation", output)
    
    @staticmethod
    def _clean_json_output(output: str) -> str:
        """清理JSON输出，移除markdown标记等"""
        # 移除可能的markdown代码块标记
        output = re.sub(r'^```json\s*', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```\s*$', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```.*$', '', output, flags=re.MULTILINE)

        # 移除开头和结尾的```标记
        output = re.sub(r'^```', '', output)
        output = re.sub(r'```$', '', output)

        # 移除前后空白字符
        output = output.strip()

        return output
    
    @staticmethod
    def _validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]):
        """验证JSON Schema (简化版本)"""
        # 这里可以集成jsonschema库进行更严格的验证
        # 目前实现基础的类型检查
        
        if "type" in schema:
            expected_type = schema["type"]
            if expected_type == "object" and not isinstance(data, dict):
                raise ValidationError(f"期望对象类型，实际为 {type(data)}", "schema_type")
            elif expected_type == "array" and not isinstance(data, list):
                raise ValidationError(f"期望数组类型，实际为 {type(data)}", "schema_type")
        
        if "required" in schema and isinstance(data, dict):
            for required_field in schema["required"]:
                if required_field not in data:
                    raise ValidationError(f"缺少必需字段: {required_field}", "schema_required")
    
    @staticmethod
    def validate_narration_script(output: str) -> List[Dict[str, Any]]:
        """
        验证解说文案输出格式
        
        Args:
            output: 待验证的解说文案输出
            
        Returns:
            解析后的解说文案列表
            
        Raises:
            ValidationError: 验证失败时抛出
        """
        try:
            # 定义解说文案的JSON Schema
            narration_schema = {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["_id", "timestamp", "picture", "narration"],
                            "properties": {
                                "_id": {"type": "number"},
                                "timestamp": {"type": "string"},
                                "picture": {"type": "string"},
                                "narration": {"type": "string"},
                                "OST": {"type": "number"}
                            }
                        }
                    }
                }
            }
            
            # 验证JSON格式
            parsed_data = OutputValidator.validate_json_output(output, narration_schema)
            
            # 提取items数组
            items = parsed_data.get("items", [])
            
            # 验证每个item的具体内容
            for i, item in enumerate(items):
                OutputValidator._validate_narration_item(item, i)
            
            logger.info(f"解说文案验证成功，共 {len(items)} 个片段")
            return items
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"解说文案验证失败: {str(e)}")
            raise ValidationError(f"解说文案验证失败: {str(e)}", "narration_validation", output)
    
    @staticmethod
    def _validate_narration_item(item: Dict[str, Any], index: int):
        """验证单个解说文案项目"""
        # 验证时间戳格式
        timestamp = item.get("timestamp", "")
        if not re.match(r'\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}', timestamp):
            raise ValidationError(f"第{index+1}项时间戳格式无效: {timestamp}", "timestamp_format")
        
        # 验证内容不为空
        if not item.get("picture", "").strip():
            raise ValidationError(f"第{index+1}项画面描述不能为空", "empty_picture")
        
        if not item.get("narration", "").strip():
            raise ValidationError(f"第{index+1}项解说文案不能为空", "empty_narration")
        
        # 验证ID为正整数
        item_id = item.get("_id")
        if not isinstance(item_id, (int, float)) or item_id <= 0:
            raise ValidationError(f"第{index+1}项ID必须为正整数: {item_id}", "invalid_id")
    
    @staticmethod
    def validate_subtitle_analysis(output: str) -> str:
        """
        验证字幕分析输出格式
        
        Args:
            output: 待验证的字幕分析输出
            
        Returns:
            验证后的分析内容
            
        Raises:
            ValidationError: 验证失败时抛出
        """
        try:
            # 基础验证：内容不能为空
            if not output or not output.strip():
                raise ValidationError("字幕分析结果不能为空", "empty_analysis")
            
            # 验证内容长度合理
            if len(output.strip()) < 50:
                raise ValidationError("字幕分析结果过短，可能不完整", "analysis_too_short")
            
            # 验证是否包含基本的分析要素（可根据需要调整）
            analysis_keywords = ["剧情", "情节", "角色", "故事", "内容"]
            if not any(keyword in output for keyword in analysis_keywords):
                logger.warning("字幕分析结果可能缺少关键分析要素")
            
            logger.info("字幕分析验证成功")
            return output.strip()
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"字幕分析验证失败: {str(e)}")
            raise ValidationError(f"字幕分析验证失败: {str(e)}", "analysis_validation", output)

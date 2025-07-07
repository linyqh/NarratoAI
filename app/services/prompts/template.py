#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : template.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 模板渲染引擎
"""

import re
from typing import Dict, Any, List, Optional
from string import Template
from loguru import logger

from .exceptions import TemplateRenderError


class TemplateRenderer:
    """模板渲染器"""
    
    def __init__(self):
        self._custom_filters = {}
        
    def register_filter(self, name: str, func: callable) -> None:
        """注册自定义过滤器"""
        self._custom_filters[name] = func
        logger.debug(f"已注册模板过滤器: {name}")
        
    def render(self, template: str, parameters: Dict[str, Any] = None) -> str:
        """
        渲染模板
        
        Args:
            template: 模板字符串
            parameters: 参数字典
            
        Returns:
            渲染后的字符串
        """
        parameters = parameters or {}
        
        try:
            # 使用简单的字符串替换进行参数替换
            rendered = template

            for key, value in parameters.items():
                # 替换 ${key} 格式的参数
                rendered = rendered.replace(f"${{{key}}}", str(value))
                # 也替换 $key 格式的参数（为了兼容性）
                rendered = rendered.replace(f"${key}", str(value))

            # 处理自定义过滤器
            rendered = self._apply_filters(rendered, parameters)

            return rendered
            
        except Exception as e:
            raise TemplateRenderError(
                template_name="unknown",
                error_message=f"模板渲染失败: {str(e)}"
            )
            
    def _apply_filters(self, text: str, parameters: Dict[str, Any]) -> str:
        """应用自定义过滤器"""
        # 查找过滤器模式: ${variable|filter_name}
        filter_pattern = r'\$\{([^}]+)\|([^}]+)\}'
        
        def replace_filter(match):
            var_name = match.group(1).strip()
            filter_name = match.group(2).strip()
            
            if filter_name not in self._custom_filters:
                logger.warning(f"未知的过滤器: {filter_name}")
                return match.group(0)  # 返回原始文本
                
            if var_name not in parameters:
                logger.warning(f"参数不存在: {var_name}")
                return match.group(0)  # 返回原始文本
                
            try:
                filter_func = self._custom_filters[filter_name]
                filtered_value = filter_func(parameters[var_name])
                return str(filtered_value)
            except Exception as e:
                logger.error(f"过滤器执行失败 {filter_name}: {str(e)}")
                return match.group(0)  # 返回原始文本
                
        return re.sub(filter_pattern, replace_filter, text)
        
    def extract_variables(self, template: str) -> List[str]:
        """提取模板中的变量名"""
        # 匹配 ${variable} 和 ${variable|filter} 模式
        pattern = r'\$\{([^}|]+)(?:\|[^}]+)?\}'
        matches = re.findall(pattern, template)
        return list(set(match.strip() for match in matches))
        
    def validate_template(self, template: str, required_params: List[str] = None) -> bool:
        """验证模板"""
        try:
            # 提取模板变量
            template_vars = self.extract_variables(template)
            
            # 检查必需参数
            if required_params:
                missing_params = set(required_params) - set(template_vars)
                if missing_params:
                    raise TemplateRenderError(
                        template_name="validation",
                        error_message="模板缺少必需参数",
                        missing_params=list(missing_params)
                    )
                    
            # 尝试渲染测试
            test_params = {var: f"test_{var}" for var in template_vars}
            self.render(template, test_params)
            
            return True
            
        except Exception as e:
            logger.error(f"模板验证失败: {str(e)}")
            return False


# 内置过滤器
def _upper_filter(value: Any) -> str:
    """转换为大写"""
    return str(value).upper()


def _lower_filter(value: Any) -> str:
    """转换为小写"""
    return str(value).lower()


def _title_filter(value: Any) -> str:
    """转换为标题格式"""
    return str(value).title()


def _strip_filter(value: Any) -> str:
    """去除首尾空白"""
    return str(value).strip()


def _truncate_filter(value: Any, length: int = 100) -> str:
    """截断文本"""
    text = str(value)
    if len(text) <= length:
        return text
    return text[:length] + "..."


def _json_filter(value: Any) -> str:
    """转换为JSON字符串"""
    import json
    return json.dumps(value, ensure_ascii=False, indent=2)


# 全局渲染器实例
_global_renderer = TemplateRenderer()

# 注册内置过滤器
_global_renderer.register_filter("upper", _upper_filter)
_global_renderer.register_filter("lower", _lower_filter)
_global_renderer.register_filter("title", _title_filter)
_global_renderer.register_filter("strip", _strip_filter)
_global_renderer.register_filter("truncate", _truncate_filter)
_global_renderer.register_filter("json", _json_filter)


def get_renderer() -> TemplateRenderer:
    """获取全局渲染器实例"""
    return _global_renderer


def render_template(template: str, parameters: Dict[str, Any] = None) -> str:
    """便捷的模板渲染函数"""
    return _global_renderer.render(template, parameters)

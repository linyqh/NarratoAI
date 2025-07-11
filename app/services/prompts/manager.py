#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : manager.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 提示词管理器
"""

from typing import Dict, Any, List, Optional, Union
from loguru import logger

from .base import BasePrompt, ModelType, OutputFormat
from .registry import get_registry
from .template import get_renderer
from .validators import PromptOutputValidator
from .exceptions import (
    PromptNotFoundError,
    PromptValidationError,
    TemplateRenderError
)


class PromptManager:
    """提示词管理器 - 统一的提示词管理接口"""
    
    def __init__(self):
        self._registry = get_registry()
        self._renderer = get_renderer()
        
    @classmethod
    def get_prompt(cls, 
                   category: str, 
                   name: str, 
                   version: Optional[str] = None,
                   parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        获取渲染后的提示词
        
        Args:
            category: 分类
            name: 名称
            version: 版本（可选，默认使用最新版本）
            parameters: 模板参数（可选）
            
        Returns:
            渲染后的提示词字符串
        """
        instance = cls()
        prompt_obj = instance._registry.get(category, name, version)
        
        try:
            rendered = prompt_obj.render(parameters)
            logger.debug(f"提示词渲染成功: {category}.{name}-{prompt_obj.version}")
            return rendered
        except Exception as e:
            logger.error(f"提示词渲染失败: {category}.{name} - {str(e)}")
            raise
            
    @classmethod
    def get_prompt_object(cls, 
                         category: str, 
                         name: str, 
                         version: Optional[str] = None) -> BasePrompt:
        """
        获取提示词对象
        
        Args:
            category: 分类
            name: 名称
            version: 版本（可选）
            
        Returns:
            提示词对象
        """
        instance = cls()
        return instance._registry.get(category, name, version)
        
    @classmethod
    def register_prompt(cls, prompt: BasePrompt, is_default: bool = True) -> None:
        """
        注册提示词
        
        Args:
            prompt: 提示词对象
            is_default: 是否设为默认版本
        """
        instance = cls()
        instance._registry.register(prompt, is_default)
        
    @classmethod
    def list_categories(cls) -> List[str]:
        """列出所有分类"""
        instance = cls()
        return instance._registry.list_categories()
        
    @classmethod
    def list_prompts(cls, category: str) -> List[str]:
        """列出指定分类下的所有提示词"""
        instance = cls()
        return instance._registry.list_prompts(category)
        
    @classmethod
    def list_versions(cls, category: str, name: str) -> List[str]:
        """列出指定提示词的所有版本"""
        instance = cls()
        return instance._registry.list_versions(category, name)
        
    @classmethod
    def exists(cls, category: str, name: str, version: Optional[str] = None) -> bool:
        """检查提示词是否存在"""
        instance = cls()
        return instance._registry.exists(category, name, version)
        
    @classmethod
    def search_prompts(cls,
                      keyword: str = None,
                      category: str = None,
                      model_type: ModelType = None,
                      output_format: OutputFormat = None) -> List[Dict[str, str]]:
        """
        搜索提示词
        
        Args:
            keyword: 关键词
            category: 分类过滤
            model_type: 模型类型过滤
            output_format: 输出格式过滤
            
        Returns:
            匹配的提示词列表
        """
        instance = cls()
        results = instance._registry.search(keyword, category, model_type, output_format)
        
        return [
            {
                "category": cat,
                "name": name,
                "version": ver,
                "full_name": f"{cat}.{name}",
                "identifier": f"{cat}.{name}@{ver}"
            }
            for cat, name, ver in results
        ]
        
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取统计信息"""
        instance = cls()
        registry_stats = instance._registry.get_stats()
        
        return {
            "registry": registry_stats,
            "categories": cls.list_categories(),
            "total_categories": registry_stats["categories"],
            "total_prompts": registry_stats["prompts"],
            "total_versions": registry_stats["versions"]
        }
        
    @classmethod
    def validate_output(cls,
                       output: Union[str, Dict],
                       category: str,
                       name: str,
                       version: Optional[str] = None) -> Any:
        """
        验证提示词输出
        
        Args:
            output: 输出内容
            category: 提示词分类
            name: 提示词名称
            version: 提示词版本
            
        Returns:
            验证后的数据
        """
        instance = cls()
        prompt_obj = instance._registry.get(category, name, version)
        
        # 根据输出格式进行验证
        output_format = prompt_obj.metadata.output_format
        
        try:
            if output_format == OutputFormat.JSON:
                # 特殊处理解说文案和剧情分析
                if "narration" in name.lower() or "script" in name.lower():
                    return PromptOutputValidator.validate_narration_script(output)
                elif "plot" in name.lower() or "analysis" in name.lower():
                    return PromptOutputValidator.validate_plot_analysis(output)
                else:
                    return PromptOutputValidator.validate_json(output)
            else:
                return PromptOutputValidator.validate_by_format(output, output_format)
                
        except Exception as e:
            logger.error(f"输出验证失败 {category}.{name}: {str(e)}")
            raise PromptValidationError(f"输出验证失败: {str(e)}")
            
    @classmethod
    def get_prompt_info(cls, category: str, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        获取提示词详细信息
        
        Args:
            category: 分类
            name: 名称
            version: 版本
            
        Returns:
            提示词详细信息
        """
        instance = cls()
        prompt_obj = instance._registry.get(category, name, version)
        
        return {
            "metadata": {
                "name": prompt_obj.metadata.name,
                "category": prompt_obj.metadata.category,
                "version": prompt_obj.metadata.version,
                "description": prompt_obj.metadata.description,
                "model_type": prompt_obj.metadata.model_type.value,
                "output_format": prompt_obj.metadata.output_format.value,
                "author": prompt_obj.metadata.author,
                "created_at": prompt_obj.metadata.created_at.isoformat(),
                "updated_at": prompt_obj.metadata.updated_at.isoformat(),
                "tags": prompt_obj.metadata.tags,
                "parameters": prompt_obj.metadata.parameters
            },
            "template_preview": prompt_obj.get_template()[:500] + "..." if len(prompt_obj.get_template()) > 500 else prompt_obj.get_template(),
            "system_prompt": prompt_obj.get_system_prompt(),
            "examples_count": len(prompt_obj.get_examples()),
            "has_parameters": bool(prompt_obj.metadata.parameters)
        }
        
    @classmethod
    def export_prompts(cls, category: Optional[str] = None) -> Dict[str, Any]:
        """
        导出提示词配置
        
        Args:
            category: 分类过滤（可选）
            
        Returns:
            提示词配置数据
        """
        instance = cls()
        categories = [category] if category else instance._registry.list_categories()
        
        export_data = {
            "version": "1.0.0",
            "exported_at": instance._get_current_time(),
            "categories": {}
        }
        
        for cat in categories:
            export_data["categories"][cat] = {}
            prompts = instance._registry.list_prompts(cat)
            
            for prompt_name in prompts:
                versions = instance._registry.list_versions(cat, prompt_name)
                export_data["categories"][cat][prompt_name] = {}
                
                for ver in versions:
                    prompt_obj = instance._registry.get(cat, prompt_name, ver)
                    export_data["categories"][cat][prompt_name][ver] = prompt_obj.to_dict()
                    
        return export_data
        
    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().isoformat()


# 便捷函数
def get_prompt(category: str, name: str, version: str = None, **parameters) -> str:
    """获取提示词的便捷函数"""
    return PromptManager.get_prompt(category, name, version, parameters)


def validate_prompt_output(output: Union[str, Dict], category: str, name: str, version: str = None) -> Any:
    """验证提示词输出的便捷函数"""
    return PromptManager.validate_output(output, category, name, version)

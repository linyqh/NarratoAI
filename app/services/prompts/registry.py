#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : registry.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 提示词注册机制
"""

from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from loguru import logger

from .base import BasePrompt, ModelType, OutputFormat
from .exceptions import (
    PromptNotFoundError,
    PromptRegistrationError,
    PromptVersionError
)


class PromptRegistry:
    """提示词注册表"""
    
    def __init__(self):
        # 存储结构: {category: {name: {version: prompt}}}
        self._prompts: Dict[str, Dict[str, Dict[str, BasePrompt]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        # 默认版本映射: {category: {name: default_version}}
        self._default_versions: Dict[str, Dict[str, str]] = defaultdict(dict)
        
    def register(self, prompt: BasePrompt, is_default: bool = True) -> None:
        """
        注册提示词
        
        Args:
            prompt: 提示词实例
            is_default: 是否设为默认版本
        """
        category = prompt.category
        name = prompt.name
        version = prompt.version
        
        # 检查是否已存在相同版本
        if version in self._prompts[category][name]:
            raise PromptRegistrationError(
                category=category,
                name=name,
                reason=f"版本 {version} 已存在"
            )
            
        # 注册提示词
        self._prompts[category][name][version] = prompt
        
        # 设置默认版本
        if is_default or name not in self._default_versions[category]:
            self._default_versions[category][name] = version

        # 降级为 debug 日志，避免启动时的噪音
        logger.debug(f"已注册提示词: {category}.{name} v{version}")
        
    def get(self, category: str, name: str, version: Optional[str] = None) -> BasePrompt:
        """
        获取提示词
        
        Args:
            category: 分类
            name: 名称
            version: 版本，为None时使用默认版本
            
        Returns:
            提示词实例
        """
        if category not in self._prompts:
            raise PromptNotFoundError(category, name, version)
            
        if name not in self._prompts[category]:
            raise PromptNotFoundError(category, name, version)
            
        # 确定版本
        if version is None:
            if name not in self._default_versions[category]:
                raise PromptNotFoundError(category, name, version)
            version = self._default_versions[category][name]
            
        if version not in self._prompts[category][name]:
            raise PromptNotFoundError(category, name, version)
            
        return self._prompts[category][name][version]
        
    def list_categories(self) -> List[str]:
        """列出所有分类"""
        return list(self._prompts.keys())
        
    def list_prompts(self, category: str) -> List[str]:
        """列出指定分类下的所有提示词名称"""
        if category not in self._prompts:
            return []
        return list(self._prompts[category].keys())
        
    def list_versions(self, category: str, name: str) -> List[str]:
        """列出指定提示词的所有版本"""
        if category not in self._prompts or name not in self._prompts[category]:
            return []
        return list(self._prompts[category][name].keys())
        
    def get_default_version(self, category: str, name: str) -> Optional[str]:
        """获取默认版本"""
        return self._default_versions.get(category, {}).get(name)
        
    def set_default_version(self, category: str, name: str, version: str) -> None:
        """设置默认版本"""
        if (category not in self._prompts or 
            name not in self._prompts[category] or 
            version not in self._prompts[category][name]):
            raise PromptVersionError(category, name, version, "版本不存在")
            
        self._default_versions[category][name] = version
        logger.info(f"已设置默认版本: {category}.{name} -> v{version}")
        
    def exists(self, category: str, name: str, version: Optional[str] = None) -> bool:
        """检查提示词是否存在"""
        try:
            self.get(category, name, version)
            return True
        except PromptNotFoundError:
            return False
            
    def remove(self, category: str, name: str, version: Optional[str] = None) -> None:
        """移除提示词"""
        if version is None:
            # 移除所有版本
            if category in self._prompts and name in self._prompts[category]:
                del self._prompts[category][name]
                if name in self._default_versions.get(category, {}):
                    del self._default_versions[category][name]
                logger.info(f"已移除提示词所有版本: {category}.{name}")
        else:
            # 移除指定版本
            if (category in self._prompts and 
                name in self._prompts[category] and 
                version in self._prompts[category][name]):
                del self._prompts[category][name][version]
                
                # 如果移除的是默认版本，需要重新设置默认版本
                if (self._default_versions.get(category, {}).get(name) == version and
                    self._prompts[category][name]):
                    # 选择最新版本作为默认版本
                    new_default = max(self._prompts[category][name].keys())
                    self._default_versions[category][name] = new_default
                    logger.info(f"默认版本已更新: {category}.{name} -> v{new_default}")
                    
                logger.info(f"已移除提示词版本: {category}.{name} v{version}")
                
    def search(self, 
               keyword: str = None,
               category: str = None,
               model_type: ModelType = None,
               output_format: OutputFormat = None) -> List[Tuple[str, str, str]]:
        """
        搜索提示词
        
        Args:
            keyword: 关键词（在名称和描述中搜索）
            category: 分类过滤
            model_type: 模型类型过滤
            output_format: 输出格式过滤
            
        Returns:
            匹配的提示词列表 [(category, name, version), ...]
        """
        results = []
        
        categories = [category] if category else self._prompts.keys()
        
        for cat in categories:
            for name in self._prompts[cat]:
                for version, prompt in self._prompts[cat][name].items():
                    # 关键词过滤
                    if keyword:
                        if (keyword.lower() not in name.lower() and 
                            keyword.lower() not in prompt.metadata.description.lower()):
                            continue
                            
                    # 模型类型过滤
                    if model_type and prompt.metadata.model_type != model_type:
                        continue
                        
                    # 输出格式过滤
                    if output_format and prompt.metadata.output_format != output_format:
                        continue
                        
                    results.append((cat, name, version))
                    
        return results
        
    def get_stats(self) -> Dict[str, int]:
        """获取注册表统计信息"""
        total_prompts = 0
        total_versions = 0
        
        for category in self._prompts:
            for name in self._prompts[category]:
                total_prompts += 1
                total_versions += len(self._prompts[category][name])
                
        return {
            "categories": len(self._prompts),
            "prompts": total_prompts,
            "versions": total_versions
        }


# 全局注册表实例
_global_registry = PromptRegistry()


def get_registry() -> PromptRegistry:
    """获取全局注册表实例"""
    return _global_registry

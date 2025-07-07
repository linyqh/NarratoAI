#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : base.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 提示词基础类定义
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class ModelType(Enum):
    """模型类型枚举"""
    TEXT = "text"           # 文本模型
    VISION = "vision"       # 视觉模型
    MULTIMODAL = "multimodal"  # 多模态模型


class OutputFormat(Enum):
    """输出格式枚举"""
    TEXT = "text"           # 纯文本
    JSON = "json"           # JSON格式
    MARKDOWN = "markdown"   # Markdown格式
    STRUCTURED = "structured"  # 结构化数据


@dataclass
class PromptMetadata:
    """提示词元数据"""
    name: str                           # 提示词名称
    category: str                       # 分类
    version: str                        # 版本
    description: str                    # 描述
    model_type: ModelType              # 适用的模型类型
    output_format: OutputFormat        # 输出格式
    author: str = "viccy同学"       # 作者
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    updated_at: datetime = field(default_factory=datetime.now)  # 更新时间
    tags: List[str] = field(default_factory=list)  # 标签
    parameters: List[str] = field(default_factory=list)  # 支持的参数列表


class BasePrompt(ABC):
    """提示词基础类"""
    
    def __init__(self, metadata: PromptMetadata):
        self.metadata = metadata
        self._template = None
        self._system_prompt = None
        self._examples = []
        
    @property
    def name(self) -> str:
        """获取提示词名称"""
        return self.metadata.name
        
    @property
    def category(self) -> str:
        """获取提示词分类"""
        return self.metadata.category
        
    @property
    def version(self) -> str:
        """获取提示词版本"""
        return self.metadata.version
        
    @property
    def model_type(self) -> ModelType:
        """获取适用的模型类型"""
        return self.metadata.model_type
        
    @property
    def output_format(self) -> OutputFormat:
        """获取输出格式"""
        return self.metadata.output_format
        
    @abstractmethod
    def get_template(self) -> str:
        """获取提示词模板"""
        pass
        
    def get_system_prompt(self) -> Optional[str]:
        """获取系统提示词"""
        return self._system_prompt
        
    def get_examples(self) -> List[str]:
        """获取示例"""
        return self._examples.copy()
        
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """验证参数"""
        required_params = set(self.metadata.parameters)
        provided_params = set(parameters.keys())
        
        missing_params = required_params - provided_params
        if missing_params:
            from .exceptions import TemplateRenderError
            raise TemplateRenderError(
                template_name=self.name,
                error_message="缺少必需参数",
                missing_params=list(missing_params)
            )
        return True
        
    def render(self, parameters: Dict[str, Any] = None) -> str:
        """渲染提示词"""
        parameters = parameters or {}

        # 验证参数
        if self.metadata.parameters:
            self.validate_parameters(parameters)

        # 渲染模板 - 使用自定义的模板渲染器
        template = self.get_template()
        try:
            from .template import get_renderer
            renderer = get_renderer()
            return renderer.render(template, parameters)
        except Exception as e:
            from .exceptions import TemplateRenderError
            raise TemplateRenderError(
                template_name=self.name,
                error_message=f"模板渲染错误: {str(e)}",
                missing_params=[]
            )
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "metadata": {
                "name": self.metadata.name,
                "category": self.metadata.category,
                "version": self.metadata.version,
                "description": self.metadata.description,
                "model_type": self.metadata.model_type.value,
                "output_format": self.metadata.output_format.value,
                "author": self.metadata.author,
                "created_at": self.metadata.created_at.isoformat(),
                "updated_at": self.metadata.updated_at.isoformat(),
                "tags": self.metadata.tags,
                "parameters": self.metadata.parameters
            },
            "template": self.get_template(),
            "system_prompt": self.get_system_prompt(),
            "examples": self.get_examples()
        }


class TextPrompt(BasePrompt):
    """文本模型专用提示词"""
    
    def __init__(self, metadata: PromptMetadata):
        if metadata.model_type not in [ModelType.TEXT, ModelType.MULTIMODAL]:
            raise ValueError(f"TextPrompt只支持TEXT或MULTIMODAL模型类型，当前: {metadata.model_type}")
        super().__init__(metadata)


class VisionPrompt(BasePrompt):
    """视觉模型专用提示词"""
    
    def __init__(self, metadata: PromptMetadata):
        if metadata.model_type not in [ModelType.VISION, ModelType.MULTIMODAL]:
            raise ValueError(f"VisionPrompt只支持VISION或MULTIMODAL模型类型，当前: {metadata.model_type}")
        super().__init__(metadata)


class ParameterizedPrompt(BasePrompt):
    """支持参数化的提示词"""
    
    def __init__(self, metadata: PromptMetadata, required_parameters: List[str] = None):
        super().__init__(metadata)
        if required_parameters:
            self.metadata.parameters.extend(required_parameters)
            # 去重
            self.metadata.parameters = list(set(self.metadata.parameters))

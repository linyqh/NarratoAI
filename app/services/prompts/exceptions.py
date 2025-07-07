#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
@Project: NarratoAI
@File   : exceptions.py
@Author : viccy同学
@Date   : 2025/1/7
@Description: 提示词管理模块异常定义
"""


class PromptError(Exception):
    """提示词模块基础异常类"""
    pass


class PromptNotFoundError(PromptError):
    """提示词未找到异常"""
    
    def __init__(self, category: str, name: str, version: str = None):
        self.category = category
        self.name = name
        self.version = version
        
        if version:
            message = f"提示词未找到: {category}.{name} (版本: {version})"
        else:
            message = f"提示词未找到: {category}.{name}"
            
        super().__init__(message)


class PromptValidationError(PromptError):
    """提示词验证异常"""
    
    def __init__(self, message: str, validation_errors: list = None):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class TemplateRenderError(PromptError):
    """模板渲染异常"""
    
    def __init__(self, template_name: str, error_message: str, missing_params: list = None):
        self.template_name = template_name
        self.error_message = error_message
        self.missing_params = missing_params or []
        
        message = f"模板渲染失败 '{template_name}': {error_message}"
        if missing_params:
            message += f" (缺少参数: {', '.join(missing_params)})"
            
        super().__init__(message)


class PromptRegistrationError(PromptError):
    """提示词注册异常"""
    
    def __init__(self, category: str, name: str, reason: str):
        self.category = category
        self.name = name
        self.reason = reason
        
        message = f"提示词注册失败 {category}.{name}: {reason}"
        super().__init__(message)


class PromptVersionError(PromptError):
    """提示词版本异常"""
    
    def __init__(self, category: str, name: str, version: str, reason: str):
        self.category = category
        self.name = name
        self.version = version
        self.reason = reason
        
        message = f"提示词版本错误 {category}.{name} v{version}: {reason}"
        super().__init__(message)

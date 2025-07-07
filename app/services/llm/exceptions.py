"""
大模型服务异常类定义

定义了大模型服务中可能出现的各种异常类型，
提供统一的错误处理机制
"""

from typing import Optional, Dict, Any


class LLMServiceError(Exception):
    """大模型服务基础异常类"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self):
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class ProviderNotFoundError(LLMServiceError):
    """供应商未找到异常"""
    
    def __init__(self, provider_name: str):
        super().__init__(
            message=f"未找到大模型供应商: {provider_name}",
            error_code="PROVIDER_NOT_FOUND",
            details={"provider_name": provider_name}
        )


class ConfigurationError(LLMServiceError):
    """配置错误异常"""
    
    def __init__(self, message: str, config_key: Optional[str] = None):
        super().__init__(
            message=f"配置错误: {message}",
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key} if config_key else {}
        )


class APICallError(LLMServiceError):
    """API调用错误异常"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(
            message=f"API调用失败: {message}",
            error_code="API_CALL_ERROR",
            details={
                "status_code": status_code,
                "response_text": response_text
            }
        )


class ValidationError(LLMServiceError):
    """输出验证错误异常"""
    
    def __init__(self, message: str, validation_type: Optional[str] = None, invalid_data: Optional[Any] = None):
        super().__init__(
            message=f"输出验证失败: {message}",
            error_code="VALIDATION_ERROR",
            details={
                "validation_type": validation_type,
                "invalid_data": str(invalid_data) if invalid_data else None
            }
        )


class ModelNotSupportedError(LLMServiceError):
    """模型不支持异常"""
    
    def __init__(self, model_name: str, provider_name: str):
        super().__init__(
            message=f"供应商 {provider_name} 不支持模型 {model_name}",
            error_code="MODEL_NOT_SUPPORTED",
            details={
                "model_name": model_name,
                "provider_name": provider_name
            }
        )


class RateLimitError(LLMServiceError):
    """API速率限制异常"""
    
    def __init__(self, message: str = "API调用频率超限", retry_after: Optional[int] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_ERROR",
            details={"retry_after": retry_after}
        )


class AuthenticationError(LLMServiceError):
    """认证错误异常"""
    
    def __init__(self, message: str = "API密钥无效或权限不足"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR"
        )


class ContentFilterError(LLMServiceError):
    """内容过滤异常"""
    
    def __init__(self, message: str = "内容被安全过滤器阻止"):
        super().__init__(
            message=message,
            error_code="CONTENT_FILTER_ERROR"
        )

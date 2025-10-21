"""
大模型服务提供商基类定义

定义了统一的大模型服务接口，包括视觉模型和文本生成模型的抽象基类
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import PIL.Image
from loguru import logger

from .exceptions import LLMServiceError, ConfigurationError


class BaseLLMProvider(ABC):
    """大模型服务提供商基类"""
    
    def __init__(self, 
                 api_key: str,
                 model_name: str,
                 base_url: Optional[str] = None,
                 **kwargs):
        """
        初始化大模型服务提供商
        
        Args:
            api_key: API密钥
            model_name: 模型名称
            base_url: API基础URL
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.config = kwargs
        
        # 验证必要配置
        self._validate_config()
        
        # 初始化提供商特定设置
        self._initialize()
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """供应商名称"""
        pass
    
    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """支持的模型列表"""
        pass
    
    def _validate_config(self):
        """验证配置参数"""
        if not self.api_key:
            raise ConfigurationError("API密钥不能为空", "api_key")

        if not self.model_name:
            raise ConfigurationError("模型名称不能为空", "model_name")

        # 检查模型支持情况
        self._validate_model_support()
    
    def _validate_model_support(self):
        """验证模型支持情况（宽松模式，仅记录警告）"""
        from loguru import logger

        # LiteLLM 已提供统一的模型验证，传统 provider 使用宽松验证
        if self.model_name not in self.supported_models:
            logger.warning(
                f"模型 {self.model_name} 未在供应商 {self.provider_name} 的预定义支持列表中。"
                f"支持的模型列表: {self.supported_models}"
            )

    def _initialize(self):
        """初始化提供商特定设置，子类可重写"""
        pass
    
    @abstractmethod
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行API调用，子类必须实现"""
        pass
    
    def _handle_api_error(self, status_code: int, response_text: str) -> LLMServiceError:
        """处理API错误，返回适当的异常"""
        from .exceptions import APICallError, RateLimitError, AuthenticationError

        if status_code == 401:
            return AuthenticationError()
        elif status_code == 429:
            return RateLimitError()
        elif status_code in [502, 503, 504]:
            return APICallError(f"服务器错误 HTTP {status_code}", status_code, response_text)
        elif status_code == 524:
            return APICallError(f"服务器处理超时 HTTP {status_code}", status_code, response_text)
        else:
            return APICallError(f"HTTP {status_code}", status_code, response_text)


class VisionModelProvider(BaseLLMProvider):
    """视觉模型提供商基类"""
    
    @abstractmethod
    async def analyze_images(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10,
                           **kwargs) -> List[str]:
        """
        分析图片并返回结果
        
        Args:
            images: 图片路径列表或PIL图片对象列表
            prompt: 分析提示词
            batch_size: 批处理大小
            **kwargs: 其他参数
            
        Returns:
            分析结果列表
        """
        pass
    
    def _prepare_images(self, images: List[Union[str, Path, PIL.Image.Image]]) -> List[PIL.Image.Image]:
        """预处理图片，统一转换为PIL.Image对象"""
        processed_images = []
        
        for img in images:
            try:
                if isinstance(img, (str, Path)):
                    pil_img = PIL.Image.open(img)
                elif isinstance(img, PIL.Image.Image):
                    pil_img = img
                else:
                    logger.warning(f"不支持的图片类型: {type(img)}")
                    continue
                
                # 调整图片大小以优化性能
                if pil_img.size[0] > 1024 or pil_img.size[1] > 1024:
                    pil_img.thumbnail((1024, 1024), PIL.Image.Resampling.LANCZOS)
                
                processed_images.append(pil_img)
                
            except Exception as e:
                logger.error(f"加载图片失败 {img}: {str(e)}")
                continue
        
        return processed_images


class TextModelProvider(BaseLLMProvider):
    """文本生成模型提供商基类"""
    
    @abstractmethod
    async def generate_text(self,
                          prompt: str,
                          system_prompt: Optional[str] = None,
                          temperature: float = 1.0,
                          max_tokens: Optional[int] = None,
                          response_format: Optional[str] = None,
                          **kwargs) -> str:
        """
        生成文本内容
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 生成温度
            max_tokens: 最大token数
            response_format: 响应格式 ('json' 或 None)
            **kwargs: 其他参数
            
        Returns:
            生成的文本内容
        """
        pass
    
    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return messages

"""
大模型服务管理器

统一管理所有大模型服务提供商，提供简单的工厂方法来创建和获取服务实例
"""

from typing import Dict, Type, Optional
from loguru import logger

from app.config import config
from .base import VisionModelProvider, TextModelProvider
from .exceptions import ProviderNotFoundError, ConfigurationError


class LLMServiceManager:
    """大模型服务管理器"""
    
    # 注册的视觉模型提供商
    _vision_providers: Dict[str, Type[VisionModelProvider]] = {}
    
    # 注册的文本模型提供商  
    _text_providers: Dict[str, Type[TextModelProvider]] = {}
    
    # 缓存的提供商实例
    _vision_instance_cache: Dict[str, VisionModelProvider] = {}
    _text_instance_cache: Dict[str, TextModelProvider] = {}
    
    @classmethod
    def register_vision_provider(cls, name: str, provider_class: Type[VisionModelProvider]):
        """注册视觉模型提供商"""
        cls._vision_providers[name.lower()] = provider_class
        logger.debug(f"注册视觉模型提供商: {name}")
    
    @classmethod
    def register_text_provider(cls, name: str, provider_class: Type[TextModelProvider]):
        """注册文本模型提供商"""
        cls._text_providers[name.lower()] = provider_class
        logger.debug(f"注册文本模型提供商: {name}")

    @classmethod
    def _ensure_providers_registered(cls):
        """确保提供商已注册"""
        try:
            # 如果没有注册的提供商，强制导入providers模块
            if not cls._vision_providers or not cls._text_providers:
                from . import providers
                logger.debug("LLMServiceManager强制注册提供商")
        except Exception as e:
            logger.error(f"LLMServiceManager确保提供商注册时发生错误: {str(e)}")
    
    @classmethod
    def get_vision_provider(cls, provider_name: Optional[str] = None) -> VisionModelProvider:
        """
        获取视觉模型提供商实例

        Args:
            provider_name: 提供商名称，如果不指定则从配置中获取

        Returns:
            视觉模型提供商实例

        Raises:
            ProviderNotFoundError: 提供商未找到
            ConfigurationError: 配置错误
        """
        # 确保提供商已注册
        cls._ensure_providers_registered()

        # 确定提供商名称
        if not provider_name:
            provider_name = config.app.get('vision_llm_provider', 'gemini').lower()
        else:
            provider_name = provider_name.lower()

        # 检查缓存
        cache_key = f"vision_{provider_name}"
        if cache_key in cls._vision_instance_cache:
            return cls._vision_instance_cache[cache_key]

        # 检查提供商是否已注册
        if provider_name not in cls._vision_providers:
            raise ProviderNotFoundError(provider_name)
        
        # 获取配置
        config_prefix = f"vision_{provider_name}"
        api_key = config.app.get(f'{config_prefix}_api_key')
        model_name = config.app.get(f'{config_prefix}_model_name')
        base_url = config.app.get(f'{config_prefix}_base_url')
        
        if not api_key:
            raise ConfigurationError(f"缺少API密钥配置: {config_prefix}_api_key")
        
        if not model_name:
            raise ConfigurationError(f"缺少模型名称配置: {config_prefix}_model_name")
        
        # 创建提供商实例
        provider_class = cls._vision_providers[provider_name]
        try:
            instance = provider_class(
                api_key=api_key,
                model_name=model_name,
                base_url=base_url
            )
            
            # 缓存实例
            cls._vision_instance_cache[cache_key] = instance
            
            logger.info(f"创建视觉模型提供商实例: {provider_name} - {model_name}")
            return instance
            
        except Exception as e:
            logger.error(f"创建视觉模型提供商实例失败: {provider_name} - {str(e)}")
            raise ConfigurationError(f"创建提供商实例失败: {str(e)}")
    
    @classmethod
    def get_text_provider(cls, provider_name: Optional[str] = None) -> TextModelProvider:
        """
        获取文本模型提供商实例

        Args:
            provider_name: 提供商名称，如果不指定则从配置中获取

        Returns:
            文本模型提供商实例

        Raises:
            ProviderNotFoundError: 提供商未找到
            ConfigurationError: 配置错误
        """
        # 确保提供商已注册
        cls._ensure_providers_registered()

        # 确定提供商名称
        if not provider_name:
            provider_name = config.app.get('text_llm_provider', 'openai').lower()
        else:
            provider_name = provider_name.lower()

        # 检查缓存
        cache_key = f"text_{provider_name}"
        if cache_key in cls._text_instance_cache:
            return cls._text_instance_cache[cache_key]

        # 检查提供商是否已注册
        if provider_name not in cls._text_providers:
            raise ProviderNotFoundError(provider_name)
        
        # 获取配置
        config_prefix = f"text_{provider_name}"
        api_key = config.app.get(f'{config_prefix}_api_key')
        model_name = config.app.get(f'{config_prefix}_model_name')
        base_url = config.app.get(f'{config_prefix}_base_url')
        
        if not api_key:
            raise ConfigurationError(f"缺少API密钥配置: {config_prefix}_api_key")
        
        if not model_name:
            raise ConfigurationError(f"缺少模型名称配置: {config_prefix}_model_name")
        
        # 创建提供商实例
        provider_class = cls._text_providers[provider_name]
        try:
            instance = provider_class(
                api_key=api_key,
                model_name=model_name,
                base_url=base_url
            )
            
            # 缓存实例
            cls._text_instance_cache[cache_key] = instance
            
            logger.info(f"创建文本模型提供商实例: {provider_name} - {model_name}")
            return instance
            
        except Exception as e:
            logger.error(f"创建文本模型提供商实例失败: {provider_name} - {str(e)}")
            raise ConfigurationError(f"创建提供商实例失败: {str(e)}")
    
    @classmethod
    def clear_cache(cls):
        """清空提供商实例缓存"""
        cls._vision_instance_cache.clear()
        cls._text_instance_cache.clear()
        logger.info("已清空提供商实例缓存")
    
    @classmethod
    def list_vision_providers(cls) -> list[str]:
        """列出所有已注册的视觉模型提供商"""
        return list(cls._vision_providers.keys())
    
    @classmethod
    def list_text_providers(cls) -> list[str]:
        """列出所有已注册的文本模型提供商"""
        return list(cls._text_providers.keys())
    
    @classmethod
    def get_provider_info(cls) -> Dict[str, Dict[str, any]]:
        """获取所有提供商信息"""
        return {
            "vision_providers": {
                name: {
                    "class": provider_class.__name__,
                    "module": provider_class.__module__
                }
                for name, provider_class in cls._vision_providers.items()
            },
            "text_providers": {
                name: {
                    "class": provider_class.__name__,
                    "module": provider_class.__module__
                }
                for name, provider_class in cls._text_providers.items()
            }
        }

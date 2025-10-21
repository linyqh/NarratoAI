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

    # _ensure_providers_registered() 方法已移除
    # 现在使用显式注册机制（见 webui.py:main()）
    # 如需检查注册状态，使用 is_registered() 方法


    @classmethod
    def is_registered(cls) -> bool:
        """
        检查是否已注册提供商
        
        Returns:
            bool: 如果已注册任何提供商则返回 True
        """
        return len(cls._text_providers) > 0 or len(cls._vision_providers) > 0
    
    @classmethod
    def get_registered_providers_info(cls) -> dict:
        """
        获取已注册提供商的信息
        
        Returns:
            dict: 包含视觉和文本提供商列表的字典
        """
        return {
            "vision_providers": list(cls._vision_providers.keys()),
            "text_providers": list(cls._text_providers.keys())
        }
    
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
        # 检查提供商是否已注册
        if not cls.is_registered():
            raise ConfigurationError(
                "LLM 提供商未注册。请确保在应用启动时调用了 register_all_providers()。"
                f"\n当前已注册的提供商: {cls.get_registered_providers_info()}"
            )

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
        # 检查提供商是否已注册
        if not cls.is_registered():
            raise ConfigurationError(
                "LLM 提供商未注册。请确保在应用启动时调用了 register_all_providers()。"
                f"\n当前已注册的提供商: {cls.get_registered_providers_info()}"
            )

        # 确定提供商名称
        if not provider_name:
            provider_name = config.app.get('text_llm_provider', 'openai').lower()
        else:
            provider_name = provider_name.lower()

        logger.debug(f"获取文本模型提供商: {provider_name}")
        logger.debug(f"已注册的文本提供商: {list(cls._text_providers.keys())}")

        # 检查缓存
        cache_key = f"text_{provider_name}"
        if cache_key in cls._text_instance_cache:
            logger.debug(f"从缓存获取提供商实例: {provider_name}")
            return cls._text_instance_cache[cache_key]

        # 检查提供商是否已注册
        if provider_name not in cls._text_providers:
            logger.error(f"提供商未注册: {provider_name}")
            logger.error(f"已注册的提供商列表: {list(cls._text_providers.keys())}")
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

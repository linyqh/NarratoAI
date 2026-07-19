"""
LLM服务配置验证器

验证大模型服务的配置是否正确，并提供配置建议
"""

from typing import Dict, List, Any, Optional
from loguru import logger

from app.config import config
from .manager import LLMServiceManager
from .exceptions import ConfigurationError


class LLMConfigValidator:
    """LLM服务配置验证器"""
    
    @staticmethod
    def validate_all_configs() -> Dict[str, Any]:
        """
        验证所有LLM服务配置
        
        Returns:
            验证结果字典
        """
        results = {
            "vision_providers": {},
            "text_providers": {},
            "summary": {
                "total_vision_providers": 0,
                "valid_vision_providers": 0,
                "total_text_providers": 0,
                "valid_text_providers": 0,
                "errors": [],
                "warnings": []
            }
        }
        
        # 验证视觉模型提供商
        vision_providers = LLMServiceManager.list_vision_providers()
        results["summary"]["total_vision_providers"] = len(vision_providers)
        
        for provider in vision_providers:
            try:
                validation_result = LLMConfigValidator.validate_vision_provider(provider)
                results["vision_providers"][provider] = validation_result
                
                if validation_result["is_valid"]:
                    results["summary"]["valid_vision_providers"] += 1
                else:
                    results["summary"]["errors"].extend(validation_result["errors"])
                    
            except Exception as e:
                error_msg = f"验证视觉模型提供商 {provider} 时发生错误: {str(e)}"
                results["vision_providers"][provider] = {
                    "is_valid": False,
                    "errors": [error_msg],
                    "warnings": []
                }
                results["summary"]["errors"].append(error_msg)
        
        # 验证文本模型提供商
        text_providers = LLMServiceManager.list_text_providers()
        results["summary"]["total_text_providers"] = len(text_providers)
        
        for provider in text_providers:
            try:
                validation_result = LLMConfigValidator.validate_text_provider(provider)
                results["text_providers"][provider] = validation_result
                
                if validation_result["is_valid"]:
                    results["summary"]["valid_text_providers"] += 1
                else:
                    results["summary"]["errors"].extend(validation_result["errors"])
                    
            except Exception as e:
                error_msg = f"验证文本模型提供商 {provider} 时发生错误: {str(e)}"
                results["text_providers"][provider] = {
                    "is_valid": False,
                    "errors": [error_msg],
                    "warnings": []
                }
                results["summary"]["errors"].append(error_msg)
        
        return results
    
    @staticmethod
    def validate_vision_provider(provider_name: str) -> Dict[str, Any]:
        """
        验证视觉模型提供商配置
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            验证结果字典
        """
        result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "config": {}
        }
        
        try:
            # 获取配置
            config_prefix = f"vision_{provider_name}"
            api_key = config.app.get(f'{config_prefix}_api_key')
            model_name = config.app.get(f'{config_prefix}_model_name')
            base_url = config.app.get(f'{config_prefix}_base_url')
            
            result["config"] = {
                "api_key": "***" if api_key else None,
                "model_name": model_name,
                "base_url": base_url
            }
            
            # 验证必需配置
            if not api_key:
                result["errors"].append(f"缺少API密钥配置: {config_prefix}_api_key")
            
            if not model_name:
                result["errors"].append(f"缺少模型名称配置: {config_prefix}_model_name")
            
            # 尝试创建提供商实例
            if api_key and model_name:
                try:
                    provider_instance = LLMServiceManager.get_vision_provider(provider_name)
                    result["is_valid"] = True
                    logger.debug(f"视觉模型提供商 {provider_name} 配置验证成功")
                    
                except Exception as e:
                    result["errors"].append(f"创建提供商实例失败: {str(e)}")
            
            # 添加警告
            if not base_url:
                result["warnings"].append(f"未配置base_url，将使用默认值")
            
        except Exception as e:
            result["errors"].append(f"配置验证过程中发生错误: {str(e)}")
        
        return result
    
    @staticmethod
    def validate_text_provider(provider_name: str) -> Dict[str, Any]:
        """
        验证文本模型提供商配置
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            验证结果字典
        """
        result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "config": {}
        }
        
        try:
            # 获取配置
            config_prefix = f"text_{provider_name}"
            api_key = config.app.get(f'{config_prefix}_api_key')
            model_name = config.app.get(f'{config_prefix}_model_name')
            fast_model_name = config.app.get(f'{config_prefix}_fast_model_name')
            base_url = config.app.get(f'{config_prefix}_base_url')
            
            result["config"] = {
                "api_key": "***" if api_key else None,
                "model_name": model_name,
                "fast_model_name": fast_model_name,
                "base_url": base_url
            }
            
            # 验证必需配置
            if not api_key:
                result["errors"].append(f"缺少API密钥配置: {config_prefix}_api_key")
            
            if not model_name:
                result["errors"].append(f"缺少模型名称配置: {config_prefix}_model_name")
            
            # 尝试创建提供商实例
            if api_key and model_name:
                try:
                    provider_instance = LLMServiceManager.get_text_provider(provider_name)
                    result["is_valid"] = True
                    logger.debug(f"文本模型提供商 {provider_name} 配置验证成功")
                    
                except Exception as e:
                    result["errors"].append(f"创建提供商实例失败: {str(e)}")
            
            # 添加警告
            if not base_url:
                result["warnings"].append(f"未配置base_url，将使用默认值")
            
        except Exception as e:
            result["errors"].append(f"配置验证过程中发生错误: {str(e)}")
        
        return result
    
    @staticmethod
    def get_config_suggestions() -> Dict[str, Any]:
        """
        获取配置建议
        
        Returns:
            配置建议字典
        """
        suggestions = {
            "vision_providers": {},
            "text_providers": {},
            "general_tips": [
                "确保所有API密钥都已正确配置",
                "建议为每个提供商配置base_url以提高稳定性",
                "定期检查模型名称是否为最新版本",
                "建议配置多个提供商作为备用方案",
                "推荐使用 OpenAI 兼容接口，便于接入多家模型网关"
            ]
        }
        
        # 为每个视觉模型提供商提供建议
        vision_providers = LLMServiceManager.list_vision_providers()
        for provider in vision_providers:
            suggestions["vision_providers"][provider] = {
                "required_configs": [
                    f"vision_{provider}_api_key",
                    f"vision_{provider}_model_name"
                ],
                "optional_configs": [
                    f"vision_{provider}_base_url"
                ],
                "example_models": LLMConfigValidator._get_example_models(provider, "vision")
            }
        
        # 为每个文本模型提供商提供建议
        text_providers = LLMServiceManager.list_text_providers()
        for provider in text_providers:
            suggestions["text_providers"][provider] = {
                "required_configs": [
                    f"text_{provider}_api_key",
                    f"text_{provider}_model_name"
                ],
                "optional_configs": [
                    f"text_{provider}_base_url",
                    f"text_{provider}_fast_model_name",
                ],
                "example_models": LLMConfigValidator._get_example_models(provider, "text")
            }
        
        return suggestions
    
    @staticmethod
    def _get_example_models(provider_name: str, model_type: str) -> List[str]:
        """获取示例模型名称"""
        examples = {
            "gemini": {
                "vision": ["gemini-2.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"],
                "text": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
            },
            "openai": {
                "vision": ["gpt-4o", "gemini-2.0-flash-lite", "Qwen/Qwen2.5-VL-32B-Instruct"],
                "text": ["gpt-4o-mini", "deepseek-chat", "zai-org/GLM-4.6"]
            },
            "qwen": {
                "vision": ["qwen2.5-vl-32b-instruct"],
                "text": ["qwen-plus-1127", "qwen-turbo"]
            },
            "deepseek": {
                "vision": [],
                "text": ["deepseek-chat", "deepseek-reasoner"]
            },
            "siliconflow": {
                "vision": ["Qwen/Qwen2.5-VL-32B-Instruct"],
                "text": ["deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct"]
            }
        }
        
        return examples.get(provider_name, {}).get(model_type, [])
    
    @staticmethod
    def print_validation_report(validation_results: Dict[str, Any]):
        """
        打印验证报告
        
        Args:
            validation_results: 验证结果
        """
        summary = validation_results["summary"]
        
        print("\n" + "="*60)
        print("LLM服务配置验证报告")
        print("="*60)
        
        print(f"\n📊 总体统计:")
        print(f"  视觉模型提供商: {summary['valid_vision_providers']}/{summary['total_vision_providers']} 有效")
        print(f"  文本模型提供商: {summary['valid_text_providers']}/{summary['total_text_providers']} 有效")
        
        if summary["errors"]:
            print(f"\n❌ 错误 ({len(summary['errors'])}):")
            for error in summary["errors"]:
                print(f"  - {error}")
        
        if summary["warnings"]:
            print(f"\n⚠️  警告 ({len(summary['warnings'])}):")
            for warning in summary["warnings"]:
                print(f"  - {warning}")
        
        print(f"\n✅ 配置验证完成")
        print("="*60)

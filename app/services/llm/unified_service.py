"""
统一的大模型服务接口

提供简化的API接口，方便现有代码迁移到新的架构
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import PIL.Image
from loguru import logger

from .manager import LLMServiceManager
from .validators import OutputValidator
from .exceptions import LLMServiceError

# 提供商注册由 webui.py:main() 显式调用（见 LLM 提供商注册机制重构）
# 这样更可靠，错误也更容易调试


class UnifiedLLMService:
    """统一的大模型服务接口"""
    
    @staticmethod
    async def analyze_images(images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           provider: Optional[str] = None,
                           batch_size: int = 10,
                           **kwargs) -> List[str]:
        """
        分析图片内容
        
        Args:
            images: 图片路径列表或PIL图片对象列表
            prompt: 分析提示词
            provider: 视觉模型提供商名称，如果不指定则使用配置中的默认值
            batch_size: 批处理大小
            **kwargs: 其他参数
            
        Returns:
            分析结果列表
            
        Raises:
            LLMServiceError: 服务调用失败时抛出
        """
        try:
            # 获取视觉模型提供商
            vision_provider = LLMServiceManager.get_vision_provider(provider)
            
            # 执行图片分析
            results = await vision_provider.analyze_images(
                images=images,
                prompt=prompt,
                batch_size=batch_size,
                **kwargs
            )
            
            logger.info(f"图片分析完成，共处理 {len(images)} 张图片，生成 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"图片分析失败: {str(e)}")
            raise LLMServiceError(f"图片分析失败: {str(e)}")
    
    @staticmethod
    async def generate_text(prompt: str,
                          system_prompt: Optional[str] = None,
                          provider: Optional[str] = None,
                          temperature: float = 1.0,
                          max_tokens: Optional[int] = None,
                          response_format: Optional[str] = None,
                          **kwargs) -> str:
        """
        生成文本内容
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            provider: 文本模型提供商名称，如果不指定则使用配置中的默认值
            temperature: 生成温度
            max_tokens: 最大token数
            response_format: 响应格式 ('json' 或 None)
            **kwargs: 其他参数
            
        Returns:
            生成的文本内容
            
        Raises:
            LLMServiceError: 服务调用失败时抛出
        """
        try:
            # 获取文本模型提供商
            text_provider = LLMServiceManager.get_text_provider(provider)
            
            # 执行文本生成
            result = await text_provider.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                **kwargs
            )
            
            logger.info(f"文本生成完成，生成内容长度: {len(result)} 字符")
            return result
            
        except Exception as e:
            logger.error(f"文本生成失败: {str(e)}")
            raise LLMServiceError(f"文本生成失败: {str(e)}")
    
    @staticmethod
    async def generate_narration_script(prompt: str,
                                      provider: Optional[str] = None,
                                      temperature: float = 1.0,
                                      validate_output: bool = True,
                                      **kwargs) -> List[Dict[str, Any]]:
        """
        生成解说文案
        
        Args:
            prompt: 提示词
            provider: 文本模型提供商名称
            temperature: 生成温度
            validate_output: 是否验证输出格式
            **kwargs: 其他参数
            
        Returns:
            解说文案列表
            
        Raises:
            LLMServiceError: 服务调用失败时抛出
        """
        try:
            # 生成文本
            result = await UnifiedLLMService.generate_text(
                prompt=prompt,
                provider=provider,
                temperature=temperature,
                response_format="json",
                **kwargs
            )
            
            # 验证输出格式
            if validate_output:
                narration_items = OutputValidator.validate_narration_script(result)
                logger.info(f"解说文案生成并验证完成，共 {len(narration_items)} 个片段")
                return narration_items
            else:
                # 简单的JSON解析
                import json
                parsed_result = json.loads(result)
                if "items" in parsed_result:
                    return parsed_result["items"]
                else:
                    return parsed_result
                    
        except Exception as e:
            logger.error(f"解说文案生成失败: {str(e)}")
            raise LLMServiceError(f"解说文案生成失败: {str(e)}")
    
    @staticmethod
    async def analyze_subtitle(subtitle_content: str,
                             provider: Optional[str] = None,
                             temperature: float = 1.0,
                             validate_output: bool = True,
                             **kwargs) -> str:
        """
        分析字幕内容
        
        Args:
            subtitle_content: 字幕内容
            provider: 文本模型提供商名称
            temperature: 生成温度
            validate_output: 是否验证输出格式
            **kwargs: 其他参数
            
        Returns:
            分析结果
            
        Raises:
            LLMServiceError: 服务调用失败时抛出
        """
        try:
            # 构建分析提示词
            system_prompt = "你是一位专业的剧本分析师和剧情概括助手。请仔细分析字幕内容，提取关键剧情信息。"
            
            # 生成分析结果
            result = await UnifiedLLMService.generate_text(
                prompt=subtitle_content,
                system_prompt=system_prompt,
                provider=provider,
                temperature=temperature,
                **kwargs
            )
            
            # 验证输出格式
            if validate_output:
                validated_result = OutputValidator.validate_subtitle_analysis(result)
                logger.info("字幕分析完成并验证通过")
                return validated_result
            else:
                return result
                
        except Exception as e:
            logger.error(f"字幕分析失败: {str(e)}")
            raise LLMServiceError(f"字幕分析失败: {str(e)}")
    
    @staticmethod
    def get_provider_info() -> Dict[str, Any]:
        """
        获取所有提供商信息
        
        Returns:
            提供商信息字典
        """
        return LLMServiceManager.get_provider_info()
    
    @staticmethod
    def list_vision_providers() -> List[str]:
        """
        列出所有视觉模型提供商
        
        Returns:
            提供商名称列表
        """
        return LLMServiceManager.list_vision_providers()
    
    @staticmethod
    def list_text_providers() -> List[str]:
        """
        列出所有文本模型提供商
        
        Returns:
            提供商名称列表
        """
        return LLMServiceManager.list_text_providers()
    
    @staticmethod
    def clear_cache():
        """清空提供商实例缓存"""
        LLMServiceManager.clear_cache()
        logger.info("已清空大模型服务缓存")


# 为了向后兼容，提供一些便捷函数
async def analyze_images_unified(images: List[Union[str, Path, PIL.Image.Image]],
                               prompt: str,
                               provider: Optional[str] = None,
                               batch_size: int = 10) -> List[str]:
    """便捷的图片分析函数"""
    return await UnifiedLLMService.analyze_images(images, prompt, provider, batch_size)


async def generate_text_unified(prompt: str,
                              system_prompt: Optional[str] = None,
                              provider: Optional[str] = None,
                              temperature: float = 1.0,
                              response_format: Optional[str] = None) -> str:
    """便捷的文本生成函数"""
    return await UnifiedLLMService.generate_text(
        prompt, system_prompt, provider, temperature, response_format=response_format
    )

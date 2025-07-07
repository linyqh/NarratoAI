"""
迁移适配器

为现有代码提供向后兼容的接口，方便逐步迁移到新的LLM服务架构
"""

import asyncio
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import PIL.Image
from loguru import logger

from .unified_service import UnifiedLLMService
from .exceptions import LLMServiceError
# 导入新的提示词管理系统
from app.services.prompts import PromptManager

# 确保提供商已注册
def _ensure_providers_registered():
    """确保所有提供商都已注册"""
    try:
        from .manager import LLMServiceManager
        # 检查是否有已注册的提供商
        if not LLMServiceManager.list_text_providers() or not LLMServiceManager.list_vision_providers():
            # 如果没有注册的提供商，强制导入providers模块
            from . import providers
            logger.debug("迁移适配器强制注册LLM服务提供商")
    except Exception as e:
        logger.error(f"迁移适配器确保LLM服务提供商注册时发生错误: {str(e)}")

# 在模块加载时确保提供商已注册
_ensure_providers_registered()


def _run_async_safely(coro_func, *args, **kwargs):
    """
    安全地运行异步协程，处理各种事件循环情况

    Args:
        coro_func: 协程函数（不是协程对象）
        *args: 协程函数的位置参数
        **kwargs: 协程函数的关键字参数

    Returns:
        协程的执行结果
    """
    def run_in_new_loop():
        """在新的事件循环中运行协程"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_func(*args, **kwargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    try:
        # 尝试获取当前事件循环
        try:
            loop = asyncio.get_running_loop()
            # 如果有运行中的事件循环，使用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_new_loop)
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            return run_in_new_loop()
    except Exception as e:
        logger.error(f"异步执行失败: {str(e)}")
        raise LLMServiceError(f"异步执行失败: {str(e)}")


class LegacyLLMAdapter:
    """传统LLM接口适配器"""
    
    @staticmethod
    def create_vision_analyzer(provider: str, api_key: str, model: str, base_url: str = None):
        """
        创建视觉分析器实例 - 兼容原有接口
        
        Args:
            provider: 提供商名称
            api_key: API密钥
            model: 模型名称
            base_url: API基础URL
            
        Returns:
            适配器实例
        """
        return VisionAnalyzerAdapter(provider, api_key, model, base_url)
    
    @staticmethod
    def generate_narration(markdown_content: str, api_key: str, base_url: str, model: str) -> str:
        """
        生成解说文案 - 兼容原有接口
        
        Args:
            markdown_content: Markdown格式的视频帧分析内容
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            
        Returns:
            生成的解说文案JSON字符串
        """
        try:
            # 构建提示词
            prompt = f"""
我是一名荒野建造解说的博主，以下是一些同行的对标文案，请你深度学习并总结这些文案的风格特点跟内容特点：

<video_frame_description>
{markdown_content}
</video_frame_description>

请根据以上视频帧描述，生成引人入胜的解说文案。

<output>
{{
  "items": [
    {{
        "_id": 1,
        "timestamp": "00:00:05,390-00:00:10,430",
        "picture": "画面描述",
        "narration": "解说文案",
    }}
  ]
}}
</output>

<restriction>
1. 只输出 json 内容，不要输出其他任何说明性的文字
2. 解说文案的语言使用 简体中文
3. 严禁虚构画面，所有画面只能从 <video_frame_description> 中摘取
</restriction>
"""
            
            # 使用统一服务生成文案
            result = _run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="你是一名专业的短视频解说文案撰写专家。",
                temperature=1.5,
                response_format="json"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"生成解说文案失败: {str(e)}")
            return f"生成解说文案失败: {str(e)}"


class VisionAnalyzerAdapter:
    """视觉分析器适配器"""
    
    def __init__(self, provider: str, api_key: str, model: str, base_url: str = None):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
    
    async def analyze_images(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10) -> List[str]:
        """
        分析图片 - 兼容原有接口
        
        Args:
            images: 图片列表
            prompt: 分析提示词
            batch_size: 批处理大小
            
        Returns:
            分析结果列表
        """
        try:
            # 使用统一服务分析图片
            results = await UnifiedLLMService.analyze_images(
                images=images,
                prompt=prompt,
                provider=self.provider,
                batch_size=batch_size
            )
            
            return results
            
        except Exception as e:
            logger.error(f"图片分析失败: {str(e)}")
            raise


class SubtitleAnalyzerAdapter:
    """字幕分析器适配器"""

    def __init__(self, api_key: str, model: str, base_url: str, provider: str = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.provider = provider or "openai"

    def _run_async_safely(self, coro_func, *args, **kwargs):
        """安全地运行异步协程"""
        return _run_async_safely(coro_func, *args, **kwargs)

    def _clean_json_output(self, output: str) -> str:
        """清理JSON输出，移除markdown标记等"""
        import re

        # 移除可能的markdown代码块标记
        output = re.sub(r'^```json\s*', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```\s*$', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```.*$', '', output, flags=re.MULTILINE)

        # 移除开头和结尾的```标记
        output = re.sub(r'^```', '', output)
        output = re.sub(r'```$', '', output)

        # 移除前后空白字符
        output = output.strip()

        return output
    
    def analyze_subtitle(self, subtitle_content: str) -> Dict[str, Any]:
        """
        分析字幕内容 - 兼容原有接口
        
        Args:
            subtitle_content: 字幕内容
            
        Returns:
            分析结果字典
        """
        try:
            # 使用统一服务分析字幕
            result = self._run_async_safely(
                UnifiedLLMService.analyze_subtitle,
                subtitle_content=subtitle_content,
                provider=self.provider,
                temperature=1.0
            )
            
            return {
                "status": "success",
                "analysis": result,
                "model": self.model,
                "temperature": 1.0
            }
            
        except Exception as e:
            logger.error(f"字幕分析失败: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "temperature": 1.0
            }
    
    def generate_narration_script(self, short_name: str, plot_analysis: str, temperature: float = 0.7) -> Dict[str, Any]:
        """
        生成解说文案 - 兼容原有接口
        
        Args:
            short_name: 短剧名称
            plot_analysis: 剧情分析内容
            temperature: 生成温度
            
        Returns:
            生成结果字典
        """
        try:
            # 使用新的提示词管理系统构建提示词
            prompt = PromptManager.get_prompt(
                category="short_drama_narration",
                name="script_generation",
                parameters={
                    "drama_name": short_name,
                    "plot_analysis": plot_analysis
                }
            )
            
            # 使用统一服务生成文案
            result = self._run_async_safely(
                UnifiedLLMService.generate_text,
                prompt=prompt,
                system_prompt="你是一位专业的短视频解说脚本撰写专家。",
                provider=self.provider,
                temperature=temperature,
                response_format="json"
            )
            
            # 清理JSON输出
            cleaned_result = self._clean_json_output(result)

            # 新的提示词系统返回的是包含items数组的JSON格式
            # 为了保持向后兼容，我们需要直接返回这个JSON字符串
            # 调用方会期望这是一个包含items数组的JSON字符串
            return {
                "status": "success",
                "narration_script": cleaned_result,
                "model": self.model,
                "temperature": temperature
            }
            
        except Exception as e:
            logger.error(f"解说文案生成失败: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "temperature": temperature
            }


# 为了向后兼容，提供一些全局函数
def create_vision_analyzer(provider: str, api_key: str, model: str, base_url: str = None):
    """创建视觉分析器 - 全局函数"""
    return LegacyLLMAdapter.create_vision_analyzer(provider, api_key, model, base_url)


def generate_narration(markdown_content: str, api_key: str, base_url: str, model: str) -> str:
    """生成解说文案 - 全局函数"""
    return LegacyLLMAdapter.generate_narration(markdown_content, api_key, base_url, model)

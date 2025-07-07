"""
硅基流动API提供商实现

支持硅基流动的视觉模型和文本生成模型
"""

import asyncio
import base64
import io
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import PIL.Image
from openai import OpenAI
from loguru import logger

from ..base import VisionModelProvider, TextModelProvider
from ..exceptions import APICallError


class SiliconflowVisionProvider(VisionModelProvider):
    """硅基流动视觉模型提供商"""
    
    @property
    def provider_name(self) -> str:
        return "siliconflow"
    
    @property
    def supported_models(self) -> List[str]:
        return [
            "Qwen/Qwen2.5-VL-32B-Instruct",
            "Qwen/Qwen2-VL-72B-Instruct",
            "deepseek-ai/deepseek-vl2",
            "OpenGVLab/InternVL2-26B"
        ]
    
    def _initialize(self):
        """初始化硅基流动客户端"""
        if not self.base_url:
            self.base_url = "https://api.siliconflow.cn/v1"
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    async def analyze_images(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10,
                           **kwargs) -> List[str]:
        """
        使用硅基流动API分析图片
        
        Args:
            images: 图片列表
            prompt: 分析提示词
            batch_size: 批处理大小
            **kwargs: 其他参数
            
        Returns:
            分析结果列表
        """
        logger.info(f"开始分析 {len(images)} 张图片，使用硅基流动")
        
        # 预处理图片
        processed_images = self._prepare_images(images)
        
        # 分批处理
        results = []
        for i in range(0, len(processed_images), batch_size):
            batch = processed_images[i:i + batch_size]
            logger.info(f"处理第 {i//batch_size + 1} 批，共 {len(batch)} 张图片")
            
            try:
                result = await self._analyze_batch(batch, prompt)
                results.append(result)
            except Exception as e:
                logger.error(f"批次 {i//batch_size + 1} 处理失败: {str(e)}")
                results.append(f"批次处理失败: {str(e)}")
        
        return results
    
    async def _analyze_batch(self, batch: List[PIL.Image.Image], prompt: str) -> str:
        """分析一批图片"""
        # 构建消息内容
        content = [{"type": "text", "text": prompt}]
        
        # 添加图片
        for img in batch:
            base64_image = self._image_to_base64(img)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
        
        # 构建消息
        messages = [{
            "role": "user",
            "content": content
        }]
        
        # 调用API
        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model_name,
            messages=messages,
            max_tokens=4000,
            temperature=1.0
        )
        
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            raise APICallError("硅基流动API返回空响应")
    
    def _image_to_base64(self, img: PIL.Image.Image) -> str:
        """将PIL图片转换为base64编码"""
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=85)
        img_bytes = img_buffer.getvalue()
        return base64.b64encode(img_bytes).decode('utf-8')
    
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行API调用 - 由于使用OpenAI SDK，这个方法主要用于兼容基类"""
        pass


class SiliconflowTextProvider(TextModelProvider):
    """硅基流动文本生成提供商"""
    
    @property
    def provider_name(self) -> str:
        return "siliconflow"
    
    @property
    def supported_models(self) -> List[str]:
        return [
            "deepseek-ai/DeepSeek-R1",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "meta-llama/Llama-3.1-70B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
            "01-ai/Yi-1.5-34B-Chat"
        ]
    
    def _initialize(self):
        """初始化硅基流动客户端"""
        if not self.base_url:
            self.base_url = "https://api.siliconflow.cn/v1"
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    async def generate_text(self,
                          prompt: str,
                          system_prompt: Optional[str] = None,
                          temperature: float = 1.0,
                          max_tokens: Optional[int] = None,
                          response_format: Optional[str] = None,
                          **kwargs) -> str:
        """
        使用硅基流动API生成文本
        
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
        # 构建消息列表
        messages = self._build_messages(prompt, system_prompt)
        
        # 构建请求参数
        request_params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # 处理JSON格式输出
        if response_format == "json":
            if self._supports_response_format():
                request_params["response_format"] = {"type": "json_object"}
            else:
                # 对于不支持response_format的模型，在提示词中添加约束
                messages[-1]["content"] += "\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"
        
        try:
            # 发送API请求
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                **request_params
            )
            
            # 提取生成的内容
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                
                # 对于不支持response_format的模型，清理输出
                if response_format == "json" and not self._supports_response_format():
                    content = self._clean_json_output(content)
                
                logger.debug(f"硅基流动API调用成功，消耗tokens: {response.usage.total_tokens if response.usage else 'N/A'}")
                return content
            else:
                raise APICallError("硅基流动API返回空响应")
                
        except Exception as e:
            logger.error(f"硅基流动API调用失败: {str(e)}")
            raise APICallError(f"硅基流动API调用失败: {str(e)}")
    
    def _supports_response_format(self) -> bool:
        """检查模型是否支持response_format参数"""
        # DeepSeek R1 和 V3 不支持 response_format=json_object
        unsupported_models = [
            "deepseek-ai/deepseek-r1",
            "deepseek-ai/deepseek-v3"
        ]
        
        return not any(unsupported in self.model_name.lower() for unsupported in unsupported_models)
    
    def _clean_json_output(self, output: str) -> str:
        """清理JSON输出，移除markdown标记等"""
        import re
        
        # 移除可能的markdown代码块标记
        output = re.sub(r'^```json\s*', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```\s*$', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```.*$', '', output, flags=re.MULTILINE)
        
        # 移除前后空白字符
        output = output.strip()
        
        return output
    
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行API调用 - 由于使用OpenAI SDK，这个方法主要用于兼容基类"""
        pass

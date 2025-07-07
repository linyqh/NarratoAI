"""
OpenAI兼容的Gemini视觉分析器
使用标准OpenAI格式调用Gemini代理服务
"""

import json
from typing import List, Union, Dict
import os
from pathlib import Path
from loguru import logger
from tqdm import tqdm
import asyncio
from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_exponential
import requests
import PIL.Image
import traceback
import base64
import io
from app.utils import utils


class GeminiOpenAIAnalyzer:
    """OpenAI兼容的Gemini视觉分析器类"""

    def __init__(self, model_name: str = "gemini-2.0-flash-exp", api_key: str = None, base_url: str = None):
        """初始化OpenAI兼容的Gemini分析器"""
        if not api_key:
            raise ValueError("必须提供API密钥")
        
        if not base_url:
            raise ValueError("必须提供OpenAI兼容的代理端点URL")

        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

        # 初始化OpenAI客户端
        self._configure_client()

    def _configure_client(self):
        """配置OpenAI兼容的客户端"""
        from openai import OpenAI
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        logger.info(f"配置OpenAI兼容Gemini代理，端点: {self.base_url}, 模型: {self.model_name}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, Exception))
    )
    async def _generate_content_with_retry(self, prompt, batch):
        """使用重试机制调用OpenAI兼容的Gemini代理"""
        try:
            return await self._generate_with_openai_api(prompt, batch)
        except Exception as e:
            logger.warning(f"OpenAI兼容Gemini代理请求异常: {str(e)}")
            raise

    async def _generate_with_openai_api(self, prompt, batch):
        """使用OpenAI兼容接口生成内容"""
        # 将PIL图片转换为base64编码
        image_contents = []
        for img in batch:
            # 将PIL图片转换为字节流
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=85)
            img_bytes = img_buffer.getvalue()
            
            # 转换为base64
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_base64}"
                }
            })
        
        # 构建OpenAI格式的消息
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *image_contents
                ]
            }
        ]
        
        # 调用OpenAI兼容接口
        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model_name,
            messages=messages,
            max_tokens=4000,
            temperature=1.0
        )
        
        # 创建兼容的响应对象
        class CompatibleResponse:
            def __init__(self, text):
                self.text = text
        
        return CompatibleResponse(response.choices[0].message.content)

    async def analyze_images(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10) -> List[str]:
        """
        分析图片并返回结果

        Args:
            images: 图片路径列表或PIL图片对象列表
            prompt: 分析提示词
            batch_size: 批处理大小

        Returns:
            分析结果列表
        """
        logger.info(f"开始分析 {len(images)} 张图片，使用OpenAI兼容Gemini代理")
        
        # 加载图片
        loaded_images = []
        for img in images:
            if isinstance(img, (str, Path)):
                try:
                    pil_img = PIL.Image.open(img)
                    # 调整图片大小以优化性能
                    if pil_img.size[0] > 1024 or pil_img.size[1] > 1024:
                        pil_img.thumbnail((1024, 1024), PIL.Image.Resampling.LANCZOS)
                    loaded_images.append(pil_img)
                except Exception as e:
                    logger.error(f"加载图片失败 {img}: {str(e)}")
                    continue
            elif isinstance(img, PIL.Image.Image):
                loaded_images.append(img)
            else:
                logger.warning(f"不支持的图片类型: {type(img)}")
                continue

        if not loaded_images:
            raise ValueError("没有有效的图片可以分析")

        # 分批处理
        results = []
        total_batches = (len(loaded_images) + batch_size - 1) // batch_size
        
        for i in tqdm(range(0, len(loaded_images), batch_size), 
                     desc="分析图片批次", total=total_batches):
            batch = loaded_images[i:i + batch_size]
            
            try:
                response = await self._generate_content_with_retry(prompt, batch)
                results.append(response.text)
                
                # 添加延迟以避免API限流
                if i + batch_size < len(loaded_images):
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"分析批次 {i//batch_size + 1} 失败: {str(e)}")
                results.append(f"分析失败: {str(e)}")

        logger.info(f"完成图片分析，共处理 {len(results)} 个批次")
        return results

    def analyze_images_sync(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10) -> List[str]:
        """
        同步版本的图片分析方法
        """
        return asyncio.run(self.analyze_images(images, prompt, batch_size))

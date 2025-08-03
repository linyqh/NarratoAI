"""
原生Gemini API提供商实现

使用Google原生Gemini API进行视觉分析和文本生成
"""

import asyncio
import base64
import io
import requests
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import PIL.Image
from loguru import logger

from ..base import VisionModelProvider, TextModelProvider
from ..exceptions import APICallError, ContentFilterError


class GeminiVisionProvider(VisionModelProvider):
    """原生Gemini视觉模型提供商"""
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    @property
    def supported_models(self) -> List[str]:
        return [
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ]
    
    def _initialize(self):
        """初始化Gemini特定设置"""
        if not self.base_url:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    async def analyze_images(self,
                           images: List[Union[str, Path, PIL.Image.Image]],
                           prompt: str,
                           batch_size: int = 10,
                           **kwargs) -> List[str]:
        """
        使用原生Gemini API分析图片
        
        Args:
            images: 图片列表
            prompt: 分析提示词
            batch_size: 批处理大小
            **kwargs: 其他参数
            
        Returns:
            分析结果列表
        """
        logger.info(f"开始分析 {len(images)} 张图片，使用原生Gemini API")
        
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
        # 构建请求数据
        parts = [{"text": prompt}]
        
        # 添加图片数据
        for img in batch:
            img_data = self._image_to_base64(img)
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_data
                }
            })
        
        payload = {
            "systemInstruction": {
                "parts": [{"text": "你是一位专业的视觉内容分析师，请仔细分析图片内容并提供详细描述。"}]
            },
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 1.0,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 4000,
                "candidateCount": 1
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
        
        # 发送API请求
        response_data = await self._make_api_call(payload)
        
        # 解析响应
        return self._parse_vision_response(response_data)
    
    def _image_to_base64(self, img: PIL.Image.Image) -> str:
        """将PIL图片转换为base64编码"""
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=85)
        img_bytes = img_buffer.getvalue()
        return base64.b64encode(img_bytes).decode('utf-8')
    
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行原生Gemini API调用，包含重试机制"""
        from app.config import config

        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"

        max_retries = config.app.get('llm_max_retries', 3)
        base_timeout = config.app.get('llm_vision_timeout', 120)

        for attempt in range(max_retries):
            try:
                # 根据尝试次数调整超时时间
                timeout = base_timeout * (attempt + 1)
                logger.debug(f"Gemini API调用尝试 {attempt + 1}/{max_retries}，超时设置: {timeout}秒")

                response = await asyncio.to_thread(
                    requests.post,
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "NarratoAI/1.0"
                    },
                    timeout=timeout
                )

                if response.status_code == 200:
                    return response.json()

                # 处理特定的错误状态码
                if response.status_code == 429:
                    # 速率限制，等待后重试
                    wait_time = 30 * (attempt + 1)
                    logger.warning(f"Gemini API速率限制，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status_code in [502, 503, 504, 524]:
                    # 服务器错误或超时，可以重试
                    if attempt < max_retries - 1:
                        wait_time = 10 * (attempt + 1)
                        logger.warning(f"Gemini API服务器错误 {response.status_code}，等待 {wait_time} 秒后重试")
                        await asyncio.sleep(wait_time)
                        continue

                # 其他错误，直接抛出
                error = self._handle_api_error(response.status_code, response.text)
                raise error

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 15 * (attempt + 1)
                    logger.warning(f"Gemini API请求超时，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise APICallError("Gemini API请求超时，已达到最大重试次数")
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)
                    logger.warning(f"Gemini API网络错误: {str(e)}，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise APICallError(f"Gemini API网络错误: {str(e)}")

        # 如果所有重试都失败了
        raise APICallError("Gemini API调用失败，已达到最大重试次数")
    
    def _parse_vision_response(self, response_data: Dict[str, Any]) -> str:
        """解析视觉分析响应"""
        if "candidates" not in response_data or not response_data["candidates"]:
            raise APICallError("原生Gemini API返回无效响应")
        
        candidate = response_data["candidates"][0]
        
        # 检查是否被安全过滤阻止
        if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
            raise ContentFilterError("内容被Gemini安全过滤器阻止")
        
        if "content" not in candidate or "parts" not in candidate["content"]:
            raise APICallError("原生Gemini API返回内容格式错误")
        
        # 提取文本内容
        result = ""
        for part in candidate["content"]["parts"]:
            if "text" in part:
                result += part["text"]
        
        if not result.strip():
            raise APICallError("原生Gemini API返回空内容")
        
        return result


class GeminiTextProvider(TextModelProvider):
    """原生Gemini文本生成提供商"""
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    @property
    def supported_models(self) -> List[str]:
        return [
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ]
    
    def _initialize(self):
        """初始化Gemini特定设置"""
        if not self.base_url:
            self.base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    async def generate_text(self,
                          prompt: str,
                          system_prompt: Optional[str] = None,
                          temperature: float = 1.0,
                          max_tokens: Optional[int] = 30000,
                          response_format: Optional[str] = None,
                          **kwargs) -> str:
        """
        使用原生Gemini API生成文本
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 生成温度
            max_tokens: 最大token数
            response_format: 响应格式
            **kwargs: 其他参数
            
        Returns:
            生成的文本内容
        """
        # 构建请求数据
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 60000,
                "candidateCount": 1
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", 
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
        
        # 添加系统提示词
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        
        # 如果需要JSON格式，调整提示词和配置
        if response_format == "json":
            # 使用更温和的JSON格式约束
            enhanced_prompt = f"{prompt}\n\n请以JSON格式输出结果。"
            payload["contents"][0]["parts"][0]["text"] = enhanced_prompt
            # 移除可能导致问题的stopSequences
            # payload["generationConfig"]["stopSequences"] = ["```", "注意", "说明"]
        
        # 记录请求信息
        # logger.debug(f"Gemini文本生成请求: {payload}")

        # 发送API请求
        response_data = await self._make_api_call(payload)

        # 解析响应
        return self._parse_text_response(response_data)
    
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行原生Gemini API调用，包含重试机制"""
        from app.config import config

        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"

        max_retries = config.app.get('llm_max_retries', 3)
        base_timeout = config.app.get('llm_text_timeout', 180)  # 文本生成任务使用更长的基础超时时间

        for attempt in range(max_retries):
            try:
                # 根据尝试次数调整超时时间
                timeout = base_timeout * (attempt + 1)
                logger.debug(f"Gemini文本API调用尝试 {attempt + 1}/{max_retries}，超时设置: {timeout}秒")

                response = await asyncio.to_thread(
                    requests.post,
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "NarratoAI/1.0"
                    },
                    timeout=timeout
                )

                if response.status_code == 200:
                    return response.json()

                # 处理特定的错误状态码
                if response.status_code == 429:
                    # 速率限制，等待后重试
                    wait_time = 30 * (attempt + 1)
                    logger.warning(f"Gemini API速率限制，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status_code in [502, 503, 504, 524]:
                    # 服务器错误或超时，可以重试
                    if attempt < max_retries - 1:
                        wait_time = 15 * (attempt + 1)
                        logger.warning(f"Gemini API服务器错误 {response.status_code}，等待 {wait_time} 秒后重试")
                        await asyncio.sleep(wait_time)
                        continue

                # 其他错误，直接抛出
                error = self._handle_api_error(response.status_code, response.text)
                raise error

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 20 * (attempt + 1)
                    logger.warning(f"Gemini文本API请求超时，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise APICallError("Gemini文本API请求超时，已达到最大重试次数")
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 15 * (attempt + 1)
                    logger.warning(f"Gemini文本API网络错误: {str(e)}，等待 {wait_time} 秒后重试")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise APICallError(f"Gemini文本API网络错误: {str(e)}")

        # 如果所有重试都失败了
        raise APICallError("Gemini文本API调用失败，已达到最大重试次数")
    
    def _parse_text_response(self, response_data: Dict[str, Any]) -> str:
        """解析文本生成响应"""
        logger.debug(f"Gemini API响应数据: {response_data}")

        if "candidates" not in response_data or not response_data["candidates"]:
            logger.error(f"Gemini API返回无效响应结构: {response_data}")
            raise APICallError("原生Gemini API返回无效响应")

        candidate = response_data["candidates"][0]
        logger.debug(f"Gemini候选响应: {candidate}")

        # 检查完成原因
        finish_reason = candidate.get("finishReason", "UNKNOWN")
        logger.debug(f"Gemini完成原因: {finish_reason}")

        # 检查是否被安全过滤阻止
        if finish_reason == "SAFETY":
            safety_ratings = candidate.get("safetyRatings", [])
            logger.warning(f"内容被Gemini安全过滤器阻止，安全评级: {safety_ratings}")
            raise ContentFilterError("内容被Gemini安全过滤器阻止")

        # 检查是否因为其他原因停止
        if finish_reason in ["RECITATION", "OTHER"]:
            logger.warning(f"Gemini因为{finish_reason}原因停止生成")
            raise APICallError(f"Gemini因为{finish_reason}原因停止生成")

        if "content" not in candidate:
            logger.error(f"Gemini候选响应中缺少content字段: {candidate}")
            raise APICallError("原生Gemini API返回内容格式错误")

        if "parts" not in candidate["content"]:
            logger.error(f"Gemini内容中缺少parts字段: {candidate['content']}")
            raise APICallError("原生Gemini API返回内容格式错误")

        # 提取文本内容
        result = ""
        for part in candidate["content"]["parts"]:
            if "text" in part:
                result += part["text"]

        if not result.strip():
            logger.error(f"Gemini API返回空文本内容，完整响应: {response_data}")
            raise APICallError("原生Gemini API返回空内容")

        logger.debug(f"Gemini成功生成内容，长度: {len(result)}")
        return result

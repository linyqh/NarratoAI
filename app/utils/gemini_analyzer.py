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


class VisionAnalyzer:
    """原生Gemini视觉分析器类"""

    def __init__(self, model_name: str = "gemini-2.0-flash-exp", api_key: str = None, base_url: str = None):
        """初始化视觉分析器"""
        if not api_key:
            raise ValueError("必须提供API密钥")

        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"

        # 初始化配置
        self._configure_client()

    def _configure_client(self):
        """配置原生Gemini API客户端"""
        # 使用原生Gemini REST API
        self.client = None
        logger.info(f"配置原生Gemini API，端点: {self.base_url}, 模型: {self.model_name}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException)
    )
    async def _generate_content_with_retry(self, prompt, batch):
        """使用重试机制调用原生Gemini API"""
        try:
            return await self._generate_with_gemini_api(prompt, batch)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Gemini API请求异常: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Gemini API生成内容时发生错误: {str(e)}")
            raise

    async def _generate_with_gemini_api(self, prompt, batch):
        """使用原生Gemini REST API生成内容"""
        # 将PIL图片转换为base64编码
        image_parts = []
        for img in batch:
            # 将PIL图片转换为字节流
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG', quality=85)  # 优化图片质量
            img_bytes = img_buffer.getvalue()

            # 转换为base64
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            image_parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_base64
                }
            })

        # 构建符合官方文档的请求数据
        request_data = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    *image_parts
                ]
            }],
            "generationConfig": {
                "temperature": 1.0,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
                "candidateCount": 1,
                "stopSequences": []
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

        # 构建请求URL
        url = f"{self.base_url}/models/{self.model_name}:generateContent"

        # 发送请求
        response = await asyncio.to_thread(
            requests.post,
            url,
            json=request_data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key
            },
            timeout=120  # 增加超时时间
        )

        # 处理HTTP错误
        if response.status_code == 429:
            raise requests.exceptions.RequestException(f"API配额限制: {response.text}")
        elif response.status_code == 400:
            raise Exception(f"请求参数错误: {response.text}")
        elif response.status_code == 403:
            raise Exception(f"API密钥无效或权限不足: {response.text}")
        elif response.status_code != 200:
            raise Exception(f"Gemini API请求失败: {response.status_code} - {response.text}")

        response_data = response.json()

        # 检查响应格式
        if "candidates" not in response_data or not response_data["candidates"]:
            raise Exception("Gemini API返回无效响应，可能触发了安全过滤")

        candidate = response_data["candidates"][0]

        # 检查是否被安全过滤阻止
        if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
            raise Exception("内容被Gemini安全过滤器阻止")

        if "content" not in candidate or "parts" not in candidate["content"]:
            raise Exception("Gemini API返回内容格式错误")

        # 提取文本内容
        text_content = ""
        for part in candidate["content"]["parts"]:
            if "text" in part:
                text_content += part["text"]

        if not text_content.strip():
            raise Exception("Gemini API返回空内容")

        # 创建兼容的响应对象
        class CompatibleResponse:
            def __init__(self, text):
                self.text = text

        return CompatibleResponse(text_content)

    async def analyze_images(self,
                           images: Union[List[str], List[PIL.Image.Image]],
                           prompt: str,
                           batch_size: int) -> List[Dict]:
        """批量分析多张图片"""
        try:
            # 加载图片
            if isinstance(images[0], str):
                images = self.load_images(images)

            # 验证图片列表
            if not images:
                raise ValueError("图片列表为空")

            # 验证每个图片对象
            valid_images = []
            for i, img in enumerate(images):
                if not isinstance(img, PIL.Image.Image):
                    logger.error(f"无效的图片对象，索引 {i}: {type(img)}")
                    continue
                valid_images.append(img)

            if not valid_images:
                raise ValueError("没有有效的图片对象")

            images = valid_images
            results = []
            # 视频帧总数除以批量处理大小，如果有小数则+1
            batches_needed = len(images) // batch_size
            if len(images) % batch_size > 0:
                batches_needed += 1
                
            logger.debug(f"视频帧总数:{len(images)}, 每批处理 {batch_size} 帧, 需要访问 VLM {batches_needed} 次")

            with tqdm(total=batches_needed, desc="分析进度") as pbar:
                for i in range(0, len(images), batch_size):
                    batch = images[i:i + batch_size]
                    retry_count = 0

                    while retry_count < 3:
                        try:
                            # 在每个批次处理前添加小延迟
                            # if i > 0:
                            #     await asyncio.sleep(2)

                            # 确保每个批次的图片都是有效的
                            valid_batch = [img for img in batch if isinstance(img, PIL.Image.Image)]
                            if not valid_batch:
                                raise ValueError(f"批次 {i // batch_size} 中没有有效的图片")

                            response = await self._generate_content_with_retry(prompt, valid_batch)
                            results.append({
                                'batch_index': i // batch_size,
                                'images_processed': len(valid_batch),
                                'response': response.text,
                                'model_used': self.model_name
                            })
                            break

                        except Exception as e:
                            retry_count += 1
                            error_msg = f"批次 {i // batch_size} 处理出错: {str(e)}"
                            logger.error(error_msg)

                            if retry_count >= 3:
                                results.append({
                                    'batch_index': i // batch_size,
                                    'images_processed': len(batch),
                                    'error': error_msg,
                                    'model_used': self.model_name
                                })
                            else:
                                logger.info(f"批次 {i // batch_size} 处理失败，等待60秒后重试当前批次...")
                                await asyncio.sleep(60)

                    pbar.update(1)

            return results

        except Exception as e:
            error_msg = f"图片分析过程中发生错误: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def save_results_to_txt(self, results: List[Dict], output_dir: str):
        """将分析结果保存到txt文件"""
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        for result in results:
            if not result.get('image_paths'):
                continue

            response_text = result['response']
            image_paths = result['image_paths']

            # 从文件名中提取时间戳并转换为标准格式
            def format_timestamp(img_path):
                # 从文件名中提取时间部分
                timestamp = Path(img_path).stem.split('_')[-1]
                try:
                    # 将时间转换为秒
                    seconds = utils.time_to_seconds(timestamp.replace('_', ':'))
                    # 转换为 HH:MM:SS,mmm 格式
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    seconds_remainder = seconds % 60
                    whole_seconds = int(seconds_remainder)
                    milliseconds = int((seconds_remainder - whole_seconds) * 1000)
                    
                    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"
                except Exception as e:
                    logger.error(f"时间戳格式转换错误: {timestamp}, {str(e)}")
                    return timestamp

            start_timestamp = format_timestamp(image_paths[0])
            end_timestamp = format_timestamp(image_paths[-1])
            
            txt_path = os.path.join(output_dir, f"frame_{start_timestamp}_{end_timestamp}.txt")

            # 保存结果到txt文件
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(response_text.strip())
            logger.info(f"已保存分析结果到: {txt_path}")

    def load_images(self, image_paths: List[str]) -> List[PIL.Image.Image]:
        """
        加载多张图片
        Args:
            image_paths: 图片路径列表
        Returns:
            加载后的PIL Image对象列表
        """
        images = []
        failed_images = []

        for img_path in image_paths:
            try:
                if not os.path.exists(img_path):
                    logger.error(f"图片文件不存在: {img_path}")
                    failed_images.append(img_path)
                    continue

                img = PIL.Image.open(img_path)
                # 确保图片被完全加载
                img.load()
                # 转换为RGB模式
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)

            except Exception as e:
                logger.error(f"无法加载图片 {img_path}: {str(e)}")
                failed_images.append(img_path)

        if failed_images:
            logger.warning(f"以下图片加载失败:\n{json.dumps(failed_images, indent=2, ensure_ascii=False)}")

        if not images:
            raise ValueError("没有成功加载任何图片")

        return images
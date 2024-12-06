import json
from typing import List, Union, Dict
import os
from pathlib import Path
from loguru import logger
from tqdm import tqdm
import asyncio
from tenacity import retry, stop_after_attempt, RetryError, wait_exponential
from openai import OpenAI
import PIL.Image
import base64
import io
import traceback


class QwenAnalyzer:
    """千问视觉分析器类"""

    def __init__(self, model_name: str = "qwen-vl-max-latest", api_key: str = None, base_url: str = None):
        """
        初始化千问视觉分析器
        
        Args:
            model_name: 模型名称，默认使用 qwen-vl-max-latest
            api_key: 阿里云API密钥
            base_url: API基础URL，如果为None则使用默认值
        """
        if not api_key:
            raise ValueError("必须提供API密钥")

        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"

        # 配置API客户端
        self._configure_client()

    def _configure_client(self):
        """
        配置API客户端
        使用最简化的参数配置，避免不必要的参数
        """
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except Exception as e:
            logger.error(f"初始化OpenAI客户端失败: {str(e)}")
            raise

    def _image_to_base64(self, image: PIL.Image.Image) -> str:
        """
        将PIL图片对象转换为base64字符串
        """
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _generate_content_with_retry(self, prompt: str, batch: List[PIL.Image.Image]):
        """使用重试机制的内部方法来调用千问API"""
        try:
            # 构建消息内容
            content = []

            # 添加图片
            for img in batch:
                base64_image = self._image_to_base64(img)
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                })

            # 添加文本提示
            content.append({
                "type": "text",
                "text": prompt
            })

            # 调用API
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": content
                }]
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"API调用错误: {str(e)}")
            raise RetryError("API调用失败")

    async def analyze_images(self,
                             images: Union[List[str], List[PIL.Image.Image]],
                             prompt: str,
                             batch_size: int = 5) -> List[Dict]:
        """
        批量分析多张图片
        Args:
            images: 图片路径列表或PIL图片对象列表
            prompt: 分析提示词
            batch_size: 批处理大小
        Returns:
            分析结果列表
        """
        try:
            # 保存原始图片路径（如果是路径列表的话）
            original_paths = images if isinstance(images[0], str) else None

            # 加载图片
            if isinstance(images[0], str):
                logger.info("正在加载图片...")
                images = self.load_images(images)

            # 验证图片列表
            if not images:
                raise ValueError("图片列表为空")

            # 验证每个图片对象
            valid_images = []
            valid_paths = []
            for i, img in enumerate(images):
                if not isinstance(img, PIL.Image.Image):
                    logger.error(f"无效的图片对象，索引 {i}: {type(img)}")
                    continue
                valid_images.append(img)
                if original_paths:
                    valid_paths.append(original_paths[i])

            if not valid_images:
                raise ValueError("没有有效的图片对象")

            images = valid_images
            results = []
            total_batches = (len(images) + batch_size - 1) // batch_size

            with tqdm(total=total_batches, desc="分析进度") as pbar:
                for i in range(0, len(images), batch_size):
                    batch = images[i:i + batch_size]
                    batch_paths = valid_paths[i:i + batch_size] if valid_paths else None
                    retry_count = 0

                    while retry_count < 3:
                        try:
                            # 在每个批次处理前��加小延迟
                            if i > 0:
                                await asyncio.sleep(2)

                            # 确保每个批次的图片都是有效的
                            valid_batch = [img for img in batch if isinstance(img, PIL.Image.Image)]
                            if not valid_batch:
                                raise ValueError(f"批次 {i // batch_size} 中没有有效的图片")

                            response = await self._generate_content_with_retry(prompt, valid_batch)
                            result_dict = {
                                'batch_index': i // batch_size,
                                'images_processed': len(valid_batch),
                                'response': response,
                                'model_used': self.model_name
                            }

                            # 添加图片路径信息（如果有的话）
                            if batch_paths:
                                result_dict['image_paths'] = batch_paths

                            results.append(result_dict)
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
                                    'model_used': self.model_name,
                                    'image_paths': batch_paths if batch_paths else []
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

        for i, result in enumerate(results):
            response_text = result['response']

            # 如果有图片路径信息，���用它来生成文件名
            if result.get('image_paths'):
                image_paths = result['image_paths']
                img_name_start = Path(image_paths[0]).stem.split('_')[-1]
                img_name_end = Path(image_paths[-1]).stem.split('_')[-1]
                file_name = f"frame_{img_name_start}_{img_name_end}.txt"
            else:
                # 如果没有路径信息，使用批次索引
                file_name = f"batch_{result['batch_index']}.txt"

            txt_path = os.path.join(output_dir, file_name)

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

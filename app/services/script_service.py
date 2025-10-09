import os
import json
import time
import asyncio
import requests
from app.utils import video_processor
from loguru import logger
from typing import List, Dict, Any, Callable

from app.utils import utils, gemini_analyzer, video_processor
from app.utils.script_generator import ScriptProcessor
from app.config import config


class ScriptGenerator:
    def __init__(self):
        self.temp_dir = utils.temp_dir()
        self.keyframes_dir = os.path.join(self.temp_dir, "keyframes")
        
    async def generate_script(
        self,
        video_path: str,
        video_theme: str = "",
        custom_prompt: str = "",
        frame_interval_input: int = 5,
        skip_seconds: int = 0,
        threshold: int = 30,
        vision_batch_size: int = 5,
        vision_llm_provider: str = "gemini",
        progress_callback: Callable[[float, str], None] = None
    ) -> List[Dict[Any, Any]]:
        """
        生成视频脚本的核心逻辑
        
        Args:
            video_path: 视频文件路径
            video_theme: 视频主题
            custom_prompt: 自定义提示词
            skip_seconds: 跳过开始的秒数
            threshold: 差异���值
            vision_batch_size: 视觉处理批次大小
            vision_llm_provider: 视觉模型提供商
            progress_callback: 进度回调函数
            
        Returns:
            List[Dict]: 生成的视频脚本
        """
        if progress_callback is None:
            progress_callback = lambda p, m: None
            
        try:
            # 提取关键帧
            progress_callback(10, "正在提取关键帧...")
            keyframe_files = await self._extract_keyframes(
                video_path,
                skip_seconds,
                threshold
            )

            normalized_provider = (vision_llm_provider or "gemini").lower()

            if normalized_provider in {"gemini", "gemini(openai)"}:
                script = await self._process_with_gemini(
                    keyframe_files,
                    video_theme,
                    custom_prompt,
                    vision_batch_size,
                    progress_callback,
                    normalized_provider
                )
            elif normalized_provider == "narratoapi":
                script = await self._process_with_narrato(
                    keyframe_files,
                    video_theme,
                    custom_prompt,
                    vision_batch_size,
                    progress_callback
                )
            else:
                raise ValueError(f"Unsupported vision provider: {vision_llm_provider}")
                
            return json.loads(script) if isinstance(script, str) else script
            
        except Exception as e:
            logger.exception("Generate script failed")
            raise
            
    async def _extract_keyframes(
        self,
        video_path: str,
        skip_seconds: int,
        threshold: int
    ) -> List[str]:
        """提取视频关键帧"""
        video_hash = utils.md5(video_path + str(os.path.getmtime(video_path)))
        video_keyframes_dir = os.path.join(self.keyframes_dir, video_hash)
        
        # 检查缓存
        keyframe_files = []
        if os.path.exists(video_keyframes_dir):
            for filename in sorted(os.listdir(video_keyframes_dir)):
                if filename.endswith('.jpg'):
                    keyframe_files.append(os.path.join(video_keyframes_dir, filename))
                    
            if keyframe_files:
                logger.info(f"Using cached keyframes: {video_keyframes_dir}")
                return keyframe_files
                
        # 提取新的关键帧
        os.makedirs(video_keyframes_dir, exist_ok=True)
        
        try:
            processor = video_processor.VideoProcessor(video_path)
            processor.process_video_pipeline(
                output_dir=video_keyframes_dir,
                skip_seconds=skip_seconds,
                threshold=threshold
            )

            for filename in sorted(os.listdir(video_keyframes_dir)):
                if filename.endswith('.jpg'):
                    keyframe_files.append(os.path.join(video_keyframes_dir, filename))
                    
            return keyframe_files
            
        except Exception as e:
            if os.path.exists(video_keyframes_dir):
                import shutil
                shutil.rmtree(video_keyframes_dir)
            raise
            
    async def _process_with_gemini(
        self,
        keyframe_files: List[str],
        video_theme: str,
        custom_prompt: str,
        vision_batch_size: int,
        progress_callback: Callable[[float, str], None],
        vision_provider: str
    ) -> str:
        """使用Gemini处理视频帧"""
        progress_callback(30, "正在初始化视觉分析器...")

        # 获取Gemini配置
        vision_api_key = config.app.get("vision_gemini_api_key")
        vision_model = config.app.get("vision_gemini_model_name")
        vision_base_url = config.app.get("vision_gemini_base_url")

        if not vision_api_key or not vision_model:
            raise ValueError("未配置 Gemini API Key 或者模型")

        # 根据提供商类型选择合适的分析器
        provider = (vision_provider or "gemini").lower()

        if provider == 'gemini(openai)':
            # 使用OpenAI兼容的Gemini代理
            from app.utils.gemini_openai_analyzer import GeminiOpenAIAnalyzer
            analyzer = GeminiOpenAIAnalyzer(
                model_name=vision_model,
                api_key=vision_api_key,
                base_url=vision_base_url
            )
        else:
            # 使用原生Gemini分析器
            analyzer = gemini_analyzer.VisionAnalyzer(
                model_name=vision_model,
                api_key=vision_api_key,
                base_url=vision_base_url
            )

        progress_callback(40, "正在分析关键帧...")

        # 执行异步分析
        results = await analyzer.analyze_images(
            images=keyframe_files,
            prompt=config.app.get('vision_analysis_prompt'),
            batch_size=vision_batch_size
        )

        progress_callback(60, "正在整理分析结果...")
        
        # 合并所有批次的分析结果
        frame_analysis = ""
        prev_batch_files = None

        for result in results:
            if 'error' in result:
                logger.warning(f"批次 {result['batch_index']} 处理出现警告: {result['error']}")
                continue
                
            batch_files = self._get_batch_files(keyframe_files, result, vision_batch_size)
            first_timestamp, last_timestamp, _ = self._get_batch_timestamps(batch_files, prev_batch_files)
            
            # 添加带时间戳的分��结果
            frame_analysis += f"\n=== {first_timestamp}-{last_timestamp} ===\n"
            frame_analysis += result['response']
            frame_analysis += "\n"
            
            prev_batch_files = batch_files
        
        if not frame_analysis.strip():
            raise Exception("未能生成有效的帧分析结果")
        
        progress_callback(70, "正在生成脚本...")

        # 构建帧内容列表
        frame_content_list = []
        prev_batch_files = None

        for result in results:
            if 'error' in result:
                continue
            
            batch_files = self._get_batch_files(keyframe_files, result, vision_batch_size)
            _, _, timestamp_range = self._get_batch_timestamps(batch_files, prev_batch_files)
            
            frame_content = {
                "timestamp": timestamp_range,
                "picture": result['response'],
                "narration": "",
                "OST": 2
            }
            frame_content_list.append(frame_content)
            prev_batch_files = batch_files

        if not frame_content_list:
            raise Exception("没有有效的帧内容可以处理")

        progress_callback(90, "正在生成文案...")
        
        # 获取文本生��配置
        text_provider = config.app.get('text_llm_provider', 'gemini').lower()
        text_api_key = config.app.get(f'text_{text_provider}_api_key')
        text_model = config.app.get(f'text_{text_provider}_model_name')
        text_base_url = config.app.get(f'text_{text_provider}_base_url')

        # 根据提供商类型选择合适的处理器
        if text_provider == 'gemini(openai)':
            # 使用OpenAI兼容的Gemini代理
            from app.utils.script_generator import GeminiOpenAIGenerator
            generator = GeminiOpenAIGenerator(
                model_name=text_model,
                api_key=text_api_key,
                prompt=custom_prompt,
                base_url=text_base_url
            )
            processor = ScriptProcessor(
                model_name=text_model,
                api_key=text_api_key,
                base_url=text_base_url,
                prompt=custom_prompt,
                video_theme=video_theme
            )
            processor.generator = generator
        else:
            # 使用标准处理器（包括原生Gemini）
            processor = ScriptProcessor(
                model_name=text_model,
                api_key=text_api_key,
                base_url=text_base_url,
                prompt=custom_prompt,
                video_theme=video_theme
            )

        return processor.process_frames(frame_content_list)

    async def _process_with_narrato(
        self,
        keyframe_files: List[str],
        video_theme: str,
        custom_prompt: str,
        vision_batch_size: int,
        progress_callback: Callable[[float, str], None]
    ) -> str:
        """使用NarratoAPI处理视频帧"""
        # 创建临时目录
        temp_dir = utils.temp_dir("narrato")
        
        # 打包关键帧
        progress_callback(30, "正在打包关键帧...")
        zip_path = os.path.join(temp_dir, f"keyframes_{int(time.time())}.zip")
        
        try:
            if not utils.create_zip(keyframe_files, zip_path):
                raise Exception("打包关键帧失败")
            
            # 获取API配置
            api_url = config.app.get("narrato_api_url")
            api_key = config.app.get("narrato_api_key")
            
            if not api_key:
                raise ValueError("未配置 Narrato API Key")
            
            headers = {
                'X-API-Key': api_key,
                'accept': 'application/json'
            }
            
            api_params = {
                'batch_size': vision_batch_size,
                'use_ai': False,
                'start_offset': 0,
                'vision_model': config.app.get('narrato_vision_model', 'gemini-1.5-flash'),
                'vision_api_key': config.app.get('narrato_vision_key'),
                'llm_model': config.app.get('narrato_llm_model', 'qwen-plus'),
                'llm_api_key': config.app.get('narrato_llm_key'),
                'custom_prompt': custom_prompt
            }
            
            progress_callback(40, "正在上传文件...")
            with open(zip_path, 'rb') as f:
                files = {'file': (os.path.basename(zip_path), f, 'application/x-zip-compressed')}
                response = requests.post(
                    f"{api_url}/video/analyze",
                    headers=headers, 
                    params=api_params, 
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
            
            task_data = response.json()
            task_id = task_data["data"].get('task_id')
            if not task_id:
                raise Exception(f"无效的API��应: {response.text}")
            
            progress_callback(50, "正在等待分析结果...")
            retry_count = 0
            max_retries = 60
            
            while retry_count < max_retries:
                try:
                    status_response = requests.get(
                        f"{api_url}/video/tasks/{task_id}",
                        headers=headers,
                        timeout=10
                    )
                    status_response.raise_for_status()
                    task_status = status_response.json()['data']
                    
                    if task_status['status'] == 'SUCCESS':
                        return task_status['result']['data']
                    elif task_status['status'] in ['FAILURE', 'RETRY']:
                        raise Exception(f"任务失败: {task_status.get('error')}")
                    
                    retry_count += 1
                    time.sleep(2)
                    
                except requests.RequestException as e:
                    logger.warning(f"获取任务状态失败，重试中: {str(e)}")
                    retry_count += 1
                    time.sleep(2)
                    continue
            
            raise Exception("任务执行超时")
            
        finally:
            # 清理临时文件
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {str(e)}")

    def _get_batch_files(
        self, 
        keyframe_files: List[str], 
        result: Dict[str, Any], 
        batch_size: int
    ) -> List[str]:
        """获取当前批次的图片文件"""
        batch_start = result['batch_index'] * batch_size
        batch_end = min(batch_start + batch_size, len(keyframe_files))
        return keyframe_files[batch_start:batch_end]

    def _get_batch_timestamps(
        self, 
        batch_files: List[str], 
        prev_batch_files: List[str] = None
    ) -> tuple[str, str, str]:
        """获取一批文件的时间戳范围，支持毫秒级精度"""
        if not batch_files:
            logger.warning("Empty batch files")
            return "00:00:00,000", "00:00:00,000", "00:00:00,000-00:00:00,000"
            
        if len(batch_files) == 1 and prev_batch_files and len(prev_batch_files) > 0:
            first_frame = os.path.basename(prev_batch_files[-1])
            last_frame = os.path.basename(batch_files[0])
        else:
            first_frame = os.path.basename(batch_files[0])
            last_frame = os.path.basename(batch_files[-1])
        
        first_time = first_frame.split('_')[2].replace('.jpg', '')
        last_time = last_frame.split('_')[2].replace('.jpg', '')
        
        def format_timestamp(time_str: str) -> str:
            """将时间字符串转换为 HH:MM:SS,mmm 格式"""
            try:
                if len(time_str) < 4:
                    logger.warning(f"Invalid timestamp format: {time_str}")
                    return "00:00:00,000"
                
                # 处理毫秒部分
                if ',' in time_str:
                    time_part, ms_part = time_str.split(',')
                    ms = int(ms_part)
                else:
                    time_part = time_str
                    ms = 0
                
                # 处理时分秒
                parts = time_part.split(':')
                if len(parts) == 3:  # HH:MM:SS
                    h, m, s = map(int, parts)
                elif len(parts) == 2:  # MM:SS
                    h = 0
                    m, s = map(int, parts)
                else:  # SS
                    h = 0
                    m = 0
                    s = int(parts[0])
                    
                # 处理进位
                if s >= 60:
                    m += s // 60
                    s = s % 60
                if m >= 60:
                    h += m // 60
                    m = m % 60
                    
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                
            except Exception as e:
                logger.error(f"时间戳格式转换错误 {time_str}: {str(e)}")
                return "00:00:00,000"
        
        first_timestamp = format_timestamp(first_time)
        last_timestamp = format_timestamp(last_time)
        timestamp_range = f"{first_timestamp}-{last_timestamp}"
        
        return first_timestamp, last_timestamp, timestamp_range
import os
import json
import traceback
from loguru import logger
import tiktoken
from typing import List, Dict
from datetime import datetime
from openai import OpenAI
import google.generativeai as genai
import time


class BaseGenerator:
    def __init__(self, model_name: str, api_key: str, prompt: str):
        self.model_name = model_name
        self.api_key = api_key
        self.base_prompt = prompt
        self.conversation_history = []
        self.chunk_overlap = 50
        self.last_chunk_ending = ""
        self.default_params = {
            "temperature": 0.7,
            "max_tokens": 500,
            "top_p": 0.9,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.5
        }

    def _try_generate(self, messages: list, params: dict = None) -> str:
        max_attempts = 3
        tolerance = 5
        
        for attempt in range(max_attempts):
            try:
                response = self._generate(messages, params or self.default_params)
                return self._process_response(response)
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise
                logger.warning(f"Generation attempt {attempt + 1} failed: {str(e)}")
                continue
        return ""

    def _generate(self, messages: list, params: dict) -> any:
        raise NotImplementedError
        
    def _process_response(self, response: any) -> str:
        return response

    def generate_script(self, scene_description: str, word_count: int) -> str:
        """生成脚本的通用方法"""
        prompt = f"""{self.base_prompt}

上一段文案的结尾：{self.last_chunk_ending if self.last_chunk_ending else "这是第一段，无需考虑上文"}

当前画面描述：{scene_description}

请确保新生成的文案与上文自然衔接，保持叙事的连贯性和趣味性。
不要出现除了文案以外的其他任何内容；
严格字数要求：{word_count}字，允许误差±5字。"""

        messages = [
            {"role": "system", "content": self.base_prompt},
            {"role": "user", "content": prompt}
        ]

        try:
            generated_script = self._try_generate(messages, self.default_params)
            
            # 更新上下文
            if generated_script:
                self.last_chunk_ending = generated_script[-self.chunk_overlap:] if len(
                    generated_script) > self.chunk_overlap else generated_script
                
            return generated_script
            
        except Exception as e:
            logger.error(f"Script generation failed: {str(e)}")
            raise


class OpenAIGenerator(BaseGenerator):
    """OpenAI API 生成器实现"""
    def __init__(self, model_name: str, api_key: str, prompt: str, base_url: str):
        super().__init__(model_name, api_key, prompt)
        base_url = base_url or f"https://api.openai.com/v1"
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.max_tokens = 5000
        
        # OpenAI特定参数
        self.default_params = {
            **self.default_params,
            "stream": False,
            "user": "script_generator"
        }
        
        # 初始化token计数器
        try:
            self.encoding = tiktoken.encoding_for_model(self.model_name)
        except KeyError:
            logger.warning(f"未找到模型 {self.model_name} 的专用编码器，使用默认编码器")
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _generate(self, messages: list, params: dict) -> any:
        """实现OpenAI特定的生成逻辑"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                **params
            )
            return response
        except Exception as e:
            logger.error(f"OpenAI generation error: {str(e)}")
            raise

    def _process_response(self, response: any) -> str:
        """处理OpenAI的响应"""
        if not response or not response.choices:
            raise ValueError("Invalid response from OpenAI API")
        return response.choices[0].message.content.strip()

    def _count_tokens(self, messages: list) -> int:
        """计算token数量"""
        num_tokens = 0
        for message in messages:
            num_tokens += 3
            for key, value in message.items():
                num_tokens += len(self.encoding.encode(str(value)))
                if key == "role":
                    num_tokens += 1
        num_tokens += 3
        return num_tokens


class GeminiGenerator(BaseGenerator):
    """Google Gemini API 生成器实现"""
    def __init__(self, model_name: str, api_key: str, prompt: str):
        super().__init__(model_name, api_key, prompt)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        
        # Gemini特定参数
        self.default_params = {
            "temperature": self.default_params["temperature"],
            "top_p": self.default_params["top_p"],
            "candidate_count": 1,
            "stop_sequences": None
        }

    def _generate(self, messages: list, params: dict) -> any:
        """实现Gemini特定的生成逻辑"""
        while True:
            try:
                # 转换消息格式为Gemini格式
                prompt = "\n".join([m["content"] for m in messages])
                response = self.model.generate_content(
                    prompt,
                    generation_config=params
                )
                
                # 检查响应是否包含有效内容
                if (hasattr(response, 'result') and 
                    hasattr(response.result, 'candidates') and 
                    response.result.candidates):
                    
                    candidate = response.result.candidates[0]
                    
                    # 检查是否有内容字段
                    if not hasattr(candidate, 'content'):
                        logger.warning("Gemini API 返回速率限制响应，等待30秒后重试...")
                        time.sleep(30)  # 等待3秒后重试
                        continue
                return response
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str:
                    logger.warning("Gemini API 触发限流，等待65秒后重试...")
                    time.sleep(65)  # 等待65秒后重试
                    continue
                else:
                    logger.error(f"Gemini 生成文案错误: \n{error_str}")
                    raise

    def _process_response(self, response: any) -> str:
        """处理Gemini的响应"""
        if not response or not response.text:
            raise ValueError("Invalid response from Gemini API")
        return response.text.strip()


class QwenGenerator(BaseGenerator):
    """阿里云千问 API 生成器实现"""
    def __init__(self, model_name: str, api_key: str, prompt: str, base_url: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        # Qwen特定参数
        self.default_params = {
            **self.default_params,
            "stream": False,
            "user": "script_generator"
        }

    def _generate(self, messages: list, params: dict) -> any:
        """实现千问特定的生成逻辑"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                **params
            )
            return response
        except Exception as e:
            logger.error(f"Qwen generation error: {str(e)}")
            raise

    def _process_response(self, response: any) -> str:
        """处理千问的响应"""
        if not response or not response.choices:
            raise ValueError("Invalid response from Qwen API")
        return response.choices[0].message.content.strip()


class MoonshotGenerator(BaseGenerator):
    """Moonshot API 生成器实现"""
    def __init__(self, model_name: str, api_key: str, prompt: str, base_url: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.moonshot.cn/v1"
        )
        
        # Moonshot特定参数
        self.default_params = {
            **self.default_params,
            "stream": False,
            "stop": None,
            "user": "script_generator",
            "tools": None
        }

    def _generate(self, messages: list, params: dict) -> any:
        """实现Moonshot特定的生成逻辑，包含429误重试机制"""
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    **params
                )
                return response
            except Exception as e:
                error_str = str(e)
                if "Error code: 429" in error_str:
                    logger.warning("Moonshot API 触发限流，等待65秒后重试...")
                    time.sleep(65)  # 等待65秒后重试
                    continue
                else:
                    logger.error(f"Moonshot generation error: {error_str}")
                    raise

    def _process_response(self, response: any) -> str:
        """处理Moonshot的响应"""
        if not response or not response.choices:
            raise ValueError("Invalid response from Moonshot API")
        return response.choices[0].message.content.strip()


class DeepSeekGenerator(BaseGenerator):
    """DeepSeek API 生成器实现"""
    def __init__(self, model_name: str, api_key: str, prompt: str, base_url: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com"
        )
        
        # DeepSeek特定参数
        self.default_params = {
            **self.default_params,
            "stream": False,
            "user": "script_generator"
        }

    def _generate(self, messages: list, params: dict) -> any:
        """实现DeepSeek特定的生成逻辑"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,  # deepseek-chat 或 deepseek-coder
                messages=messages,
                **params
            )
            return response
        except Exception as e:
            logger.error(f"DeepSeek generation error: {str(e)}")
            raise

    def _process_response(self, response: any) -> str:
        """处理DeepSeek的响应"""
        if not response or not response.choices:
            raise ValueError("Invalid response from DeepSeek API")
        return response.choices[0].message.content.strip()


class ScriptProcessor:
    def __init__(self, model_name: str, api_key: str = None, base_url: str = None, prompt: str = None, video_theme: str = ""):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.video_theme = video_theme
        self.prompt = prompt or self._get_default_prompt()

        # 根据模型名称选择对应的生成器
        logger.info(f"文本 LLM 提供商: {model_name}")
        if 'gemini' in model_name.lower():
            self.generator = GeminiGenerator(model_name, self.api_key, self.prompt)
        elif 'qwen' in model_name.lower():
            self.generator = QwenGenerator(model_name, self.api_key, self.prompt, self.base_url)
        elif 'moonshot' in model_name.lower():
            self.generator = MoonshotGenerator(model_name, self.api_key, self.prompt, self.base_url)
        elif 'deepseek' in model_name.lower():
            self.generator = DeepSeekGenerator(model_name, self.api_key, self.prompt, self.base_url)
        else:
            self.generator = OpenAIGenerator(model_name, self.api_key, self.prompt, self.base_url)

    def _get_default_prompt(self) -> str:
        return f"""
        你是一位极具幽默感的短视频脚本创作大师，擅长用"温和的违反"制造笑点，让主题为 《{self.video_theme}》 的视频既有趣又富有传播力。
你的任务是将视频画面描述转化为能在社交平台疯狂传播的爆款口播文案。

目标受众：热爱生活、追求独特体验的18-35岁年轻人
文案风格：基于HKRR理论 + 段子手精神
主题：{self.video_theme}

【创作核心理念】
1. 敢于用"温和的违反"制造笑点，但不能过于冒犯
2. 巧妙运用中国式幽默，让观众会心一笑
3. 保持轻松愉快的叙事基调

【爆款内容四要素】

【快乐元素 Happy】
1. 用调侃的语气描述画面
2. 巧妙植入网络流行梗，增加内容的传播性
3. 适时自嘲，展现真实且有趣的一面

【知识价值 Knowledge】
1. 用段子手的方式解释专业知识
2. 在幽默中传递实用的生活常识

【情感共鸣 Resonance】
1. 描述"真实但夸张"的环境描述
2. 把对自然的感悟融入俏皮话中
3. 用接地气的表达方式拉近与观众距离

【节奏控制 Rhythm】
1. 像讲段子一样，注意铺垫和包袱的节奏
2. 确保每段都有笑点，但不强求
3. 段落结尾干净利落，不拖泥带水

【连贯性要求】
1. 新生成的内容必须自然衔接上一段文案的结尾
2. 使用恰当的连接词和过渡语，确保叙事流畅
3. 保持人物视角和语气的一致性
4. 避免重复上一段已经提到的信息
5. 确保情节的逻辑连续性

我会按顺序提供多段视频画面描述。请创作既搞笑又能火爆全网的口播文案。
记住：要敢于用"温和的违反"制造笑点，但要把握好尺度，让观众在轻松愉快中感受到乐趣。"""

    def calculate_duration_and_word_count(self, time_range: str) -> int:
        """
        计算时间范围的持续时长并估算合适的字数
        
        Args:
            time_range: 时间范围字符串,格式为 "HH:MM:SS,mmm-HH:MM:SS,mmm"
                       例如: "00:00:50,100-00:01:21,500"
        
        Returns:
            int: 估算的合适字数
                  基于经验公式: 每0.35秒可以说一个字
                  例如: 10秒可以说约28个字 (10/0.35≈28.57)
        """
        try:
            start_str, end_str = time_range.split('-')
            
            def time_to_seconds(time_str: str) -> float:
                """
                将时间字符串转换为秒数(带毫秒精度)
                
                Args:
                    time_str: 时间字符串,格式为 "HH:MM:SS,mmm"
                             例如: "00:00:50,100" 表示50.1秒
                
                Returns:
                    float: 转换后的秒数(带毫秒)
                """
                try:
                    # 处理毫秒部分
                    time_part, ms_part = time_str.split(',')
                    hours, minutes, seconds = map(int, time_part.split(':'))
                    milliseconds = int(ms_part)
                    
                    # 转换为秒
                    total_seconds = (hours * 3600) + (minutes * 60) + seconds + (milliseconds / 1000)
                    return total_seconds
                    
                except ValueError as e:
                    logger.warning(f"时间格式解析错误: {time_str}, error: {e}")
                    return 0.0
            
            # 计算开始和结束时间的秒数
            start_seconds = time_to_seconds(start_str)
            end_seconds = time_to_seconds(end_str)
            
            # 计算持续时间(秒)
            duration = end_seconds - start_seconds
            
            # 根据经验公式计算字数: 每0.5秒一个字
            word_count = int(duration / 0.4)
            
            # 确保字数在合理范围内
            word_count = max(10, min(word_count, 500))  # 限制在10-500字之间
            
            logger.debug(f"时间范围 {time_range} 的持续时间为 {duration:.3f}秒, 估算字数: {word_count}")
            return word_count
            
        except Exception as e:
            logger.warning(f"字数计算错误: {traceback.format_exc()}")
            return 100  # 发生错误时返回默认字数

    def process_frames(self, frame_content_list: List[Dict]) -> List[Dict]:
        for frame_content in frame_content_list:
            word_count = self.calculate_duration_and_word_count(frame_content["timestamp"])
            script = self.generator.generate_script(frame_content["picture"], word_count)
            frame_content["narration"] = script
            frame_content["OST"] = 2
            logger.info(f"时间范围: {frame_content['timestamp']}, 建议字数: {word_count}")
            logger.info(script)

        self._save_results(frame_content_list)
        return frame_content_list

    def _save_results(self, frame_content_list: List[Dict]):
        """保存处理结果，并添加新的时间戳"""
        try:
            def format_timestamp(seconds: float) -> str:
                """将秒数转换为 HH:MM:SS,mmm 格式"""
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                seconds_remainder = seconds % 60
                whole_seconds = int(seconds_remainder)
                milliseconds = int((seconds_remainder - whole_seconds) * 1000)
                
                return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"

            # 计算新的时间戳
            current_time = 0.0  # 当前时间点（秒，包含毫秒）

            for frame in frame_content_list:
                # 获取原始时间戳的持续时间
                start_str, end_str = frame['timestamp'].split('-')

                def time_to_seconds(time_str: str) -> float:
                    """将时间字符串转换为秒数（包含毫秒）"""
                    try:
                        if ',' in time_str:
                            time_part, ms_part = time_str.split(',')
                            ms = float(ms_part) / 1000
                        else:
                            time_part = time_str
                            ms = 0

                        parts = time_part.split(':')
                        if len(parts) == 3:  # HH:MM:SS
                            h, m, s = map(float, parts)
                            seconds = h * 3600 + m * 60 + s
                        elif len(parts) == 2:  # MM:SS
                            m, s = map(float, parts)
                            seconds = m * 60 + s
                        else:  # SS
                            seconds = float(parts[0])

                        return seconds + ms
                    except Exception as e:
                        logger.error(f"时间格式转换错误 {time_str}: {str(e)}")
                        return 0.0

                # 计算当前片段的持续时间
                start_seconds = time_to_seconds(start_str)
                end_seconds = time_to_seconds(end_str)
                duration = end_seconds - start_seconds

                # 设置新的时间戳
                new_start = format_timestamp(current_time)
                new_end = format_timestamp(current_time + duration)
                frame['new_timestamp'] = f"{new_start}-{new_end}"

                # 更新当前时间点
                current_time += duration

            # 保存结果
            file_name = f"storage/json/step2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            os.makedirs(os.path.dirname(file_name), exist_ok=True)

            with open(file_name, 'w', encoding='utf-8') as file:
                json.dump(frame_content_list, file, ensure_ascii=False, indent=4)

            logger.info(f"保存脚本成功，总时长: {format_timestamp(current_time)}")

        except Exception as e:
            logger.error(f"保存结果时发生错误: {str(e)}\n{traceback.format_exc()}")
            raise

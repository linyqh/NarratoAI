import os
import json
import traceback
from loguru import logger
import tiktoken
from typing import List, Dict
from datetime import datetime
from openai import OpenAI
import google.generativeai as genai


class BaseGenerator:
    def __init__(self, model_name: str, api_key: str, prompt: str):
        self.model_name = model_name
        self.api_key = api_key
        self.base_prompt = prompt
        self.conversation_history = []
        self.chunk_overlap = 50
        self.last_chunk_ending = ""

    def generate_script(self, scene_description: str, word_count: int) -> str:
        raise NotImplementedError("Subclasses must implement generate_script method")


class OpenAIGenerator(BaseGenerator):
    def __init__(self, model_name: str, api_key: str, prompt: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(api_key=api_key)
        self.max_tokens = 7000
        try:
            self.encoding = tiktoken.encoding_for_model(self.model_name)
        except KeyError:
            logger.info(f"警告：未找到模型 {self.model_name} 的专用编码器，使用认编码器")
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, messages: list) -> int:
        num_tokens = 0
        for message in messages:
            num_tokens += 3
            for key, value in message.items():
                num_tokens += len(self.encoding.encode(str(value)))
                if key == "role":
                    num_tokens += 1
        num_tokens += 3
        return num_tokens

    def _trim_conversation_history(self, system_prompt: str, new_user_prompt: str) -> None:
        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": new_user_prompt}
        ]
        base_tokens = self._count_tokens(base_messages)

        temp_history = []
        current_tokens = base_tokens

        for message in reversed(self.conversation_history):
            message_tokens = self._count_tokens([message])
            if current_tokens + message_tokens > self.max_tokens:
                break
            temp_history.insert(0, message)
            current_tokens += message_tokens

        self.conversation_history = temp_history

    def generate_script(self, scene_description: str, word_count: int) -> str:
        max_attempts = 3
        tolerance = 5

        for attempt in range(max_attempts):
            system_prompt, user_prompt = self._create_prompt(scene_description, word_count)
            self._trim_conversation_history(system_prompt, user_prompt)

            messages = [
                {"role": "system", "content": system_prompt},
                *self.conversation_history,
                {"role": "user", "content": user_prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
                top_p=0.9,
                frequency_penalty=0.3,
                presence_penalty=0.5
            )

            generated_script = response.choices[0].message.content.strip().strip('"').strip("'").replace('\"',
                                                                                                         '').replace(
                '\n', '')

            current_length = len(generated_script)
            if abs(current_length - word_count) <= tolerance:
                self.conversation_history.append({"role": "user", "content": user_prompt})
                self.conversation_history.append({"role": "assistant", "content": generated_script})
                self.last_chunk_ending = generated_script[-self.chunk_overlap:] if len(
                    generated_script) > self.chunk_overlap else generated_script
                return generated_script

        return generated_script

    def _create_prompt(self, scene_description: str, word_count: int) -> tuple:
        system_prompt = self.base_prompt.format(word_count=word_count)

        user_prompt = f"""上一段文案的结尾：{self.last_chunk_ending if self.last_chunk_ending else "这是第一段，无需考虑上文"}

当前画面描述：{scene_description}

请确保新生成的文案与上文自然衔接，保持叙事的连贯性和趣味性。
严格字数要求：{word_count}字，允许误差±5字。"""

        return system_prompt, user_prompt


class GeminiGenerator(BaseGenerator):
    def __init__(self, model_name: str, api_key: str, prompt: str):
        super().__init__(model_name, api_key, prompt)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def generate_script(self, scene_description: str, word_count: int) -> str:
        max_attempts = 3
        tolerance = 5

        for attempt in range(max_attempts):
            prompt = f"""{self.base_prompt}

上一段文案的结尾：{self.last_chunk_ending if self.last_chunk_ending else "这是第一段，无需考虑上文"}

当前画面描述：{scene_description}

请确保新生成的文案与上文自然衔接，保持叙事的连贯性和趣味性。
严格字数要求：{word_count}字，允许误差±5字。"""

            response = self.model.generate_content(prompt)
            generated_script = response.text.strip().strip('"').strip("'").replace('\"', '').replace('\n', '')

            current_length = len(generated_script)
            if abs(current_length - word_count) <= tolerance:
                self.last_chunk_ending = generated_script[-self.chunk_overlap:] if len(
                    generated_script) > self.chunk_overlap else generated_script
                return generated_script

        return generated_script


class QwenGenerator(BaseGenerator):
    def __init__(self, model_name: str, api_key: str, prompt: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

    def generate_script(self, scene_description: str, word_count: int) -> str:
        max_attempts = 3
        tolerance = 5

        for attempt in range(max_attempts):
            prompt = f"""{self.base_prompt}

上一段文案的结尾：{self.last_chunk_ending if self.last_chunk_ending else "这是第一段，无需考虑上文"}

当前画面描述：{scene_description}

请确保新生成的文案与上文自然衔接，保持叙事的连贯性和趣味性。
严格字数要求：{word_count}字，允许误差±5字。"""

            messages = [
                {"role": "system", "content": self.base_prompt},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model_name,  # 如 "qwen-plus"
                messages=messages,
                temperature=0.7,
                max_tokens=500,
                top_p=0.9,
                frequency_penalty=0.3,
                presence_penalty=0.5
            )

            generated_script = response.choices[0].message.content.strip().strip('"').strip("'").replace('\"',
                                                                                                         '').replace(
                '\n', '')

            current_length = len(generated_script)
            if abs(current_length - word_count) <= tolerance:
                self.last_chunk_ending = generated_script[-self.chunk_overlap:] if len(
                    generated_script) > self.chunk_overlap else generated_script
                return generated_script

        return generated_script


class MoonshotGenerator(BaseGenerator):
    def __init__(self, model_name: str, api_key: str, prompt: str):
        super().__init__(model_name, api_key, prompt)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )

    def generate_script(self, scene_description: str, word_count: int) -> str:
        max_attempts = 3
        tolerance = 5

        for attempt in range(max_attempts):
            prompt = f"""{self.base_prompt}

上一段文案的结尾：{self.last_chunk_ending if self.last_chunk_ending else "这是第一段，无需考虑上文"}

当前画面描述：{scene_description}

请确保新生成的文案与上文自然衔接，保持叙事的连贯性和趣味性。
严格字数要求：{word_count}字，允许误差±5字。"""

            messages = [
                {"role": "system", "content": self.base_prompt},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model_name,  # 如 "moonshot-v1-8k"
                messages=messages,
                temperature=0.7,
                max_tokens=500,
                top_p=0.9,
                frequency_penalty=0.3,
                presence_penalty=0.5
            )

            generated_script = response.choices[0].message.content.strip().strip('"').strip("'").replace('\"',
                                                                                                         '').replace(
                '\n', '')

            current_length = len(generated_script)
            if abs(current_length - word_count) <= tolerance:
                self.last_chunk_ending = generated_script[-self.chunk_overlap:] if len(
                    generated_script) > self.chunk_overlap else generated_script
                return generated_script

        return generated_script


class ScriptProcessor:
    def __init__(self, model_name: str, api_key: str = None, prompt: str = None, video_theme: str = ""):
        self.model_name = model_name
        self.api_key = api_key
        self.video_theme = video_theme
        self.prompt = prompt or self._get_default_prompt()

        # 根据模型名称选择对应的生成器
        if 'gemini' in model_name.lower():
            self.generator = GeminiGenerator(model_name, self.api_key, self.prompt)
        elif 'qwen' in model_name.lower():
            self.generator = QwenGenerator(model_name, self.api_key, self.prompt)
        elif 'moonshot' in model_name.lower():
            self.generator = MoonshotGenerator(model_name, self.api_key, self.prompt)
        else:
            self.generator = OpenAIGenerator(model_name, self.api_key, self.prompt)

    def _get_default_prompt(self) -> str:
        return f"""你是一位极具幽默感的短视频脚本创作大师，擅长用"温和的违反"制造笑点，让{self.video_theme}视频既有趣又富有传播力。你的任务是将视频画面描述转化为能在社交平台疯狂传播的爆款口播文案。

目标受众：热爱生活、追求独特体验的18-35岁年轻人
文案风格：基于HKRR理论 + 段子手精神
主题：{self.video_theme}

【创作核心理念】
1. 敢于用"温和的违反"制造笑点，但不能过于冒犯
2. 巧妙运用中国式幽默，让观众会心一笑
3. 保持轻松愉快的叙事基调

【爆款内容四要素】

【快乐元素 Happy】
1. 用调侃的语气描述建造过程中的"笨手笨脚"
2. 巧妙植入网络流行梗，增加内容的传播性
3. 适时自嘲，展现真实且有趣的一面

【知识价值 Knowledge】
1. 用段子手的方式解释专业知识（比如："这根木头不是一般的木头，它比我前任还难搞..."）
2. 把复杂的建造技巧转化为生动有趣的比喻
3. 在幽默中传递实用的野外生存技能

【情感共鸣 Resonance】
1. 描述"真实但夸张"的建造困境
2. 把对自然的感悟融入俏皮话中
3. 用接地气的表达方式拉近与观众距离

【节奏控制 Rhythm】
1. 严格控制文案字数在{self.word_count}字左右，允许误差不超过5字
2. 像讲段子一样，注意铺垫和包袱的节奏
3. 确保每段都有笑点，但不强求
4. 段落结尾干净利落，不拖泥带水

【连贯性要求】
1. 新生成的内容必须自然衔接上一段文案的结尾
2. 使用恰当的连接词和过渡语，确保叙事流畅
3. 保持人物视角和语气的一致性
4. 避免重复上一段已经提到的信息
5. 确保情节和建造过程的逻辑连续性

【字数控制要求】
1. 严格控制文案字数在{self.word_count}字左右，允许误差不超过5字
2. 如果内容过长，优先精简修饰性词语
3. 如果内容过短，可以适当增加细节描写
4. 保持文案结构完整，不因字数限制而牺牲内容质量
5. 确保每个笑点和包袱都得到完整表达

我会按顺序提供多段视频画面描述。请创作既搞笑又能火爆全网的口播文案。
记住：要敢于用"温和的违反"制造笑点，但要把握好尺度，让观众在轻松愉快中感受野外建造的乐趣。"""

    def calculate_duration_and_word_count(self, time_range: str) -> int:
        try:
            start_str, end_str = time_range.split('-')

            def time_to_seconds(time_str):
                minutes, seconds = map(int, time_str.split(':'))
                return minutes * 60 + seconds

            start_seconds = time_to_seconds(start_str)
            end_seconds = time_to_seconds(end_str)
            duration = end_seconds - start_seconds
            word_count = int(duration / 0.2)

            return word_count
        except Exception as e:
            logger.info(f"时间格式转换错误: {traceback.format_exc()}")
            return 100

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
            # 计算新的时间戳
            current_time = 0  # 当前时间点（秒）

            for frame in frame_content_list:
                # 获取原始时间戳的持续时间
                start_str, end_str = frame['timestamp'].split('-')

                def time_to_seconds(time_str):
                    minutes, seconds = map(int, time_str.split(':'))
                    return minutes * 60 + seconds

                # 计算当前片段的持续时间
                start_seconds = time_to_seconds(start_str)
                end_seconds = time_to_seconds(end_str)
                duration = end_seconds - start_seconds

                # 转换秒数为 MM:SS 格式
                def seconds_to_time(seconds):
                    minutes = seconds // 60
                    remaining_seconds = seconds % 60
                    return f"{minutes:02d}:{remaining_seconds:02d}"

                # 设置新的时间戳
                new_start = seconds_to_time(current_time)
                new_end = seconds_to_time(current_time + duration)
                frame['new_timestamp'] = f"{new_start}-{new_end}"

                # 更新当前时间点
                current_time += duration

            # 保存结果
            file_name = f"storage/json/step2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            os.makedirs(os.path.dirname(file_name), exist_ok=True)

            with open(file_name, 'w', encoding='utf-8') as file:
                json.dump(frame_content_list, file, ensure_ascii=False, indent=4)

            logger.info(f"保存脚本成功，总时长: {seconds_to_time(current_time)}")

        except Exception as e:
            logger.error(f"保存结果时发生错误: {str(e)}\n{traceback.format_exc()}")
            raise

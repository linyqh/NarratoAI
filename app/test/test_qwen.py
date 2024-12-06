import os
import traceback
import json
from openai import OpenAI
from pydantic import BaseModel
from typing import List
from app.utils import utils
from app.services.subtitle import extract_audio_and_create_subtitle


class Step(BaseModel):
    timestamp: str
    picture: str
    narration: str
    OST: int
    new_timestamp: str

class MathReasoning(BaseModel):
    result: List[Step]


def chat_with_qwen(prompt: str, system_message: str, subtitle_path: str) -> str:
    """
    与通义千问AI模型进行对话
    
    Args:
        prompt (str): 用户输入的问题或提示
        system_message (str): 系统提示信息，用于设定AI助手的行为。默认为"You are a helpful assistant."
        subtitle_path (str): 字幕文件路径
    Returns:
        str: AI助手的回复内容

    Raises:
        Exception: 当API调用失败时抛出异常
    """
    try:
        client = OpenAI(
            api_key="sk-a1acd853d88d41d3ae92777d7bfa2612",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        # 读取字幕文件
        with open(subtitle_path, "r", encoding="utf-8") as file:
            subtitle_content = file.read()

        completion = client.chat.completions.create(
            model="qwen-turbo-2024-11-01",
            messages=[
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': prompt + subtitle_content}
            ]
        )
        return completion.choices[0].message.content

    except Exception as e:
        error_message = f"调用千问API时发生错误：{str(e)}"
        print(error_message)
        print("请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code")
        raise Exception(error_message)


# 使用示例
if __name__ == "__main__":
    try:
        video_path = utils.video_dir("duanju_yuansp.mp4")
        # # 判断视频是否存在
        # if not os.path.exists(video_path):
        #     print(f"视频文件不存在：{video_path}")
        #     exit(1)
        # 提取字幕
        subtitle_path = os.path.join(utils.video_dir(""), f"duanju_yuan.srt")
        extract_audio_and_create_subtitle(video_file=video_path, subtitle_file=subtitle_path)
        # 分析字幕
        system_message = """
        你是一个视频srt字幕分析剪辑器, 输入视频的srt字幕, 分析其中的精彩且尽可能连续的片段并裁剪出来, 注意确保文字与时间戳的正确匹配。
        输出需严格按照如下 json 格式:
        [
            {
                "timestamp": "00:00:50,020-00,01:44,000",
                "picture": "画面1",
                "narration": "播放原声",
                "OST": 0,
                "new_timestamp": "00:00:00,000-00:00:54,020"
            },
            {
                "timestamp": "01:49-02:30",
                "picture": "画面2",
                "narration": "播放原声",
                "OST": 2,
                "new_timestamp": "00:54-01:35"
            },
        ]
        """
        prompt = "字幕如下：\n"
        response = chat_with_qwen(prompt, system_message, subtitle_path)
        print(response)
        # 保存json，注意json中是时间戳需要转换为 分:秒(现在的时间是 "timestamp": "00:00:00,020-00:00:01,660", 需要转换为 "timestamp": "00:00-01:66")
        # response = json.loads(response)
        # for item in response:
        #     item["timestamp"] = item["timestamp"].replace(":", "-")
        # with open(os.path.join(utils.video_dir(""), "duanju_yuan.json"), "w", encoding="utf-8") as file:
        #     json.dump(response, file, ensure_ascii=False)

    except Exception as e:
        print(traceback.format_exc())

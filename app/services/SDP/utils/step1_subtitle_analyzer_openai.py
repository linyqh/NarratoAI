"""
使用OpenAI API，分析字幕文件，返回剧情梗概和爆点
"""
import traceback
from openai import OpenAI, BadRequestError
import os
import json

from .utils import load_srt
# 导入新的提示词管理系统
from app.services.prompts import PromptManager


def analyze_subtitle(
    srt_path: str,
    model_name: str,
    api_key: str = None,
    base_url: str = None,
    custom_clips: int = 5
) -> dict:
    """分析字幕内容，返回完整的分析结果

    Args:
        srt_path (str): SRT字幕文件路径
        api_key (str, optional): 大模型API密钥. Defaults to None.
        model_name (str, optional): 大模型名称. Defaults to "gpt-4o-2024-11-20".
        base_url (str, optional): 大模型API基础URL. Defaults to None.

    Returns:
        dict: 包含剧情梗概和结构化的时间段分析的字典
    """
    try:
        # 加载字幕文件
        subtitles = load_srt(srt_path)
        subtitle_content = "\n".join([f"{sub['timestamp']}\n{sub['text']}" for sub in subtitles])

        # 初始化客户端
        global client
        if "deepseek" in model_name.lower():
            client = OpenAI(
                api_key=api_key or os.getenv('DeepSeek_API_KEY'),
                base_url="https://api.siliconflow.cn/v1"    # 使用第三方 硅基流动 API
            )
        else:
            client = OpenAI(
                api_key=api_key or os.getenv('OPENAI_API_KEY'),
                base_url=base_url
            )

        # 使用新的提示词管理系统
        subtitle_analysis_prompt = PromptManager.get_prompt(
            category="short_drama_editing",
            name="subtitle_analysis",
            parameters={
                "subtitle_content": subtitle_content,
                "custom_clips": custom_clips
            }
        )

        messages = [
            {
                "role": "system",
                "content": "你是一名短剧编剧和内容分析师，擅长从字幕中提取剧情要点和关键情节。"
            },
            {
                "role": "user",
                "content": subtitle_analysis_prompt
            }
        ]
        # DeepSeek R1 和 V3 不支持 response_format=json_object
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"}
            )
            summary_data = json.loads(completion.choices[0].message.content)
        except BadRequestError as e:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages
            )
            # 去除 completion 字符串前的 ```json 和 结尾的 ```
            completion = completion.choices[0].message.content.replace("```json", "").replace("```", "")
            summary_data = json.loads(completion)
        except Exception as e:
            raise Exception(f"大模型解析发生错误：{str(e)}\n{traceback.format_exc()}")

        print(json.dumps(summary_data, indent=4, ensure_ascii=False))

        # 构建爆点标题列表
        plot_titles_text = ""
        print(f"找到 {len(summary_data['plot_titles'])} 个片段")
        for i, point in enumerate(summary_data['plot_titles'], 1):
            plot_titles_text += f"{i}. {point}\n"

        # 使用新的提示词管理系统
        plot_extraction_prompt = PromptManager.get_prompt(
            category="short_drama_editing",
            name="plot_extraction",
            parameters={
                "subtitle_content": subtitle_content,
                "plot_summary": summary_data['summary'],
                "plot_titles": plot_titles_text
            }
        )

        messages = [
            {
                "role": "system",
                "content": "你是一名短剧编剧，非常擅长根据字幕中分析视频中关键剧情出现的具体时间段。"
            },
            {
                "role": "user",
                "content": plot_extraction_prompt
            }
        ]
        # DeepSeek R1 和 V3 不支持 response_format=json_object
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"}
            )
            plot_points_data = json.loads(completion.choices[0].message.content)
        except BadRequestError as e:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages
            )
            # 去除 completion 字符串前的 ```json 和 结尾的 ```
            completion = completion.choices[0].message.content.replace("```json", "").replace("```", "")
            plot_points_data = json.loads(completion)
        except Exception as e:
            raise Exception(f"大模型解析错误：{str(e)}\n{traceback.format_exc()}")

        print(json.dumps(plot_points_data, indent=4, ensure_ascii=False))

        # 合并结果
        return {
            "plot_summary": summary_data,
            "plot_points": plot_points_data["plot_points"]
        }

    except Exception as e:
        raise Exception(f"分析字幕时发生错误：{str(e)}\n{traceback.format_exc()}")

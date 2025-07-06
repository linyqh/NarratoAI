"""
使用OpenAI API，分析字幕文件，返回剧情梗概和爆点
"""
import traceback
from openai import OpenAI, BadRequestError
import os
import json

from .utils import load_srt


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

        messages = [
            {
                "role": "system",
                "content": """你是一名经验丰富的短剧编剧，擅长根据字幕内容按照先后顺序分析关键剧情,并找出 %s 个关键片段。
                请返回一个JSON对象，包含以下字段：
                {
                    "summary": "整体剧情梗概",
                    "plot_titles": [
                        "关键剧情1",
                        "关键剧情2",
                        "关键剧情3",
                        "关键剧情4",
                        "关键剧情5",
                        "..."
                    ]
                }
                请确保返回的是合法的JSON格式, 请确保返回的是 %s 个片段。
                """ % (custom_clips, custom_clips)
            },
            {
                "role": "user",
                "content": f"srt字幕如下：{subtitle_content}"
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

        # 获取爆点时间段分析
        prompt = f"""剧情梗概：
            {summary_data['summary']}

            需要定位的爆点内容：
            """
        print(f"找到 {len(summary_data['plot_titles'])} 个片段")
        for i, point in enumerate(summary_data['plot_titles'], 1):
            prompt += f"{i}. {point}\n"

        messages = [
            {
                "role": "system",
                "content": """你是一名短剧编剧，非常擅长根据字幕中分析视频中关键剧情出现的具体时间段。
                请仔细阅读剧情梗概和爆点内容，然后在字幕中找出每个爆点发生的具体时间段和爆点前后的详细剧情。
                
                请返回一个JSON对象，包含一个名为"plot_points"的数组，数组中包含多个对象，每个对象都要包含以下字段：
                {
                    "plot_points": [
                        {
                            "timestamp": "时间段，格式为xx:xx:xx,xxx-xx:xx:xx,xxx",
                            "title": "关键剧情的主题",
                            "picture": "关键剧情前后的详细剧情描述"
                        }
                    ]
                }
                请确保返回的是合法的JSON格式。"""
            },
            {
                "role": "user",
                "content": f"""字幕内容：
{subtitle_content}

{prompt}"""
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

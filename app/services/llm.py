import logging
import re
import json
import traceback
from typing import List
from loguru import logger
from openai import OpenAI
from openai import AzureOpenAI
from openai.types.chat import ChatCompletion
import google.generativeai as gemini

from app.config import config

_max_retries = 5


def _generate_response(prompt: str) -> str:
    content = ""
    llm_provider = config.app.get("llm_provider", "openai")
    logger.info(f"llm provider: {llm_provider}")
    if llm_provider == "g4f":
        model_name = config.app.get("g4f_model_name", "")
        if not model_name:
            model_name = "gpt-3.5-turbo-16k-0613"
        import g4f

        content = g4f.ChatCompletion.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )
    else:
        api_version = ""  # for azure
        if llm_provider == "moonshot":
            api_key = config.app.get("moonshot_api_key")
            model_name = config.app.get("moonshot_model_name")
            base_url = "https://api.moonshot.cn/v1"
        elif llm_provider == "ollama":
            # api_key = config.app.get("openai_api_key")
            api_key = "ollama"  # any string works but you are required to have one
            model_name = config.app.get("ollama_model_name")
            base_url = config.app.get("ollama_base_url", "")
            if not base_url:
                base_url = "http://localhost:11434/v1"
        elif llm_provider == "openai":
            api_key = config.app.get("openai_api_key")
            model_name = config.app.get("openai_model_name")
            base_url = config.app.get("openai_base_url", "")
            if not base_url:
                base_url = "https://api.openai.com/v1"
        elif llm_provider == "oneapi":
            api_key = config.app.get("oneapi_api_key")
            model_name = config.app.get("oneapi_model_name")
            base_url = config.app.get("oneapi_base_url", "")
        elif llm_provider == "azure":
            api_key = config.app.get("azure_api_key")
            model_name = config.app.get("azure_model_name")
            base_url = config.app.get("azure_base_url", "")
            api_version = config.app.get("azure_api_version", "2024-02-15-preview")
        elif llm_provider == "gemini":
            api_key = config.app.get("gemini_api_key")
            model_name = config.app.get("gemini_model_name")
            base_url = "***"
        elif llm_provider == "qwen":
            api_key = config.app.get("qwen_api_key")
            model_name = config.app.get("qwen_model_name")
            base_url = "***"
        elif llm_provider == "cloudflare":
            api_key = config.app.get("cloudflare_api_key")
            model_name = config.app.get("cloudflare_model_name")
            account_id = config.app.get("cloudflare_account_id")
            base_url = "***"
        elif llm_provider == "deepseek":
            api_key = config.app.get("deepseek_api_key")
            model_name = config.app.get("deepseek_model_name")
            base_url = config.app.get("deepseek_base_url")
            if not base_url:
                base_url = "https://api.deepseek.com"
        elif llm_provider == "ernie":
            api_key = config.app.get("ernie_api_key")
            secret_key = config.app.get("ernie_secret_key")
            base_url = config.app.get("ernie_base_url")
            model_name = "***"
            if not secret_key:
                raise ValueError(
                    f"{llm_provider}: secret_key is not set, please set it in the config.toml file."
                )
        else:
            raise ValueError(
                "llm_provider is not set, please set it in the config.toml file."
            )

        if not api_key:
            raise ValueError(
                f"{llm_provider}: api_key is not set, please set it in the config.toml file."
            )
        if not model_name:
            raise ValueError(
                f"{llm_provider}: model_name is not set, please set it in the config.toml file."
            )
        if not base_url:
            raise ValueError(
                f"{llm_provider}: base_url is not set, please set it in the config.toml file."
            )

        if llm_provider == "qwen":
            import dashscope
            from dashscope.api_entities.dashscope_response import GenerationResponse

            dashscope.api_key = api_key
            response = dashscope.Generation.call(
                model=model_name, messages=[{"role": "user", "content": prompt}]
            )
            if response:
                if isinstance(response, GenerationResponse):
                    status_code = response.status_code
                    if status_code != 200:
                        raise Exception(
                            f'[{llm_provider}] returned an error response: "{response}"'
                        )

                    content = response["output"]["text"]
                    return content.replace("\n", "")
                else:
                    raise Exception(
                        f'[{llm_provider}] returned an invalid response: "{response}"'
                    )
            else:
                raise Exception(f"[{llm_provider}] returned an empty response")

        if llm_provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=api_key, transport="rest")

            generation_config = {
                "temperature": 0.5,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 2048,
            }

            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
            ]

            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
                safety_settings=safety_settings,
            )

            try:
                response = model.generate_content(prompt)
                candidates = response.candidates
                generated_text = candidates[0].content.parts[0].text
            except (AttributeError, IndexError) as e:
                print("Gemini Error:", e)

            return generated_text

        if llm_provider == "cloudflare":
            import requests

            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "messages": [
                        {"role": "system", "content": "You are a friendly assistant"},
                        {"role": "user", "content": prompt},
                    ]
                },
            )
            result = response.json()
            logger.info(result)
            return result["result"]["response"]

        if llm_provider == "ernie":
            import requests

            params = {
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret_key,
            }
            access_token = (
                requests.post("https://aip.baidubce.com/oauth/2.0/token", params=params)
                .json()
                .get("access_token")
            )
            url = f"{base_url}?access_token={access_token}"

            payload = json.dumps(
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "top_p": 0.8,
                    "penalty_score": 1,
                    "disable_search": False,
                    "enable_citation": False,
                    "response_format": "text",
                }
            )
            headers = {"Content-Type": "application/json"}

            response = requests.request(
                "POST", url, headers=headers, data=payload
            ).json()
            return response.get("result")

        if llm_provider == "azure":
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=base_url,
            )
        else:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

        response = client.chat.completions.create(
            model=model_name, messages=[{"role": "user", "content": prompt}]
        )
        if response:
            if isinstance(response, ChatCompletion):
                content = response.choices[0].message.content
            else:
                raise Exception(
                    f'[{llm_provider}] returned an invalid response: "{response}", please check your network '
                    f"connection and try again."
                )
        else:
            raise Exception(
                f"[{llm_provider}] returned an empty response, please check your network connection and try again."
            )

    return content.replace("\n", "")


def generate_script(
    video_subject: str, language: str = "", paragraph_number: int = 1
) -> str:
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a script for a video, depending on the subject of the video.

## Constrains:
1. the script is to be returned as a string with the specified number of paragraphs.
2. do not under any circumstance reference this prompt in your response.
3. get straight to the point, don't start with unnecessary things like, "welcome to this video".
4. you must not include any type of markdown or formatting in the script, never use a title.
5. only return the raw content of the script.
6. do not include "voiceover", "narrator" or similar indicators of what should be spoken at the beginning of each paragraph or line.
7. you must not mention the prompt, or anything about the script itself. also, never talk about the amount of paragraphs or lines. just write the script.
8. respond in the same language as the video subject.

# Initialization:
- video subject: {video_subject}
- number of paragraphs: {paragraph_number}
""".strip()
    if language:
        prompt += f"\n- language: {language}"

    final_script = ""
    logger.info(f"subject: {video_subject}")

    def format_response(response):
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*\]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Select the specified number of paragraphs
        selected_paragraphs = paragraphs[:paragraph_number]

        # Join the selected paragraphs into a single string
        return "\n\n".join(paragraphs)

    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                final_script = format_response(response)
            else:
                logging.error("gpt returned an empty response")

            # g4f may return an error message
            if final_script and "当日额度已消耗完" in final_script:
                raise ValueError(final_script)

            if final_script:
                break
        except Exception as e:
            logger.error(f"failed to generate script: {e}")

        if i < _max_retries:
            logger.warning(f"failed to generate video script, trying again... {i + 1}")

    logger.success(f"completed: \n{final_script}")
    return final_script.strip()


def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
    prompt = f"""
# Role: Video Search Terms Generator

## Goals:
Generate {amount} search terms for stock videos, depending on the subject of a video.

## Constrains:
1. the search terms are to be returned as a json-array of strings.
2. each search term should consist of 1-3 words, always add the main subject of the video.
3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
4. the search terms must be related to the subject of the video.
5. reply with english search terms only.

## Output Example:
["search term 1", "search term 2", "search term 3","search term 4","search term 5"]

## Context:
### Video Subject
{video_subject}

### Video Script
{video_script}

Please note that you must use English for generating video search terms; Chinese is not accepted.
""".strip()

    logger.info(f"subject: {video_subject}")

    search_terms = []
    response = ""
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt)
            search_terms = json.loads(response)
            if not isinstance(search_terms, list) or not all(
                isinstance(term, str) for term in search_terms
            ):
                logger.error("response is not a list of strings.")
                continue

        except Exception as e:
            logger.warning(f"failed to generate video terms: {str(e)}")
            if response:
                match = re.search(r"\[.*]", response)
                if match:
                    try:
                        search_terms = json.loads(match.group())
                    except Exception as e:
                        logger.warning(f"failed to generate video terms: {str(e)}")
                        pass

        if search_terms and len(search_terms) > 0:
            break
        if i < _max_retries:
            logger.warning(f"failed to generate video terms, trying again... {i + 1}")

    logger.success(f"completed: \n{search_terms}")
    return search_terms


def gemini_video2json(video_origin_name: str, video_origin_path: str, video_plot: str, language: str) -> str:
    '''
    使用 gemini-1.5-pro 进行影视解析
    Args:
        video_origin_name: str - 影视作品的原始名称
        video_origin_path: str - 影视作品的原始路径
        video_plot: str - 影视作品的简介或剧情概述

    Return:
        str - 解析后的 JSON 格式字符串
    '''
    api_key = config.app.get("gemini_api_key")
    model_name = config.app.get("gemini_model_name")

    gemini.configure(api_key=api_key)
    model = gemini.GenerativeModel(model_name=model_name)

    prompt = """
**角色设定：**  
你是一位影视解说专家，擅长根据剧情生成引人入胜的短视频解说文案，特别熟悉适用于TikTok/抖音风格的快速、抓人视频解说。

**任务目标：**  
1. 根据给定剧情，详细描述画面，重点突出重要场景和情节。  
2. 生成符合TikTok/抖音风格的解说，节奏紧凑，语言简洁，吸引观众。  
3. 解说的时候需要解说一段播放一段原视频，原视频一般为有台词的片段，原视频的控制有 OST 字段控制。
4. 结果输出为JSON格式，包含字段：  
   - "picture"：画面描述  
   - "timestamp"：画面出现的时间范围  
   - "narration"：解说内容
   - "OST": 是否开启原声（true / false）

**输入示例：**  
```text  
在一个黑暗的小巷中，主角缓慢走进，四周静谧无声，只有远处隐隐传来猫的叫声。突然，背后出现一个神秘的身影。  
```  

**输出格式：**  
```json  
[  
    {  
        "picture": "黑暗的小巷，主角缓慢走入，四周安静，远处传来猫叫声。",  
        "timestamp": "00:00-00:17",  
        "narration": "静谧的小巷里，主角步步前行，气氛渐渐变得压抑。"  
        "OST": False  
    },  
    {  
        "picture": "神秘身影突然出现，紧张气氛加剧。",  
        "timestamp": "00:17-00:39",  
        "narration": "原声播放"  
        "OST": True  
    }  
]  
```  

**提示：**  
- 文案要简短有力，契合短视频平台用户的观赏习惯。  
- 保持强烈的悬念和情感代入，吸引观众继续观看。  
- 解说一段后播放一段原声，原声内容尽量和解说匹配。
- 文案语言为：%s  
- 剧情内容：%s (为空则忽略)  

""" % (language, video_plot)

    logger.debug(f"视频名称: {video_origin_name}")
    try:
        gemini_video_file = gemini.upload_file(video_origin_path)
        logger.debug(f"上传视频至 Google cloud 成功: {gemini_video_file.name}")
        while gemini_video_file.state.name == "PROCESSING":
            import time
            time.sleep(1)
            gemini_video_file = gemini.get_file(gemini_video_file.name)
            logger.debug(f"视频当前状态(ACTIVE才可用): {gemini_video_file.state.name}")
        if gemini_video_file.state.name == "FAILED":
            raise ValueError(gemini_video_file.state.name)
    except Exception as err:
        logger.error(f"上传视频至 Google cloud 失败, 请检查 VPN 配置和 APIKey 是否正确 \n{traceback.format_exc()}")
        raise TimeoutError(f"上传视频至 Google cloud 失败, 请检查 VPN 配置和 APIKey 是否正确; {err}")

    streams = model.generate_content([prompt, gemini_video_file], stream=True)
    response = []
    for chunk in streams:
        response.append(chunk.text)

    response = "".join(response)
    logger.success(f"llm response: \n{response}")

    return response


if __name__ == "__main__":
    """
    File API 可让您为每个项目存储最多 20 GB 的文件，每个项目使用 每个文件的大小上限为 2 GB。文件会存储 48 小时。
    它们可以是 在此期间使用您的 API 密钥访问，但无法下载 使用任何 API。它已在使用 Gemini 的所有地区免费提供 API 可用。
    """
    import os
    import sys
    import requests
    from app.utils.utils import get_current_country

    # # 添加当前目录到系统路径
    # sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    #
    video_subject = "卖菜大妈竟是皇嫂"
    video_path = "/NarratoAI/resource/videos/demoyasuo.mp4"

    video_plot = ''' '''
    language = "zh-CN"
    res = gemini_video2json(video_subject, video_path, video_plot, language)
    print(res)

    # get_current_country()
    # api_key = config.app.get("gemini_api_key")
    # model_name = config.app.get("gemini_model_name")
    # gemini.configure(api_key=api_key)
    # model = gemini.GenerativeModel(model_name=model_name)
    # # 卖菜大妈竟是皇嫂 测试视频
    # video_name = "files/y3npkshvldsd"
    # video_file = gemini.get_file(video_name)
    # logger.debug(f"视频当前状态(ACTIVE才可用): {video_file.state.name}")
    #
    # # 转录视频并提供视觉说明
    # prompt = "Transcribe the audio, giving timestamps. Also provide visual descriptions. use ZH-CN ONLY"
    # # Make the LLM request.
    # print("发出 LLM 推理请求...")
    # streams = model.generate_content([prompt, video_file],
    #                                   request_options={"timeout": 600},
    #                                   stream=True)
    # response = []
    # for chunk in streams:
    #     response.append(chunk.text)
    #
    # response = "".join(response)
    # logger.success(f"llm response: \n{response}")

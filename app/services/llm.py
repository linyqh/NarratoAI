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
# 角色设定：
你是一位影视解说专家，擅长根据剧情描述视频的画面和故事生成一段有趣且吸引人的解说文案。你特别熟悉 tiktok/抖音 风格的影视解说文案创作。

# 任务目标：
1.	根据给定的剧情描述，详细描述视频画面并展开叙述，尤其是对重要画面进行细致刻画。
2.	生成风格符合 tiktok/抖音 的影视解说文案，使其节奏快、内容抓人。
3.	最终结果以 JSON 格式输出，字段包含：
  • "picture"：画面描述
  • "timestamp"：时间戳（表示画面出现的时间-画面结束的时间）
  • "narration"：对应的解说文案

# 输入示例：
```text
在一个黑暗的小巷中，主角缓慢走进，四周静谧无声，只有远处隐隐传来猫的叫声。突然，背后出现一个神秘的身影。
```

# 输出格式：
```json
[
    {
        "picture": "黑暗的小巷中，主角缓慢走进，四周静谧无声，远处有模糊的猫叫声。",
        "timestamp": "00:00-00:17",
        "narration": "昏暗的小巷里，他独自前行，空气中透着一丝不安，隐约中能听到远处的猫叫声。 "
    },
    {
        "picture": "主角背后突然出现一个神秘的身影，气氛骤然紧张。",
        "timestamp": "00:17-00:39",
        "narration": "就在他以为安全时，一个身影悄无声息地出现在他身后，危险一步步逼近！ "
    }
    ...
]
```
# 提示：
  - 生成的解说文案应简洁有力，符合短视频平台用户的偏好。
  - 叙述中应有强烈的代入感和悬念，以吸引观众持续观看。
  - 文案语言为：%s
  - 剧情内容如下：%s (若为空则忽略)
  
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
    video_subject = "摔跤吧！爸爸 Dangal"
    video_path = "/NarratoAI/resource/videos/test.mp4"
    video_plot = '''
马哈维亚（阿米尔·汗 Aamir Khan 饰）曾经是一名前途无量的摔跤运动员，在放弃了职业生涯后，他最大的遗憾就是没有能够替国家赢得金牌。马哈维亚将这份希望寄托在了尚未出生的儿子身上，哪知道妻子接连给他生了两个女儿，取名吉塔（法缇玛·萨那·纱卡 Fatima Sana Shaikh 饰）和巴比塔（桑亚·玛荷塔 Sanya Malhotra 饰）。让马哈维亚没有想到的是，两个姑娘展现出了杰出的摔跤天赋，让他幡然醒悟，就算是女孩，也能够昂首挺胸的站在比赛场上，为了国家和她们自己赢得荣誉。
就这样，在马哈维亚的指导下，吉塔和巴比塔开始了艰苦的训练，两人进步神速，很快就因为在比赛中连连获胜而成为了当地的名人。为了获得更多的机会，吉塔进入了国家体育学院学习，在那里，她将面对更大的诱惑和更多的选择。
'''
    language = "zh-CN"
    res = gemini_video2json(video_subject, video_path, video_plot, language)
    print(res)

    # video_subject = "生命的意义是什么"
    # script = generate_script(
    #     video_subject=video_subject, language="zh-CN", paragraph_number=1
    # )
    # print("######################")
    # print(script)
    # search_terms = generate_terms(
    #     video_subject=video_subject, video_script=script, amount=5
    # )
    # print("######################")
    # print(search_terms)
    #     prompt = """
    # # Role: 影视解说专家
    #
    # ## Background:
    # 擅长根据剧情描述视频的画面和故事，能够生成一段非常有趣的解说文案。
    #
    # ## Goals:
    # 1. 根据剧情描述视频的画面和故事，并对重要的画面进行展开叙述
    # 2. 根据剧情内容，生成符合 tiktok/抖音 风格的影视解说文案
    # 3. 将结果直接以json格式输出给用户，需要包含字段： picture 画面描述， timestamp 时间戳， narration 解说文案
    # 4. 剧情内容如下：{%s}
    #
    # ## Skills
    # - 精通 tiktok/抖音 等短视频影视解说文案撰写
    # - 能够理解视频中的故事和画面表现
    # - 能精准匹配视频中的画面和时间戳
    # - 能精准把控旁白和时长
    # - 精通中文
    # - 精通JSON数据格式
    #
    # ## Constrains
    # - 解说文案的时长要和时间戳的时长尽量匹配
    # - 忽略视频中关于广告的内容
    # - 忽略视频中片头和片尾
    # - 不得在脚本中包含任何类型的 Markdown 或格式
    #
    # ## Format
    # - 对应JSON的key为：picture， timestamp， narration
    #
    # # Initialization:
    # - video subject: {video_subject}
    # - number of paragraphs: {paragraph_number}
    # """.strip()
    #     if language:
    #         prompt += f"\n- language: {language}"

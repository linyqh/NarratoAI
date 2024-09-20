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
from googleapiclient.errors import ResumableUploadError
from google.api_core.exceptions import FailedPrecondition
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.config import config

_max_retries = 5

Method = """
重要提示：每一部剧的文案，前几句必须吸引人
首先我们在看完看懂电影后，大脑里面要先有一个大概的轮廓，也就是一个类似于作文的大纲，电影主题线在哪里，首先要找到。
一般将文案分为开头、内容、结尾
## 开头部分
文案开头三句话，是留住用户的关键！

### 方式一：开头概括总结
文案的前三句，是整部电影的概括总结，2-3句介绍后，开始叙述故事剧情！
推荐新手（新号）做：（盘点型）
盘点全球最恐怖的10部电影
盘点全球最科幻的10部电影
盘点全球最悲惨的10部电影
盘点全球最值得看的10部灾难电影
盘点全球最值得看的10部励志电影

下面的示例就是最简单的解说文案开头：
1.这是XXX国20年来最大尺度的一部剧，极度烧脑，却让99%的人看得心潮澎湃、无法自拔，故事开始……
2.这是有史以来电影院唯一一部全程开灯放完的电影，期间无数人尖叫昏厥，他被成为勇敢者的专属，因为99%的人都不敢看到结局，许多人看完它从此不愿再碰手机，他就是大名鼎鼎的暗黑神作《XXX》……
3.这到底是一部什么样的电影，能被55个国家公开抵制，它甚至为了上映，不惜删减掉整整47分钟的剧情……
4.是什么样的一个人，被豆瓣网友称之为史上最牛P的老太太，都70岁了还要去贩毒……
5.他是M国历史上最NB/惨/猖狂/冤枉……的囚犯/抢劫犯/……
6.这到底是一部什么样的影片，他一个人就拿了4个顶级奖项，第一季8.7分，第二季直接干到9.5分，11万人给出5星好评，一共也就6集，却斩获26项国际大奖，看过的人都说，他是近年来最好的xxx剧，几乎成为了近年来xxx剧的标杆。故事发生在……
7.他是国产电影的巅峰佳作，更是许多80-90后的青春启蒙，曾入选《时代》周刊，获得年度佳片第一，可在国内却被尘封多年，至今为止都无法在各大视频网站看到完整资源，他就是《xxxxxx》
8.这是一部让所有人看得荷尔蒙飙升的爽片……
9.他被成为世界上最虐心绝望的电影，至今无人敢看第二遍，很难想象，他是根据真实事件改编而来……
10.这大概是有史以来最令人不寒而栗的电影，当年一经放映，就点燃了无数人的怒火，不少观众不等影片放完，就愤然离场，它比《xxx》更让人绝望，比比《xxx》更让人xxx，能坚持看完全片的人，更是万中无一，包括我。甚至观影结束后，有无数人抵制投诉这部电影，认为影片的导演玩弄了他们的情感！他就是顶级神作《xxxx》……
11.这是X国有史以来最高赞的一部悬疑电影，然而却因为某些原因，国内90%的人，没能看过这部片子，他就是《xxx》……
12.有这样一部电影，这辈子，你绝对不想再看第二遍，并不是它剧情烂俗，而是它的结局你根本承受不起/想象不到……甚至有80%的观众在观影途中情绪崩溃中途离场，更让许多同行都不想解说这部电影，他就是大名鼎鼎的暗黑神作《xxx》…
13.它被誉为史上最牛悬疑片，无数人在看完它时候，一个月不敢照镜子，这样一部仅适合部分年龄段观看的影片，究竟有什么样的魅力，竟然获得某瓣8.2的高分，很多人说这部电影到处都是看点，他就是《xxx》….
14.这是一部在某瓣上被70万人打出9.3分的高分的电影……到底是一部什么样的电影，能够在某瓣上被70万人打出9.3分的高分……
15.这是一部细思极恐的科幻大片，整部电影颠覆你的三观，它的名字叫……
16.史上最震撼的灾难片，每一点都不舍得快进的电影，他叫……
17.今天给大家带来一部基于真实事件改编的（主题介绍一句……）的故事片，这是一部连环悬疑剧，如果不看到最后绝对想不到结局竟然是这样的反转……

### 方式二：情景式、假设性开头
1.他叫……你以为他是……的吗？不。他是来……然后开始叙述
2.你知道……吗？原来……然后开始叙述
3.如果给你….，你会怎么样？
4.如果你是….，你会怎么样？

### 方式三：以国家为开头！简单明了。话语不需要多，但是需要讲解透彻！
1.这是一部韩国最新灾难片，你一定没有看过……
2.这是一部印度高分悬疑片，
3.这部电影原在日本因为……而被下架，
4.这是韩国最恐怖的犯罪片，
5.这是最近国产片评分最高的悬疑片
以上均按照影片国家来区分，然后简单介绍下主题。就可以开始直接叙述作品。也是一个很不错的方法！

### 方式四：如何自由发挥
正常情况下，每一部电影都有非常关键的一个大纲，这部电影的主题其实是可以用一句话、两句话概括的。只要看懂电影，就能找到这个主题大纲。
我们提前把这个主题大纲给放到影视最前面，作为我们的前三句的文案，将会非常吸引人！

例如：
1.这不是电影，这是真实故事。两个女人和一个男人被关在可桑拿室。喊破喉咙也没有一丝回音。窒息感和热度让人抓狂，故事就是从这里开始！ 
2.如果你男朋友出轨了，他不爱你了，还对你家暴，怎么办？接下来这部电影就会教你如何让老公服服帖帖的呆在你身边！女主是一个……开始叙述了。 
3.他力大无穷，双眼放光，这不是拯救地球的超人吗？然而不是。今天给大家推荐的这部电影叫……

以上是需要看完影片，看懂影片，然后从里面提炼出精彩的几句话,当然是比较难的，当你不会自己去总结前三句的经典的话。可以用前面方式一二三！
实在想不出来如何去提炼，可以去搜索这部剧，对这部电影的影评，也会给你带过来很多灵感的！


## 内容部分
开头有了，剩下的就是开始叙述正文了。主题介绍是根据影片内容来介绍，如果实在自己想不出来。可以参考其他平台中对这部电影的精彩介绍，提取2-3句也可以！
正常情况下，我们叙述的时候其实是非常简单的，把整部电影主题线，叙述下来，其实文案就是加些修饰词把电影重点内容叙述下来。加上一些修饰词。

以悬疑剧为例：
竟然，突然，原来，但是，但，可是，结果，直到，如果，而，果然，发现，只是，出奇，之后，没错，不止，更是，当然，因为，所以……等！
以上是比较常用的，当然还有很多，需要靠平时思考和阅读的积累！因悬疑剧会有多处反转剧情。所以需要用到反转的修饰词比较多，只有用到这些词。才能体现出各种反转剧情！
建议大家在刚开始做的时候，做8分钟内的，不要太长，分成三段。每段也是不超过三分钟，这样时间刚好。可以比较好的完成完播率！


## 结尾部分
最后故事的结局，除了反转，可以来点人生的道理！如果刚开始不会，可以不写。
后面水平越来越高的时候，可以进行人生道理的讲评。

比如：这部电影告诉我们……
类似于哲理性质的，作为一个总结！
也可以把最后的影视反转，原生放出来，留下悬念。

比如：也可以总结下这部短片如何的好，推荐/值得大家去观看之类的话语。
其实就是给我们的作品来一个总结，总结我们所做的三个视频，有开始就要有结束。这个结束不一定是固定的模版。但是视频一定要有结尾。让人感觉有头有尾才最舒服！
做解说是一个比较浪费脑细胞的活，虽然刚开始比较难一点，但是当你正常做三部剧之后。所有自己的思路都会被打开！以后的基本就可以独立完成来操作来。
做解说第一次，可能会做两天。第二次可能就需要一天了。慢慢的。时间缩短到8个小时之内是我们平常的制作全部时间！

"""


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
    # try:
    gemini_video_file = gemini.upload_file(video_origin_path)
    logger.debug(f"上传视频至 Google cloud 成功: {gemini_video_file.name}")
    while gemini_video_file.state.name == "PROCESSING":
        import time
        time.sleep(1)
        gemini_video_file = gemini.get_file(gemini_video_file.name)
        logger.debug(f"视频当前状态(ACTIVE才可用): {gemini_video_file.state.name}")
    if gemini_video_file.state.name == "FAILED":
        raise ValueError(gemini_video_file.state.name)
    # except Exception as err:
    #     logger.error(f"上传视频至 Google cloud 失败, 请检查 VPN 配置和 APIKey 是否正确 \n{traceback.format_exc()}")
    #     raise TimeoutError(f"上传视频至 Google cloud 失败, 请检查 VPN 配置和 APIKey 是否正确; {err}")

    streams = model.generate_content([prompt, gemini_video_file], stream=True)
    response = []
    for chunk in streams:
        response.append(chunk.text)

    response = "".join(response)
    logger.success(f"llm response: \n{response}")

    return response


def gemini_video_transcription(video_origin_name: str, video_origin_path: str, language: str):
    '''
    使用 gemini-1.5-xxx 进行视频画面转录
    '''
    api_key = config.app.get("gemini_api_key")
    model_name = config.app.get("gemini_model_name")

    gemini.configure(api_key=api_key)
    model = gemini.GenerativeModel(model_name=model_name)

    prompt = """
    Please transcribe the audio, include timestamps, and provide visual descriptions, then output in JSON format，use %s ONLY.

    Use this JSON schema:

    Graphics = {"timestamp": "MM:SS-MM:SS", "picture": "str", "quotes": "str"(If no one says anything, use an empty string instead.)}
    Return: list[Graphics]
    """ % language

    logger.debug(f"视频名称: {video_origin_name}")
    try:
        gemini_video_file = gemini.upload_file(video_origin_path)
        # gemini_video_file = gemini.get_file("files/uxo6r9n80s84")
        logger.debug(f"上传视频至 Google cloud 成功: {gemini_video_file.name}")
        while gemini_video_file.state.name == "PROCESSING":
            import time
            time.sleep(1)
            gemini_video_file = gemini.get_file(gemini_video_file.name)
            logger.debug(f"视频当前状态(ACTIVE才可用): {gemini_video_file.state.name}")
        if gemini_video_file.state.name == "FAILED":
            raise ValueError(gemini_video_file.state.name)
    except ResumableUploadError as err:
        logger.error(f"上传视频至 Google cloud 失败, 用户的位置信息不支持用于该API; \n{traceback.format_exc()}")
        return ""
    except FailedPrecondition as err:
        logger.error(f"400 用户位置不支持 Google API 使用。\n{traceback.format_exc()}")
        return ""

    response = model.generate_content(
        [prompt, gemini_video_file],
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    logger.success(f"llm 视频转录: \n{response.text}")
    return response.text


def video_copy_writing(video_plot, video_name):
    """
    影视解说（电影解说）
    """
    api_key = config.app.get("gemini_api_key")
    model_name = config.app.get("gemini_model_name")

    gemini.configure(api_key=api_key)
    model = gemini.GenerativeModel(model_name)

    prompt = f"""
    **角色设定：**  
    你是一名有10年经验的影视解说文案的创作者，
    下面是关于如何写解说文案的方法 {Method}，请认真阅读它，之后我会给你一部影视作品的名称，然后让你写一篇文案
    请根据方法撰写 《{video_name}》的影视解说文案，文案要符合以下要求:
    
    **任务目标：**  
    1. 文案字数在 1500字左右，严格要求字数，最低不得少于 1000字。
    2. 避免使用 markdown 格式输出文案。  
    3. 仅输出解说文案，不输出任何其他内容。
    4. 不要包含小标题，每个段落以 \n 进行分隔。
    """
    response = model.generate_content(
        prompt,
        generation_config=gemini.types.GenerationConfig(
            candidate_count=1,
            temperature=1.3,
        ),
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    print(response.text)
    print("字数：", len(response.text))


def short_play_commentary(video_plot: str, video_name: str):
    """
    影视解说（短剧解说）
    """
    api_key = config.app.get("gemini_api_key")
    model_name = config.app.get("gemini_model_name")

    gemini.configure(api_key=api_key)
    model = gemini.GenerativeModel(model_name)

    if not video_plot:
        raise ValueError("短剧的简介不能为空")
    if not video_name:
        raise ValueError("短剧名称不能为空")

    prompt = f"""
    **角色设定：**  
    你是一名有10年经验的短剧解说文案的创作者，
    下面是关于如何写解说文案的方法 {Method}，请认真阅读它，之后我会给你一部短剧作品的简介，然后让你写一篇解说文案
    请根据方法撰写 《{video_name}》的解说文案，《{video_name}》的大致剧情如下: {video_plot}
    文案要符合以下要求:

    **任务目标：**  
    1. 文案字数在 800字左右，严格要求字数，最低不得少于 500字。
    2. 避免使用 markdown 格式输出文案。
    3. 仅输出解说文案，不输出任何其他内容。
    4. 不要包含小标题，每个段落以 \n 进行分隔。
    """
    response = model.generate_content(
        prompt,
        generation_config=gemini.types.GenerationConfig(
            candidate_count=1,
            temperature=1.0,
        ),
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    print(response.text)
    print("字数：", len(response.text))


if __name__ == "__main__":
    """
    File API 可让您为每个项目存储最多 20 GB 的文件，每个项目使用 每个文件的大小上限为 2 GB。文件会存储 48 小时。
    它们可以是 在此期间使用您的 API 密钥访问，但无法下载 使用任何 API。它已在使用 Gemini 的所有地区免费提供 API 可用。
    """
    # video_copy_writing("", "阿甘正传")

    video_plot = """
    ## 短剧《卖菜大妈竟是皇嫂》分析

**主要剧情:**

短剧《卖菜大妈竟是皇嫂》讲述了农妇刘桂花在逃荒途中意外救助了一名孩童，这个孩童正是当时的五皇子。然而，在救五皇子的过程中，刘桂花失去了自己的儿子志洲。二十年后，五皇子长大成人，并与刘桂花重逢。刘桂花在得知真相后，面对着皇室的权势和自己的过往，最终选择勇敢地面对命运，并最终收获了幸福。

**内容:**

短剧以古装仙侠为题材，融合了穿越、宫廷、爱情等元素，展现了主角刘桂花从一个平凡的卖菜大妈成长为皇室成员的传奇故事。剧中展现了刘桂花善良、勇敢、坚韧的性格，以及她与五皇子之间错综复杂的情感纠葛。

**核心信息:**

这部短剧的核心信息是“命运的安排，无法改变，但我们可以选择如何面对”。刘桂花在经历了失去儿子的痛苦和与五皇子重逢的惊喜后，最终选择了勇敢地面对命运，并最终获得了幸福。这体现了人性的善良、勇敢和坚韧，也展现了对美好生活的追求和对命运的掌控。

**人物:**

* **刘桂花:**  短剧的主角，一位善良、勇敢、坚韧的农妇。她经历了失去儿子的痛苦，却依然保持着善良的本性，最终获得了幸福。
* **五皇子:** 皇室成员，与刘桂花有着特殊的缘分。他善良、正直、勇敢，最终与刘桂花相爱。

**思考:**

这部短剧带给我们的思考是，面对命运的安排，我们应该保持勇敢和坚韧，积极地面对生活，追求美好的生活，而不是一味地沉溺于痛苦之中。同时，短剧也提醒我们，人性的善良和勇敢，是战胜困难、获得幸福的关键。

**总结:**

《卖菜大妈竟是皇嫂》是一部以女性视角展开的古装仙侠题材作品，讲述了主角刘桂花从一个平凡的卖菜大妈成长为皇室成员的传奇故事。剧中展现了刘桂花善良、勇敢、坚韧的性格，以及她与五皇子之间错综复杂的情感纠葛。这部短剧的核心信息是“命运的安排，无法改变，但我们可以选择如何面对”，它鼓励人们在面对困难时，保持勇敢和坚韧，积极地面对生活，最终获得幸福。
    """
    short_play_commentary(video_plot, "卖菜大妈竟是皇嫂")

    # import os
    # import sys
    # import requests
    # from app.utils.utils import get_current_country
    #
    # # # 添加当前目录到系统路径
    # # sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # # proxy_url_http = "http://127.0.0.1:7890"
    # # os.environ["HTTP_PROXY"] = proxy_url_http
    # # os.environ["HTTPS_PROXY"] = proxy_url_http
    #
    # video_subject = "卖菜大妈竟是皇嫂"
    # video_path = "../../resource/videos/demoyasuo.mp4"
    # # video_path = "../../resource/videos/庆余年2-1-1.mp4"
    #
    # video_plot = ''' '''
    # language = "zh-CN"
    # # res = gemini_video2json(video_subject, video_path, video_plot, language)
    # script = gemini_video_transcription(video_subject, video_path, language)
    # cleaned_string = script.strip("```json").strip("```")
    # res = json.loads(cleaned_string)
    # print(res)

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
    wenan = """
重要提示：每一部剧的文案，前几句必须吸引人
首先我们在看完看懂电影后，大脑里面要先有一个大概的轮廓，也就是一个类似于作文的大纲，电影主题线在哪里，首先要找到。
一般将文案分为开头、内容、结尾
## 开头部分
文案开头三句话，是留住用户的关键！

### 方式一：开头概括总结
文案的前三句，是整部电影的概括总结，2-3句介绍后，开始叙述故事剧情！
推荐新手（新号）做：（盘点型）
盘点全球最恐怖的10部电影
盘点全球最科幻的10部电影
盘点全球最悲惨的10部电影
盘点全球最值得看的10部灾难电影
盘点全球最值得看的10部励志电影

下面的示例就是最简单的解说文案开头：
1.这是XXX国20年来最大尺度的一部剧，极度烧脑，却让99%的人看得心潮澎湃、无法自拔，故事开始……
2.这是有史以来电影院唯一一部全程开灯放完的电影，期间无数人尖叫昏厥，他被成为勇敢者的专属，因为99%的人都不敢看到结局，许多人看完它从此不愿再碰手机，他就是大名鼎鼎的暗黑神作《XXX》……
3.这到底是一部什么样的电影，能被55个国家公开抵制，它甚至为了上映，不惜删减掉整整47分钟的剧情……
4.是什么样的一个人，被豆瓣网友称之为史上最牛P的老太太，都70岁了还要去贩毒……
5.他是M国历史上最NB/惨/猖狂/冤枉……的囚犯/抢劫犯/……
6.这到底是一部什么样的影片，他一个人就拿了4个顶级奖项，第一季8.7分，第二季直接干到9.5分，11万人给出5星好评，一共也就6集，却斩获26项国际大奖，看过的人都说，他是近年来最好的xxx剧，几乎成为了近年来xxx剧的标杆。故事发生在……
7.他是国产电影的巅峰佳作，更是许多80-90后的青春启蒙，曾入选《时代》周刊，获得年度佳片第一，可在国内却被尘封多年，至今为止都无法在各大视频网站看到完整资源，他就是《xxxxxx》
8.这是一部让所有人看得荷尔蒙飙升的爽片……
9.他被成为世界上最虐心绝望的电影，至今无人敢看第二遍，很难想象，他是根据真实事件改编而来……
10.这大概是有史以来最令人不寒而栗的电影，当年一经放映，就点燃了无数人的怒火，不少观众不等影片放完，就愤然离场，它比《xxx》更让人绝望，比比《xxx》更让人xxx，能坚持看完全片的人，更是万中无一，包括我。甚至观影结束后，有无数人抵制投诉这部电影，认为影片的导演玩弄了他们的情感！他就是顶级神作《xxxx》……
11.这是X国有史以来最高赞的一部悬疑电影，然而却因为某些原因，国内90%的人，没能看过这部片子，他就是《xxx》……
12.有这样一部电影，这辈子，你绝对不想再看第二遍，并不是它剧情烂俗，而是它的结局你根本承受不起/想象不到……甚至有80%的观众在观影途中情绪崩溃中途离场，更让许多同行都不想解说这部电影，他就是大名鼎鼎的暗黑神作《xxx》…
13.它被誉为史上最牛悬疑片，无数人在看完它时候，一个月不敢照镜子，这样一部仅适合部分年龄段观看的影片，究竟有什么样的魅力，竟然获得某瓣8.2的高分，很多人说这部电影到处都是看点，他就是《xxx》….
14.这是一部在某瓣上被70万人打出9.3分的高分的电影……到底是一部什么样的电影，能够在某瓣上被70万人打出9.3分的高分……
15.这是一部细思极恐的科幻大片，整部电影颠覆你的三观，它的名字叫……
16.史上最震撼的灾难片，每一点都不舍得快进的电影，他叫……
17.今天给大家带来一部基于真实事件改编的（主题介绍一句……）的故事片，这是一部连环悬疑剧，如果不看到最后绝对想不到结局竟然是这样的反转……

### 方式二：情景式、假设性开头
1.他叫……你以为他是……的吗？不。他是来……然后开始叙述
2.你知道……吗？原来……然后开始叙述
3.如果给你….，你会怎么样？
4.如果你是….，你会怎么样？
 
### 方式三：以国家为开头！简单明了。话语不需要多，但是需要讲解透彻！
1.这是一部韩国最新灾难片，你一定没有看过……
2.这是一部印度高分悬疑片，
3.这部电影原在日本因为……而被下架，
4.这是韩国最恐怖的犯罪片，
5.这是最近国产片评分最高的悬疑片
以上均按照影片国家来区分，然后简单介绍下主题。就可以开始直接叙述作品。也是一个很不错的方法！

### 方式四：如何自由发挥
正常情况下，每一部电影都有非常关键的一个大纲，这部电影的主题其实是可以用一句话、两句话概括的。只要看懂电影，就能找到这个主题大纲。
我们提前把这个主题大纲给放到影视最前面，作为我们的前三句的文案，将会非常吸引人！

例如：
1.这不是电影，这是真实故事。两个女人和一个男人被关在可桑拿室。喊破喉咙也没有一丝回音。窒息感和热度让人抓狂，故事就是从这里开始！ 
2.如果你男朋友出轨了，他不爱你了，还对你家暴，怎么办？接下来这部电影就会教你如何让老公服服帖帖的呆在你身边！女主是一个……开始叙述了。 
3.他力大无穷，双眼放光，这不是拯救地球的超人吗？然而不是。今天给大家推荐的这部电影叫……

以上是需要看完影片，看懂影片，然后从里面提炼出精彩的几句话,当然是比较难的，当你不会自己去总结前三句的经典的话。可以用前面方式一二三！
实在想不出来如何去提炼，可以去搜索这部剧，对这部电影的影评，也会给你带过来很多灵感的！


## 内容部分
开头有了，剩下的就是开始叙述正文了。主题介绍是根据影片内容来介绍，如果实在自己想不出来。可以参考其他平台中对这部电影的精彩介绍，提取2-3句也可以！
正常情况下，我们叙述的时候其实是非常简单的，把整部电影主题线，叙述下来，其实文案就是加些修饰词把电影重点内容叙述下来。加上一些修饰词。

以悬疑剧为例：
竟然，突然，原来，但是，但，可是，结果，直到，如果，而，果然，发现，只是，出奇，之后，没错，不止，更是，当然，因为，所以……等！
以上是比较常用的，当然还有很多，需要靠平时思考和阅读的积累！因悬疑剧会有多处反转剧情。所以需要用到反转的修饰词比较多，只有用到这些词。才能体现出各种反转剧情！
建议大家在刚开始做的时候，做8分钟内的，不要太长，分成三段。每段也是不超过三分钟，这样时间刚好。可以比较好的完成完播率！


## 结尾部分
最后故事的结局，除了反转，可以来点人生的道理！如果刚开始不会，可以不写。
后面水平越来越高的时候，可以进行人生道理的讲评。

比如：这部电影告诉我们……
类似于哲理性质的，作为一个总结！
也可以把最后的影视反转，原生放出来，留下悬念。

比如：也可以总结下这部短片如何的好，推荐/值得大家去观看之类的话语。
其实就是给我们的作品来一个总结，总结我们所做的三个视频，有开始就要有结束。这个结束不一定是固定的模版。但是视频一定要有结尾。让人感觉有头有尾才最舒服！
做解说是一个比较浪费脑细胞的活，虽然刚开始比较难一点，但是当你正常做三部剧之后。所有自己的思路都会被打开！以后的基本就可以独立完成来操作来。
做解说第一次，可能会做两天。第二次可能就需要一天了。慢慢的。时间缩短到8个小时之内是我们平常的制作全部时间！

    """

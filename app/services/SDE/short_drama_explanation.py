#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : 短剧解说
@Author : 小林同学
@Date   : 2025/5/9 上午12:36 
'''

import os
import json
import requests
from typing import Dict, Any, Optional
from loguru import logger
from app.config import config
from app.utils.utils import get_uuid, storage_dir
# 导入新的提示词管理系统
from app.services.prompts import PromptManager


class SubtitleAnalyzer:
    """字幕剧情分析器，负责分析字幕内容并提取关键剧情段落"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        temperature: Optional[float] = 1.0,
        provider: Optional[str] = None,
    ):
        """
        初始化字幕分析器

        Args:
            api_key: API密钥，如果不提供则从配置中读取
            model: 模型名称，如果不提供则从配置中读取
            base_url: API基础URL，如果不提供则从配置中读取或使用默认值
            custom_prompt: 自定义提示词，如果不提供则使用默认值
            temperature: 模型温度
            provider: 提供商类型，用于确定API调用格式
        """
        # 使用传入的参数或从配置中获取
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.provider = provider or self._detect_provider()

        # 设置自定义提示词（如果提供）
        self.custom_prompt = custom_prompt

        # 根据提供商类型确定是否为原生Gemini
        self.is_native_gemini = self.provider.lower() == 'gemini'

        # 初始化HTTP请求所需的头信息
        self._init_headers()

    def _detect_provider(self):
        """根据配置自动检测提供商类型"""
        return config.app.get('text_llm_provider', 'gemini').lower()
    
    def _init_headers(self):
        """初始化HTTP请求头"""
        try:
            # 基础请求头，包含API密钥和内容类型
            self.headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            # logger.debug(f"初始化成功 - API Key: {self.api_key[:8]}... - Base URL: {self.base_url}")
        except Exception as e:
            logger.error(f"初始化请求头失败: {str(e)}")
            raise
    
    def analyze_subtitle(self, subtitle_content: str) -> Dict[str, Any]:
        """
        分析字幕内容

        Args:
            subtitle_content: 字幕内容文本

        Returns:
            Dict[str, Any]: 包含分析结果的字典
        """
        try:
            # 构建完整提示词
            if self.custom_prompt:
                # 使用自定义提示词
                prompt = f"{self.custom_prompt}\n\n{subtitle_content}"
            else:
                # 使用新的提示词管理系统，正确传入参数
                prompt = PromptManager.get_prompt(
                    category="short_drama_narration",
                    name="plot_analysis",
                    parameters={"subtitle_content": subtitle_content}
                )

            if self.is_native_gemini:
                # 使用原生Gemini API格式
                return self._call_native_gemini_api(prompt)
            else:
                # 使用OpenAI兼容格式
                return self._call_openai_compatible_api(prompt)

        except Exception as e:
            logger.error(f"字幕分析过程中发生错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "temperature": self.temperature
            }

    def _call_native_gemini_api(self, prompt: str) -> Dict[str, Any]:
        """调用原生Gemini API"""
        try:
            # 构建原生Gemini API请求数据
            payload = {
                "systemInstruction": {
                    "parts": [{"text": "你是一位专业的剧本分析师和剧情概括助手。请严格按照要求的格式输出分析结果。"}]
                },
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": self.temperature,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 64000,
                    "candidateCount": 1
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]
            }

            # 构建请求URL
            url = f"{self.base_url}/models/{self.model}:generateContent"

            # 发送请求
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                timeout=120
            )

            if response.status_code == 200:
                response_data = response.json()

                # 检查响应格式
                if "candidates" not in response_data or not response_data["candidates"]:
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回无效响应，可能触发了安全过滤",
                        "temperature": self.temperature
                    }

                candidate = response_data["candidates"][0]

                # 检查是否被安全过滤阻止
                if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
                    return {
                        "status": "error",
                        "message": "内容被Gemini安全过滤器阻止",
                        "temperature": self.temperature
                    }

                if "content" not in candidate or "parts" not in candidate["content"]:
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回内容格式错误",
                        "temperature": self.temperature
                    }

                # 提取文本内容
                analysis_result = ""
                for part in candidate["content"]["parts"]:
                    if "text" in part:
                        analysis_result += part["text"]

                if not analysis_result.strip():
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回空内容",
                        "temperature": self.temperature
                    }

                logger.debug(f"原生Gemini字幕分析完成")

                return {
                    "status": "success",
                    "analysis": analysis_result,
                    "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
                    "model": self.model,
                    "temperature": self.temperature
                }
            else:
                error_msg = f"原生Gemini API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "temperature": self.temperature
                }

        except Exception as e:
            logger.error(f"原生Gemini API调用失败: {str(e)}")
            return {
                "status": "error",
                "message": f"原生Gemini API调用失败: {str(e)}",
                "temperature": self.temperature
            }

    def _call_openai_compatible_api(self, prompt: str) -> Dict[str, Any]:
        """调用OpenAI兼容的API"""
        try:
            # 构建OpenAI格式的请求数据
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的剧本分析师和剧情概括助手。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature
            }

            # 构建请求地址
            url = f"{self.base_url}/chat/completions"

            # 发送HTTP请求
            response = requests.post(url, headers=self.headers, json=payload, timeout=120)

            # 解析响应
            if response.status_code == 200:
                response_data = response.json()

                # 提取响应内容
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    analysis_result = response_data["choices"][0]["message"]["content"]
                    logger.debug(f"OpenAI兼容API字幕分析完成，消耗的tokens: {response_data.get('usage', {}).get('total_tokens', 0)}")

                    # 返回结果
                    return {
                        "status": "success",
                        "analysis": analysis_result,
                        "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
                        "model": self.model,
                        "temperature": self.temperature
                    }
                else:
                    logger.error("OpenAI兼容API字幕分析失败: 未获取到有效响应")
                    return {
                        "status": "error",
                        "message": "未获取到有效响应",
                        "temperature": self.temperature
                    }
            else:
                error_msg = f"OpenAI兼容API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "temperature": self.temperature
                }

        except Exception as e:
            logger.error(f"OpenAI兼容API调用失败: {str(e)}")
            return {
                "status": "error",
                "message": f"OpenAI兼容API调用失败: {str(e)}",
                "temperature": self.temperature
            }
    
    def analyze_subtitle_from_file(self, subtitle_file_path: str) -> Dict[str, Any]:
        """
        从文件读取字幕并分析
        
        Args:
            subtitle_file_path: 字幕文件的路径
            
        Returns:
            Dict[str, Any]: 包含分析结果的字典
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(subtitle_file_path):
                return {
                    "status": "error",
                    "message": f"字幕文件不存在: {subtitle_file_path}",
                    "temperature": self.temperature
                }
            
            # 读取文件内容
            with open(subtitle_file_path, 'r', encoding='utf-8') as f:
                subtitle_content = f.read()
            
            # 分析字幕
            return self.analyze_subtitle(subtitle_content)
            
        except Exception as e:
            logger.error(f"从文件读取字幕并分析过程中发生错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "temperature": self.temperature
            }

    def save_analysis_result(self, analysis_result: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        保存分析结果到文件
        
        Args:
            analysis_result: 分析结果
            output_path: 输出文件路径，如果不提供则自动生成
            
        Returns:
            str: 输出文件的路径
        """
        try:
            # 如果未提供输出路径，则自动生成
            if not output_path:
                output_dir = storage_dir("drama_analysis", create=True)
                output_path = os.path.join(output_dir, f"analysis_{get_uuid(True)}.txt")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存结果
            with open(output_path, 'w', encoding='utf-8') as f:
                if analysis_result["status"] == "success":
                    f.write(analysis_result["analysis"])
                else:
                    f.write(f"分析失败: {analysis_result['message']}")
            
            logger.info(f"分析结果已保存到: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"保存分析结果时发生错误: {str(e)}")
            return ""

    def generate_narration_script(self, short_name: str, plot_analysis: str, subtitle_content: str = "", temperature: float = 0.7) -> Dict[str, Any]:
        """
        根据剧情分析生成解说文案

        Args:
            short_name: 短剧名称
            plot_analysis: 剧情分析内容
            subtitle_content: 原始字幕内容，用于提供准确的时间戳信息
            temperature: 生成温度，控制创造性，默认0.7

        Returns:
            Dict[str, Any]: 包含生成结果的字典
        """
        try:
            # 使用新的提示词管理系统构建提示词
            prompt = PromptManager.get_prompt(
                category="short_drama_narration",
                name="script_generation",
                parameters={
                    "drama_name": short_name,
                    "plot_analysis": plot_analysis,
                    "subtitle_content": subtitle_content
                }
            )

            if self.is_native_gemini:
                # 使用原生Gemini API格式
                return self._generate_narration_with_native_gemini(prompt, temperature)
            else:
                # 使用OpenAI兼容格式
                return self._generate_narration_with_openai_compatible(prompt, temperature)

        except Exception as e:
            logger.error(f"解说文案生成过程中发生错误: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "temperature": self.temperature
            }

    def _generate_narration_with_native_gemini(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """使用原生Gemini API生成解说文案"""
        try:
            # 构建原生Gemini API请求数据
            # 为了确保JSON输出，在提示词中添加更强的约束
            enhanced_prompt = f"{prompt}\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"

            payload = {
                "systemInstruction": {
                    "parts": [{"text": "你是一位专业的短视频解说脚本撰写专家。你必须严格按照JSON格式输出，不能包含任何其他文字、说明或代码块标记。"}]
                },
                "contents": [{
                    "parts": [{"text": enhanced_prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 64000,
                    "candidateCount": 1,
                    "stopSequences": ["```", "注意", "说明"]
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]
            }

            # 构建请求URL
            url = f"{self.base_url}/models/{self.model}:generateContent"

            # 发送请求
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                timeout=120
            )

            if response.status_code == 200:
                response_data = response.json()

                # 检查响应格式
                if "candidates" not in response_data or not response_data["candidates"]:
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回无效响应，可能触发了安全过滤",
                        "temperature": temperature
                    }

                candidate = response_data["candidates"][0]

                # 检查是否被安全过滤阻止
                if "finishReason" in candidate and candidate["finishReason"] == "SAFETY":
                    return {
                        "status": "error",
                        "message": "内容被Gemini安全过滤器阻止",
                        "temperature": temperature
                    }

                if "content" not in candidate or "parts" not in candidate["content"]:
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回内容格式错误",
                        "temperature": temperature
                    }

                # 提取文本内容
                narration_script = ""
                for part in candidate["content"]["parts"]:
                    if "text" in part:
                        narration_script += part["text"]

                if not narration_script.strip():
                    return {
                        "status": "error",
                        "message": "原生Gemini API返回空内容",
                        "temperature": temperature
                    }

                logger.debug(f"原生Gemini解说文案生成完成")

                return {
                    "status": "success",
                    "narration_script": narration_script,
                    "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
                    "model": self.model,
                    "temperature": temperature
                }
            else:
                error_msg = f"原生Gemini API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "temperature": temperature
                }

        except Exception as e:
            logger.error(f"原生Gemini API解说文案生成失败: {str(e)}")
            return {
                "status": "error",
                "message": f"原生Gemini API解说文案生成失败: {str(e)}",
                "temperature": temperature
            }

    def _generate_narration_with_openai_compatible(self, prompt: str, temperature: float) -> Dict[str, Any]:
        """使用OpenAI兼容API生成解说文案"""
        try:
            # 构建OpenAI格式的请求数据
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一位专业的短视频解说脚本撰写专家。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature
            }

            # 对特定模型添加响应格式设置
            if self.model not in ["deepseek-reasoner"]:
                payload["response_format"] = {"type": "json_object"}

            # 构建请求地址
            url = f"{self.base_url}/chat/completions"

            # 发送HTTP请求
            response = requests.post(url, headers=self.headers, json=payload, timeout=120)

            # 解析响应
            if response.status_code == 200:
                response_data = response.json()

                # 提取响应内容
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    narration_script = response_data["choices"][0]["message"]["content"]
                    logger.debug(f"OpenAI兼容API解说文案生成完成，消耗的tokens: {response_data.get('usage', {}).get('total_tokens', 0)}")

                    # 返回结果
                    return {
                        "status": "success",
                        "narration_script": narration_script,
                        "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
                        "model": self.model,
                        "temperature": temperature
                    }
                else:
                    logger.error("OpenAI兼容API解说文案生成失败: 未获取到有效响应")
                    return {
                        "status": "error",
                        "message": "未获取到有效响应",
                        "temperature": temperature
                    }
            else:
                error_msg = f"OpenAI兼容API请求失败，状态码: {response.status_code}, 响应: {response.text}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "message": error_msg,
                    "temperature": temperature
                }

        except Exception as e:
            logger.error(f"OpenAI兼容API解说文案生成失败: {str(e)}")
            return {
                "status": "error",
                "message": f"OpenAI兼容API解说文案生成失败: {str(e)}",
                "temperature": temperature
            }
    
    def save_narration_script(self, narration_result: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        保存解说文案到文件
        
        Args:
            narration_result: 解说文案生成结果
            output_path: 输出文件路径，如果不提供则自动生成
            
        Returns:
            str: 输出文件的路径
        """
        try:
            # 如果未提供输出路径，则自动生成
            if not output_path:
                output_dir = storage_dir("narration_scripts", create=True)
                output_path = os.path.join(output_dir, f"narration_{get_uuid(True)}.json")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存结果
            with open(output_path, 'w', encoding='utf-8') as f:
                if narration_result["status"] == "success":
                    f.write(narration_result["narration_script"])
                else:
                    f.write(f"生成失败: {narration_result['message']}")
            
            logger.info(f"解说文案已保存到: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"保存解说文案时发生错误: {str(e)}")
            return ""


def analyze_subtitle(
        subtitle_content: str = None,
        subtitle_file_path: str = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        temperature: float = 1.0,
        save_result: bool = False,
        output_path: Optional[str] = None,
        provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    分析字幕内容的便捷函数

    Args:
        subtitle_content: 字幕内容文本
        subtitle_file_path: 字幕文件路径
        custom_prompt: 自定义提示词
        api_key: API密钥
        model: 模型名称
        base_url: API基础URL
        temperature: 模型温度
        save_result: 是否保存结果到文件
        output_path: 输出文件路径
        provider: 提供商类型

    Returns:
        Dict[str, Any]: 包含分析结果的字典
    """
    # 初始化分析器
    analyzer = SubtitleAnalyzer(
        temperature=temperature,
        api_key=api_key,
        model=model,
        base_url=base_url,
        custom_prompt=custom_prompt,
        provider=provider
    )
    logger.debug(f"使用模型: {analyzer.model} 开始分析, 温度: {analyzer.temperature}")
    # 分析字幕
    if subtitle_content:
        result = analyzer.analyze_subtitle(subtitle_content)
    elif subtitle_file_path:
        result = analyzer.analyze_subtitle_from_file(subtitle_file_path)
    else:
        return {
            "status": "error",
            "message": "必须提供字幕内容或字幕文件路径",
            "temperature": temperature
        }
    
    # 保存结果
    if save_result and result["status"] == "success":
        result["output_path"] = analyzer.save_analysis_result(result, output_path)
    
    return result


def generate_narration_script(
    short_name: str = None,
    plot_analysis: str = None,
    subtitle_content: str = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 1.0,
    save_result: bool = False,
    output_path: Optional[str] = None,
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    根据剧情分析生成解说文案的便捷函数

    Args:
        short_name: 短剧名称
        plot_analysis: 剧情分析内容，直接提供
        subtitle_content: 原始字幕内容，用于提供准确的时间戳信息
        api_key: API密钥
        model: 模型名称
        base_url: API基础URL
        temperature: 生成温度，控制创造性
        save_result: 是否保存结果到文件
        output_path: 输出文件路径
        provider: 提供商类型

    Returns:
        Dict[str, Any]: 包含生成结果的字典
    """
    # 初始化分析器
    analyzer = SubtitleAnalyzer(
        temperature=temperature,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider
    )
    
    # 生成解说文案
    result = analyzer.generate_narration_script(short_name, plot_analysis, subtitle_content or "", temperature)
    
    # 保存结果
    if save_result and result["status"] == "success":
        result["output_path"] = analyzer.save_narration_script(result, output_path)
    
    return result


if __name__ == '__main__':
    text_api_key = "skxxxx"
    text_model = "gemini-2.0-flash"
    text_base_url = "https://api.narratoai.cn/v1/chat/completions"  # 确保URL不以斜杠结尾，便于后续拼接
    subtitle_path = "/Users/apple/Desktop/home/NarratoAI/resource/srt/家里家外1-5.srt"
    
    # 示例用法
    if subtitle_path:
        # 分析字幕总结剧情
        analysis_result = analyze_subtitle(
            subtitle_file_path=subtitle_path,
            api_key=text_api_key,
            model=text_model,
            base_url=text_base_url,
            save_result=True
        )
        
        if analysis_result["status"] == "success":
            print("字幕分析成功！")
            print("分析结果：")
            print(analysis_result["analysis"])

            # 读取原始字幕内容用于解说脚本生成
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                subtitle_content = f.read()

            # 根据剧情生成解说文案
            narration_result = generate_narration_script(
                short_name="家里家外",
                plot_analysis=analysis_result["analysis"],
                subtitle_content=subtitle_content,
                api_key=text_api_key,
                model=text_model,
                base_url=text_base_url,
                save_result=True
            )
            
            if narration_result["status"] == "success":
                print("\n解说文案生成成功！")
                print("解说文案：")
                print(narration_result["narration_script"])
            else:
                print(f"\n解说文案生成失败: {narration_result['message']}")
        else:
            print(f"分析失败: {analysis_result['message']}")

"""
DeepSeek API提供商实现

支持DeepSeek的文本生成模型
"""

import asyncio
from typing import List, Dict, Any, Optional
from openai import OpenAI, BadRequestError
from loguru import logger

from ..base import TextModelProvider
from ..exceptions import APICallError


class DeepSeekTextProvider(TextModelProvider):
    """DeepSeek文本生成提供商"""
    
    @property
    def provider_name(self) -> str:
        return "deepseek"
    
    @property
    def supported_models(self) -> List[str]:
        return [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-r1",
            "deepseek-v3"
        ]
    
    def _initialize(self):
        """初始化DeepSeek客户端"""
        if not self.base_url:
            self.base_url = "https://api.deepseek.com"
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    async def generate_text(self,
                          prompt: str,
                          system_prompt: Optional[str] = None,
                          temperature: float = 1.0,
                          max_tokens: Optional[int] = None,
                          response_format: Optional[str] = None,
                          **kwargs) -> str:
        """
        使用DeepSeek API生成文本
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 生成温度
            max_tokens: 最大token数
            response_format: 响应格式 ('json' 或 None)
            **kwargs: 其他参数
            
        Returns:
            生成的文本内容
        """
        # 构建消息列表
        messages = self._build_messages(prompt, system_prompt)
        
        # 构建请求参数
        request_params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # 处理JSON格式输出
        # DeepSeek R1 和 V3 不支持 response_format=json_object
        if response_format == "json":
            if self._supports_response_format():
                request_params["response_format"] = {"type": "json_object"}
            else:
                # 对于不支持response_format的模型，在提示词中添加约束
                messages[-1]["content"] += "\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"
        
        try:
            # 发送API请求
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                **request_params
            )
            
            # 提取生成的内容
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                
                # 对于不支持response_format的模型，清理输出
                if response_format == "json" and not self._supports_response_format():
                    content = self._clean_json_output(content)
                
                logger.debug(f"DeepSeek API调用成功，消耗tokens: {response.usage.total_tokens if response.usage else 'N/A'}")
                return content
            else:
                raise APICallError("DeepSeek API返回空响应")
                
        except BadRequestError as e:
            # 处理不支持response_format的情况
            if "response_format" in str(e) and response_format == "json":
                logger.warning(f"DeepSeek模型 {self.model_name} 不支持response_format，重试不带格式约束的请求")
                request_params.pop("response_format", None)
                messages[-1]["content"] += "\n\n请确保输出严格的JSON格式，不要包含任何其他文字或标记。"
                
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    **request_params
                )
                
                if response.choices and len(response.choices) > 0:
                    content = response.choices[0].message.content
                    content = self._clean_json_output(content)
                    return content
                else:
                    raise APICallError("DeepSeek API返回空响应")
            else:
                raise APICallError(f"DeepSeek API请求失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {str(e)}")
            raise APICallError(f"DeepSeek API调用失败: {str(e)}")
    
    def _supports_response_format(self) -> bool:
        """检查模型是否支持response_format参数"""
        # DeepSeek R1 和 V3 不支持 response_format=json_object
        unsupported_models = [
            "deepseek-reasoner",
            "deepseek-r1",
            "deepseek-v3"
        ]
        
        return not any(unsupported in self.model_name.lower() for unsupported in unsupported_models)
    
    def _clean_json_output(self, output: str) -> str:
        """清理JSON输出，移除markdown标记等"""
        import re
        
        # 移除可能的markdown代码块标记
        output = re.sub(r'^```json\s*', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```\s*$', '', output, flags=re.MULTILINE)
        output = re.sub(r'^```.*$', '', output, flags=re.MULTILINE)
        
        # 移除前后空白字符
        output = output.strip()
        
        return output
    
    async def _make_api_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行API调用 - 由于使用OpenAI SDK，这个方法主要用于兼容基类"""
        pass

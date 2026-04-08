#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
自定义Prompt管理器
用于管理用户自定义的短剧解说脚本生成Prompt
"""

import os
import json
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger


class CustomPromptManager:
    """自定义Prompt管理器"""
    
    def __init__(self):
        self.prompts_dir = self._get_prompts_dir()
        self._ensure_prompts_dir()
    
    def _get_prompts_dir(self) -> str:
        """获取自定义Prompt存储目录"""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        prompts_dir = os.path.join(base_dir, "storage", "custom_prompts")
        return prompts_dir
    
    def _ensure_prompts_dir(self):
        """确保Prompt目录存在"""
        if not os.path.exists(self.prompts_dir):
            os.makedirs(self.prompts_dir, exist_ok=True)
            logger.info(f"创建自定义Prompt目录: {self.prompts_dir}")
    
    def list_prompts(self) -> List[Dict[str, str]]:
        """列出所有自定义Prompt"""
        prompts = []
        
        try:
            if not os.path.exists(self.prompts_dir):
                return prompts
            
            for filename in os.listdir(self.prompts_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.prompts_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            prompt_data = json.load(f)
                            if isinstance(prompt_data, dict) and 'name' in prompt_data and 'content' in prompt_data:
                                prompts.append({
                                    'id': filename[:-5],  # 移除.json后缀
                                    'name': prompt_data['name'],
                                    'content': prompt_data['content'],
                                    'description': prompt_data.get('description', ''),
                                    'created_at': prompt_data.get('created_at', ''),
                                    'updated_at': prompt_data.get('updated_at', '')
                                })
                    except Exception as e:
                        logger.error(f"加载Prompt文件失败 {filename}: {e}")
                        continue
        except Exception as e:
            logger.error(f"列出Prompt失败: {e}")
        
        return prompts
    
    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, str]]:
        """获取指定ID的Prompt"""
        filepath = os.path.join(self.prompts_dir, f"{prompt_id}.json")
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                prompt_data = json.load(f)
                if isinstance(prompt_data, dict) and 'name' in prompt_data and 'content' in prompt_data:
                    return prompt_data
        except Exception as e:
            logger.error(f"加载Prompt失败 {prompt_id}: {e}")
            return None
    
    def save_prompt(self, name: str, content: str, description: str = "") -> str:
        """保存新的自定义Prompt"""
        import time
        from app.utils.utils import get_uuid
        
        prompt_id = get_uuid(True)
        prompt_data = {
            'name': name,
            'content': content,
            'description': description,
            'created_at': time.strftime("%Y-%m-%d %H:%M:%S"),
            'updated_at': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        filepath = os.path.join(self.prompts_dir, f"{prompt_id}.json")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(prompt_data, f, ensure_ascii=False, indent=2)
            logger.info(f"保存自定义Prompt成功: {name} ({prompt_id})")
            return prompt_id
        except Exception as e:
            logger.error(f"保存Prompt失败: {e}")
            raise
    
    def update_prompt(self, prompt_id: str, name: str, content: str, description: str = "") -> bool:
        """更新现有的Prompt"""
        filepath = os.path.join(self.prompts_dir, f"{prompt_id}.json")
        
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                prompt_data = json.load(f)
            
            prompt_data['name'] = name
            prompt_data['content'] = content
            prompt_data['description'] = description
            import time
            prompt_data['updated_at'] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(prompt_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"更新自定义Prompt成功: {name} ({prompt_id})")
            return True
        except Exception as e:
            logger.error(f"更新Prompt失败: {e}")
            return False
    
    def delete_prompt(self, prompt_id: str) -> bool:
        """删除指定的Prompt"""
        filepath = os.path.join(self.prompts_dir, f"{prompt_id}.json")
        
        if not os.path.exists(filepath):
            return False
        
        try:
            os.remove(filepath)
            logger.info(f"删除自定义Prompt成功: {prompt_id}")
            return True
        except Exception as e:
            logger.error(f"删除Prompt失败: {e}")
            return False
    
    def get_default_prompt(self) -> str:
        """获取默认的Prompt模板"""
        from app.services.prompts import PromptManager
        try:
            return PromptManager.get_prompt(
                category="short_drama_narration",
                name="script_generation",
                parameters={}
            )
        except Exception as e:
            logger.error(f"获取默认Prompt失败: {e}")
            return ""


# 全局单例
_custom_prompt_manager = None

def get_custom_prompt_manager() -> CustomPromptManager:
    """获取自定义Prompt管理器单例"""
    global _custom_prompt_manager
    if _custom_prompt_manager is None:
        _custom_prompt_manager = CustomPromptManager()
    return _custom_prompt_manager

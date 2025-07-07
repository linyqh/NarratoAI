#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : audio_config
@Author : Viccy同学
@Date   : 2025/1/7 
@Description: 音频配置管理
'''

from typing import Dict, Any
from loguru import logger


class AudioConfig:
    """音频配置管理类"""
    
    # 默认音量配置
    DEFAULT_VOLUMES = {
        'tts_volume': 0.8,          # TTS音量稍微降低
        'original_volume': 1.3,     # 原声音量提高
        'bgm_volume': 0.3,          # 背景音乐保持较低
    }
    
    # 音频质量配置
    AUDIO_QUALITY = {
        'sample_rate': 44100,       # 采样率
        'channels': 2,              # 声道数（立体声）
        'bitrate': '128k',          # 比特率
    }
    
    # 音频处理配置
    PROCESSING_CONFIG = {
        'enable_smart_volume': True,        # 启用智能音量调整
        'enable_audio_normalization': True, # 启用音频标准化
        'target_lufs': -20.0,              # 目标响度 (LUFS)
        'max_peak': -1.0,                  # 最大峰值 (dBFS)
        'volume_analysis_method': 'lufs',   # 音量分析方法: 'lufs' 或 'rms'
    }
    
    # 音频混合配置
    MIXING_CONFIG = {
        'crossfade_duration': 0.1,     # 交叉淡化时长（秒）
        'bgm_fade_out': 3.0,           # BGM淡出时长（秒）
        'dynamic_range_compression': False,  # 动态范围压缩
    }
    
    @classmethod
    def get_optimized_volumes(cls, video_type: str = 'default') -> Dict[str, float]:
        """
        根据视频类型获取优化的音量配置
        
        Args:
            video_type: 视频类型 ('default', 'educational', 'entertainment', 'news')
            
        Returns:
            Dict[str, float]: 音量配置字典
        """
        base_volumes = cls.DEFAULT_VOLUMES.copy()
        
        # 根据视频类型调整音量
        if video_type == 'educational':
            # 教育类视频：突出解说，降低原声
            base_volumes.update({
                'tts_volume': 0.9,
                'original_volume': 0.8,
                'bgm_volume': 0.2,
            })
        elif video_type == 'entertainment':
            # 娱乐类视频：平衡解说和原声
            base_volumes.update({
                'tts_volume': 0.8,
                'original_volume': 1.2,
                'bgm_volume': 0.4,
            })
        elif video_type == 'news':
            # 新闻类视频：突出解说，最小化背景音
            base_volumes.update({
                'tts_volume': 1.0,
                'original_volume': 0.6,
                'bgm_volume': 0.1,
            })
        
        logger.info(f"使用 {video_type} 类型的音量配置: {base_volumes}")
        return base_volumes
    
    @classmethod
    def get_audio_processing_config(cls) -> Dict[str, Any]:
        """获取音频处理配置"""
        return cls.PROCESSING_CONFIG.copy()
    
    @classmethod
    def get_mixing_config(cls) -> Dict[str, Any]:
        """获取音频混合配置"""
        return cls.MIXING_CONFIG.copy()
    
    @classmethod
    def validate_volume(cls, volume: float, name: str) -> float:
        """
        验证和限制音量值
        
        Args:
            volume: 音量值
            name: 音量名称（用于日志）
            
        Returns:
            float: 验证后的音量值
        """
        min_volume = 0.0
        max_volume = 2.0  # 允许原声超过1.0
        
        if volume < min_volume:
            logger.warning(f"{name}音量 {volume} 低于最小值 {min_volume}，已调整")
            return min_volume
        elif volume > max_volume:
            logger.warning(f"{name}音量 {volume} 超过最大值 {max_volume}，已调整")
            return max_volume
        
        return volume
    
    @classmethod
    def apply_volume_profile(cls, profile_name: str) -> Dict[str, float]:
        """
        应用预设的音量配置文件
        
        Args:
            profile_name: 配置文件名称
            
        Returns:
            Dict[str, float]: 音量配置
        """
        profiles = {
            'balanced': {
                'tts_volume': 0.8,
                'original_volume': 1.2,
                'bgm_volume': 0.3,
            },
            'voice_focused': {
                'tts_volume': 1.0,
                'original_volume': 0.7,
                'bgm_volume': 0.2,
            },
            'original_focused': {
                'tts_volume': 0.7,
                'original_volume': 1.5,
                'bgm_volume': 0.2,
            },
            'quiet_background': {
                'tts_volume': 0.8,
                'original_volume': 1.3,
                'bgm_volume': 0.1,
            }
        }
        
        if profile_name in profiles:
            logger.info(f"应用音量配置文件: {profile_name}")
            return profiles[profile_name]
        else:
            logger.warning(f"未找到配置文件 {profile_name}，使用默认配置")
            return cls.DEFAULT_VOLUMES.copy()


# 全局音频配置实例
audio_config = AudioConfig()


def get_recommended_volumes_for_content(content_type: str = 'mixed') -> Dict[str, float]:
    """
    根据内容类型推荐音量设置
    
    Args:
        content_type: 内容类型
            - 'mixed': 混合内容（默认）
            - 'voice_only': 纯解说
            - 'original_heavy': 原声为主
            - 'music_video': 音乐视频
            
    Returns:
        Dict[str, float]: 推荐的音量配置
    """
    recommendations = {
        'mixed': {
            'tts_volume': 0.8,
            'original_volume': 1.3,
            'bgm_volume': 0.3,
        },
        'voice_only': {
            'tts_volume': 1.0,
            'original_volume': 0.5,
            'bgm_volume': 0.2,
        },
        'original_heavy': {
            'tts_volume': 0.6,
            'original_volume': 1.6,
            'bgm_volume': 0.1,
        },
        'music_video': {
            'tts_volume': 0.7,
            'original_volume': 1.8,
            'bgm_volume': 0.0,  # 不添加额外BGM
        }
    }
    
    return recommendations.get(content_type, recommendations['mixed'])


if __name__ == "__main__":
    # 测试配置
    config = AudioConfig()
    
    # 测试不同类型的音量配置
    for video_type in ['default', 'educational', 'entertainment', 'news']:
        volumes = config.get_optimized_volumes(video_type)
        print(f"{video_type}: {volumes}")
    
    # 测试配置文件
    for profile in ['balanced', 'voice_focused', 'original_focused']:
        volumes = config.apply_volume_profile(profile)
        print(f"{profile}: {volumes}")

#!/usr/bin/env python
# -*- coding: UTF-8 -*-

'''
@Project: NarratoAI
@File   : audio_normalizer
@Author : Viccy同学
@Date   : 2025/1/7 
@Description: 音频响度分析和标准化工具
'''

import os
import subprocess
import tempfile
from typing import Optional, Tuple, Dict, Any
from loguru import logger
from moviepy import AudioFileClip
from pydub import AudioSegment
import numpy as np


class AudioNormalizer:
    """音频响度分析和标准化工具"""
    
    def __init__(self):
        self.target_lufs = -23.0  # 目标响度 (LUFS)，符合广播标准
        self.max_peak = -1.0      # 最大峰值 (dBFS)
        
    def analyze_audio_lufs(self, audio_path: str) -> Optional[float]:
        """
        使用FFmpeg分析音频的LUFS响度
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            float: LUFS值，如果分析失败返回None
        """
        if not os.path.exists(audio_path):
            logger.error(f"音频文件不存在: {audio_path}")
            return None
            
        try:
            # 使用FFmpeg的loudnorm滤镜分析音频响度
            cmd = [
                'ffmpeg', '-hide_banner', '-nostats',
                '-i', audio_path,
                '-af', 'loudnorm=I=-23:TP=-1:LRA=7:print_format=json',
                '-f', 'null', '-'
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=False
            )
            
            # 从stderr中提取JSON信息
            stderr_lines = result.stderr.split('\n')
            json_start = False
            json_lines = []
            
            for line in stderr_lines:
                if line.strip() == '{':
                    json_start = True
                if json_start:
                    json_lines.append(line)
                if line.strip() == '}':
                    break
                    
            if json_lines:
                import json
                try:
                    loudness_data = json.loads('\n'.join(json_lines))
                    input_i = float(loudness_data.get('input_i', 0))
                    logger.info(f"音频 {os.path.basename(audio_path)} 的LUFS: {input_i}")
                    return input_i
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"解析LUFS数据失败: {e}")
                    
        except Exception as e:
            logger.error(f"分析音频LUFS失败: {e}")
            
        return None
    
    def get_audio_rms(self, audio_path: str) -> Optional[float]:
        """
        计算音频的RMS值作为响度的简单估计
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            float: RMS值 (dB)，如果计算失败返回None
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            # 转换为numpy数组
            samples = np.array(audio.get_array_of_samples())
            
            # 如果是立体声，取平均值
            if audio.channels == 2:
                samples = samples.reshape((-1, 2))
                samples = samples.mean(axis=1)
            
            # 计算RMS
            rms = np.sqrt(np.mean(samples**2))
            
            # 转换为dB
            if rms > 0:
                rms_db = 20 * np.log10(rms / (2**15))  # 假设16位音频
                logger.info(f"音频 {os.path.basename(audio_path)} 的RMS: {rms_db:.2f} dB")
                return rms_db
            else:
                return -60.0  # 静音
                
        except Exception as e:
            logger.error(f"计算音频RMS失败: {e}")
            return None
    
    def normalize_audio_lufs(self, input_path: str, output_path: str, 
                           target_lufs: Optional[float] = None) -> bool:
        """
        使用FFmpeg的loudnorm滤镜标准化音频响度
        
        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径
            target_lufs: 目标LUFS值，默认使用-23.0
            
        Returns:
            bool: 是否成功
        """
        if target_lufs is None:
            target_lufs = self.target_lufs
            
        try:
            # 第一遍：分析音频
            analyze_cmd = [
                'ffmpeg', '-hide_banner', '-nostats',
                '-i', input_path,
                '-af', f'loudnorm=I={target_lufs}:TP={self.max_peak}:LRA=7:print_format=json',
                '-f', 'null', '-'
            ]
            
            analyze_result = subprocess.run(
                analyze_cmd, 
                capture_output=True, 
                text=True, 
                check=False
            )
            
            # 解析分析结果
            stderr_lines = analyze_result.stderr.split('\n')
            json_start = False
            json_lines = []
            
            for line in stderr_lines:
                if line.strip() == '{':
                    json_start = True
                if json_start:
                    json_lines.append(line)
                if line.strip() == '}':
                    break
            
            if not json_lines:
                logger.warning("无法获取音频分析数据，使用简单标准化")
                return self._simple_normalize(input_path, output_path)
            
            import json
            loudness_data = json.loads('\n'.join(json_lines))
            
            # 第二遍：应用标准化
            normalize_cmd = [
                'ffmpeg', '-y', '-hide_banner',
                '-i', input_path,
                '-af', (
                    f'loudnorm=I={target_lufs}:TP={self.max_peak}:LRA=7:'
                    f'measured_I={loudness_data["input_i"]}:'
                    f'measured_LRA={loudness_data["input_lra"]}:'
                    f'measured_TP={loudness_data["input_tp"]}:'
                    f'measured_thresh={loudness_data["input_thresh"]}'
                ),
                '-ar', '44100',  # 统一采样率
                '-ac', '2',      # 统一为立体声
                output_path
            ]
            
            result = subprocess.run(
                normalize_cmd, 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            logger.info(f"音频标准化完成: {output_path}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg标准化失败: {e}")
            return self._simple_normalize(input_path, output_path)
        except Exception as e:
            logger.error(f"音频标准化失败: {e}")
            return False
    
    def _simple_normalize(self, input_path: str, output_path: str) -> bool:
        """
        简单的音频标准化（备用方案）
        
        Args:
            input_path: 输入音频文件路径
            output_path: 输出音频文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用pydub进行简单的音量标准化
            audio = AudioSegment.from_file(input_path)
            
            # 标准化到-20dB
            target_dBFS = -20.0
            change_in_dBFS = target_dBFS - audio.dBFS
            normalized_audio = audio.apply_gain(change_in_dBFS)
            
            # 导出
            normalized_audio.export(output_path, format="mp3", bitrate="128k")
            logger.info(f"简单音频标准化完成: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"简单音频标准化失败: {e}")
            return False
    
    def calculate_volume_adjustment(self, tts_path: str, original_path: str) -> Tuple[float, float]:
        """
        计算TTS和原声的音量调整系数，使它们达到相似的响度
        
        Args:
            tts_path: TTS音频文件路径
            original_path: 原声音频文件路径
            
        Returns:
            Tuple[float, float]: (TTS音量系数, 原声音量系数)
        """
        # 分析两个音频的响度
        tts_lufs = self.analyze_audio_lufs(tts_path)
        original_lufs = self.analyze_audio_lufs(original_path)
        
        # 如果LUFS分析失败，使用RMS作为备用
        if tts_lufs is None:
            tts_lufs = self.get_audio_rms(tts_path)
        if original_lufs is None:
            original_lufs = self.get_audio_rms(original_path)
        
        if tts_lufs is None or original_lufs is None:
            logger.warning("无法分析音频响度，使用默认音量设置")
            return 0.7, 1.0  # 默认设置
        
        # 计算调整系数
        # 目标：让两个音频达到相似的响度
        target_lufs = -20.0  # 目标响度
        
        tts_adjustment = 10 ** ((target_lufs - tts_lufs) / 20)
        original_adjustment = 10 ** ((target_lufs - original_lufs) / 20)
        
        # 限制调整范围，避免过度放大
        tts_adjustment = max(0.1, min(2.0, tts_adjustment))
        original_adjustment = max(0.1, min(3.0, original_adjustment))  # 原声可以放大更多
        
        logger.info(f"音量调整建议 - TTS: {tts_adjustment:.2f}, 原声: {original_adjustment:.2f}")
        return tts_adjustment, original_adjustment


def normalize_audio_for_mixing(audio_path: str, output_dir: str, 
                             target_lufs: float = -20.0) -> Optional[str]:
    """
    为音频混合准备标准化的音频文件
    
    Args:
        audio_path: 输入音频文件路径
        output_dir: 输出目录
        target_lufs: 目标LUFS值
        
    Returns:
        str: 标准化后的音频文件路径，失败返回None
    """
    if not os.path.exists(audio_path):
        return None
        
    normalizer = AudioNormalizer()
    
    # 生成输出文件名
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_normalized.mp3")
    
    # 执行标准化
    if normalizer.normalize_audio_lufs(audio_path, output_path, target_lufs):
        return output_path
    else:
        return None


if __name__ == "__main__":
    # 测试代码
    normalizer = AudioNormalizer()
    
    # 测试音频分析
    test_audio = "/path/to/test/audio.mp3"
    if os.path.exists(test_audio):
        lufs = normalizer.analyze_audio_lufs(test_audio)
        rms = normalizer.get_audio_rms(test_audio)
        print(f"LUFS: {lufs}, RMS: {rms}")

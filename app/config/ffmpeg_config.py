"""
FFmpeg 配置管理模块
专门用于管理 FFmpeg 兼容性设置和优化参数
"""

import os
import platform
from typing import Dict, List, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class FFmpegProfile:
    """FFmpeg 配置文件"""
    name: str
    description: str
    hwaccel_enabled: bool
    hwaccel_type: Optional[str]
    encoder: str
    quality_preset: str
    pixel_format: str
    additional_args: List[str]
    compatibility_level: int  # 1-5, 5为最高兼容性


class FFmpegConfigManager:
    """FFmpeg 配置管理器"""
    
    # 预定义的配置文件
    PROFILES = {
        # 高性能配置（适用于现代硬件）
        "high_performance": FFmpegProfile(
            name="high_performance",
            description="高性能配置（NVIDIA/AMD 独立显卡）",
            hwaccel_enabled=True,
            hwaccel_type="auto",
            encoder="auto",
            quality_preset="fast",
            pixel_format="yuv420p",
            additional_args=["-preset", "fast"],
            compatibility_level=2
        ),
        
        # 兼容性配置（适用于有问题的硬件）
        "compatibility": FFmpegProfile(
            name="compatibility",
            description="兼容性配置（解决滤镜链问题）",
            hwaccel_enabled=False,
            hwaccel_type=None,
            encoder="libx264",
            quality_preset="medium",
            pixel_format="yuv420p",
            additional_args=["-preset", "medium", "-crf", "23"],
            compatibility_level=5
        ),
        
        # Windows N 卡优化配置
        "windows_nvidia": FFmpegProfile(
            name="windows_nvidia",
            description="Windows NVIDIA 显卡优化配置",
            hwaccel_enabled=True,
            hwaccel_type="nvenc_pure",  # 纯编码器，避免解码问题
            encoder="h264_nvenc",
            quality_preset="medium",
            pixel_format="yuv420p",
            additional_args=["-preset", "medium", "-cq", "23"],
            compatibility_level=3
        ),
        
        # macOS 优化配置
        "macos_videotoolbox": FFmpegProfile(
            name="macos_videotoolbox",
            description="macOS VideoToolbox 优化配置",
            hwaccel_enabled=True,
            hwaccel_type="videotoolbox",
            encoder="h264_videotoolbox",
            quality_preset="medium",
            pixel_format="yuv420p",
            additional_args=["-q:v", "65"],
            compatibility_level=3
        ),
        
        # 通用软件配置
        "universal_software": FFmpegProfile(
            name="universal_software",
            description="通用软件编码配置（最高兼容性）",
            hwaccel_enabled=False,
            hwaccel_type=None,
            encoder="libx264",
            quality_preset="medium",
            pixel_format="yuv420p",
            additional_args=["-preset", "medium", "-crf", "23"],
            compatibility_level=5
        )
    }
    
    @classmethod
    def get_recommended_profile(cls) -> str:
        """
        根据系统环境推荐最佳配置文件
        
        Returns:
            str: 推荐的配置文件名称
        """
        system = platform.system().lower()
        
        # 检测硬件加速可用性
        try:
            from app.utils import ffmpeg_utils
            hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
            hwaccel_available = hwaccel_info.get("available", False)
            hwaccel_type = hwaccel_info.get("type", "software")
            gpu_vendor = hwaccel_info.get("gpu_vendor", "unknown")
        except Exception as e:
            logger.warning(f"无法检测硬件加速信息: {e}")
            hwaccel_available = False
            hwaccel_type = "software"
            gpu_vendor = "unknown"
        
        # 根据平台和硬件推荐配置
        if system == "windows":
            if hwaccel_available and gpu_vendor == "nvidia":
                return "windows_nvidia"
            elif hwaccel_available:
                return "high_performance"
            else:
                return "compatibility"
        elif system == "darwin":
            if hwaccel_available and hwaccel_type == "videotoolbox":
                return "macos_videotoolbox"
            else:
                return "universal_software"
        elif system == "linux":
            if hwaccel_available:
                return "high_performance"
            else:
                return "universal_software"
        else:
            return "universal_software"
    
    @classmethod
    def get_profile(cls, profile_name: str) -> FFmpegProfile:
        """
        获取指定的配置文件
        
        Args:
            profile_name: 配置文件名称
            
        Returns:
            FFmpegProfile: 配置文件对象
        """
        if profile_name not in cls.PROFILES:
            logger.warning(f"未知的配置文件: {profile_name}，使用默认配置")
            profile_name = "universal_software"
        
        return cls.PROFILES[profile_name]
    
    @classmethod
    def get_extraction_command(cls, 
                             input_path: str, 
                             output_path: str, 
                             timestamp: float,
                             profile_name: Optional[str] = None) -> List[str]:
        """
        根据配置文件生成关键帧提取命令
        
        Args:
            input_path: 输入视频路径
            output_path: 输出图片路径
            timestamp: 时间戳
            profile_name: 配置文件名称，None 表示自动选择
            
        Returns:
            List[str]: FFmpeg 命令列表
        """
        if profile_name is None:
            profile_name = cls.get_recommended_profile()
        
        profile = cls.get_profile(profile_name)
        
        # 构建基础命令
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
        ]
        
        # 添加硬件加速参数
        if profile.hwaccel_enabled and profile.hwaccel_type:
            if profile.hwaccel_type == "auto":
                # 自动检测硬件加速
                try:
                    from app.utils import ffmpeg_utils
                    hw_args = ffmpeg_utils.get_ffmpeg_hwaccel_args()
                    cmd.extend(hw_args)
                except Exception:
                    pass
            elif profile.hwaccel_type == "nvenc_pure":
                # 纯 NVENC 编码器，不使用硬件解码
                pass
            else:
                # 指定的硬件加速类型
                cmd.extend(["-hwaccel", profile.hwaccel_type])
        
        # 添加输入参数
        cmd.extend([
            "-ss", str(timestamp),
            "-i", input_path,
            "-vframes", "1",
        ])
        
        # 添加质量和格式参数
        if profile.encoder == "libx264":
            cmd.extend(["-q:v", "2"])
        elif profile.encoder == "h264_nvenc":
            cmd.extend(["-cq", "23"])
        elif profile.encoder == "h264_videotoolbox":
            cmd.extend(["-q:v", "65"])
        else:
            cmd.extend(["-q:v", "2"])
        
        # 添加像素格式
        cmd.extend(["-pix_fmt", profile.pixel_format])
        
        # 添加额外参数
        cmd.extend(profile.additional_args)
        
        # 添加输出参数
        cmd.extend(["-y", output_path])
        
        return cmd
    
    @classmethod
    def list_profiles(cls) -> Dict[str, str]:
        """
        列出所有可用的配置文件
        
        Returns:
            Dict[str, str]: 配置文件名称到描述的映射
        """
        return {name: profile.description for name, profile in cls.PROFILES.items()}
    
    @classmethod
    def get_compatibility_report(cls) -> Dict[str, any]:
        """
        生成兼容性报告
        
        Returns:
            Dict: 兼容性报告
        """
        recommended_profile = cls.get_recommended_profile()
        profile = cls.get_profile(recommended_profile)
        
        try:
            from app.utils import ffmpeg_utils
            hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
        except Exception:
            hwaccel_info = {"available": False, "message": "检测失败"}
        
        return {
            "system": platform.system(),
            "recommended_profile": recommended_profile,
            "profile_description": profile.description,
            "compatibility_level": profile.compatibility_level,
            "hardware_acceleration": hwaccel_info,
            "suggestions": cls._get_suggestions(profile, hwaccel_info)
        }
    
    @classmethod
    def _get_suggestions(cls, profile: FFmpegProfile, hwaccel_info: Dict) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        if not hwaccel_info.get("available", False):
            suggestions.append("建议更新显卡驱动以启用硬件加速")
        
        if profile.compatibility_level >= 4:
            suggestions.append("当前使用高兼容性配置，性能可能较低")
        
        if platform.system().lower() == "windows" and "nvidia" in hwaccel_info.get("gpu_vendor", "").lower():
            suggestions.append("Windows NVIDIA 用户建议使用纯编码器模式避免滤镜链问题")
        
        return suggestions

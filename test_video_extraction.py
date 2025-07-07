#!/usr/bin/env python3
"""
视频关键帧提取测试脚本
用于验证 Windows 系统 FFmpeg 兼容性修复效果
"""

import os
import sys
import tempfile
import traceback
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from app.utils import video_processor, ffmpeg_utils


def test_ffmpeg_compatibility():
    """测试 FFmpeg 兼容性"""
    print("=" * 60)
    print("🔧 FFmpeg 兼容性测试")
    print("=" * 60)
    
    # 检查 FFmpeg 安装
    if not ffmpeg_utils.check_ffmpeg_installation():
        print("❌ FFmpeg 未安装或不在系统 PATH 中")
        return False
    
    print("✅ FFmpeg 已安装")
    
    # 获取硬件加速信息
    hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
    print(f"🎮 硬件加速状态: {hwaccel_info.get('message', '未知')}")
    print(f"🔧 加速类型: {hwaccel_info.get('type', 'software')}")
    print(f"🎯 编码器: {hwaccel_info.get('encoder', 'libx264')}")
    
    return True


def test_video_extraction(video_path: str, output_dir: str = None):
    """测试视频关键帧提取"""
    print("\n" + "=" * 60)
    print("🎬 视频关键帧提取测试")
    print("=" * 60)
    
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    # 创建临时输出目录
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="keyframes_test_")
    
    try:
        # 初始化视频处理器
        print(f"📁 输入视频: {video_path}")
        print(f"📁 输出目录: {output_dir}")
        
        processor = video_processor.VideoProcessor(video_path)
        
        # 显示视频信息
        print(f"📊 视频信息:")
        print(f"   - 分辨率: {processor.width}x{processor.height}")
        print(f"   - 帧率: {processor.fps:.1f} fps")
        print(f"   - 时长: {processor.duration:.1f} 秒")
        print(f"   - 总帧数: {processor.total_frames}")
        
        # 测试关键帧提取
        print("\n🚀 开始提取关键帧...")
        
        # 先测试硬件加速方案
        print("\n1️⃣ 测试硬件加速方案:")
        try:
            processor.process_video_pipeline(
                output_dir=output_dir,
                interval_seconds=10.0,  # 10秒间隔，减少测试时间
                use_hw_accel=True
            )
            
            # 检查结果
            extracted_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
            print(f"✅ 硬件加速成功，提取了 {len(extracted_files)} 个关键帧")
            
            if len(extracted_files) > 0:
                return True
                
        except Exception as e:
            print(f"⚠️ 硬件加速失败: {str(e)}")
            
            # 清理失败的文件
            for f in os.listdir(output_dir):
                if f.endswith('.jpg'):
                    os.remove(os.path.join(output_dir, f))
        
        # 测试软件方案
        print("\n2️⃣ 测试软件方案:")
        try:
            # 强制使用软件编码
            ffmpeg_utils.force_software_encoding()
            
            processor.process_video_pipeline(
                output_dir=output_dir,
                interval_seconds=10.0,
                use_hw_accel=False
            )
            
            # 检查结果
            extracted_files = [f for f in os.listdir(output_dir) if f.endswith('.jpg')]
            print(f"✅ 软件方案成功，提取了 {len(extracted_files)} 个关键帧")
            
            if len(extracted_files) > 0:
                return True
            else:
                print("❌ 软件方案也未能提取到关键帧")
                return False
                
        except Exception as e:
            print(f"❌ 软件方案也失败: {str(e)}")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {str(e)}")
        print(f"详细错误信息:\n{traceback.format_exc()}")
        return False
    
    finally:
        # 清理临时文件
        try:
            import shutil
            if output_dir and os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                print(f"🧹 已清理临时目录: {output_dir}")
        except Exception as e:
            print(f"⚠️ 清理临时目录失败: {e}")


def main():
    """主函数"""
    print("🎯 视频关键帧提取兼容性测试工具")
    print("专门用于测试 Windows 系统 FFmpeg 兼容性修复效果")
    
    # 测试 FFmpeg 兼容性
    if not test_ffmpeg_compatibility():
        return
    
    # 获取测试视频路径
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
    else:
        # 尝试找到项目中的测试视频
        possible_paths = [
            "./resource/videos/test.mp4",
            "./storage/videos/test.mp4",
            "./test_video.mp4"
        ]
        
        video_path = None
        for path in possible_paths:
            if os.path.exists(path):
                video_path = path
                break
        
        if not video_path:
            print("\n❌ 未找到测试视频文件")
            print("请提供视频文件路径作为参数:")
            print(f"python {sys.argv[0]} <video_path>")
            return
    
    # 执行测试
    success = test_video_extraction(video_path)
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 测试成功！关键帧提取功能正常工作")
        print("💡 建议：如果之前遇到问题，现在应该已经修复")
    else:
        print("❌ 测试失败！可能需要进一步调试")
        print("💡 建议：")
        print("   1. 检查视频文件是否损坏")
        print("   2. 尝试更新显卡驱动")
        print("   3. 检查 FFmpeg 版本是否过旧")
    print("=" * 60)


if __name__ == "__main__":
    main()

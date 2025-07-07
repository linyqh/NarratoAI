"""
FFmpeg 诊断和配置组件
为用户提供 FFmpeg 兼容性诊断和配置选项
"""

import streamlit as st
import platform
from typing import Dict, Any
from loguru import logger

try:
    from app.utils import ffmpeg_utils
    from app.config.ffmpeg_config import FFmpegConfigManager
except ImportError as e:
    logger.error(f"导入模块失败: {e}")
    ffmpeg_utils = None
    FFmpegConfigManager = None


def show_ffmpeg_diagnostics():
    """显示 FFmpeg 诊断信息"""
    st.subheader("🔧 FFmpeg 兼容性诊断")
    
    if ffmpeg_utils is None or FFmpegConfigManager is None:
        st.error("❌ 无法加载 FFmpeg 工具模块")
        return
    
    # 基础信息
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**系统信息**")
        st.write(f"- 操作系统: {platform.system()} {platform.release()}")
        st.write(f"- 架构: {platform.machine()}")
        st.write(f"- Python: {platform.python_version()}")
    
    with col2:
        st.write("**FFmpeg 状态**")
        
        # 检查 FFmpeg 安装
        if ffmpeg_utils.check_ffmpeg_installation():
            st.success("✅ FFmpeg 已安装")
        else:
            st.error("❌ FFmpeg 未安装或不在 PATH 中")
            st.info("请安装 FFmpeg 并确保其在系统 PATH 中")
            return
    
    # 硬件加速信息
    st.write("**硬件加速检测**")
    
    try:
        hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
        
        if hwaccel_info.get("available", False):
            st.success(f"✅ {hwaccel_info.get('message', '硬件加速可用')}")
            
            # 显示详细信息
            with st.expander("硬件加速详情"):
                st.write(f"- 加速类型: {hwaccel_info.get('type', '未知')}")
                st.write(f"- 编码器: {hwaccel_info.get('encoder', '未知')}")
                st.write(f"- GPU 厂商: {hwaccel_info.get('gpu_vendor', '未知')}")
                st.write(f"- 独立显卡: {'是' if hwaccel_info.get('is_dedicated_gpu', False) else '否'}")
                
                if hwaccel_info.get("tested_methods"):
                    st.write(f"- 测试的方法: {', '.join(hwaccel_info['tested_methods'])}")
        else:
            st.warning(f"⚠️ {hwaccel_info.get('message', '硬件加速不可用')}")
            
    except Exception as e:
        st.error(f"❌ 硬件加速检测失败: {str(e)}")
    
    # 配置文件推荐
    st.write("**推荐配置**")
    
    try:
        recommended_profile = FFmpegConfigManager.get_recommended_profile()
        profile = FFmpegConfigManager.get_profile(recommended_profile)
        
        st.info(f"🎯 推荐配置: **{profile.description}**")
        
        # 显示配置详情
        with st.expander("配置详情"):
            st.write(f"- 配置名称: {profile.name}")
            st.write(f"- 硬件加速: {'启用' if profile.hwaccel_enabled else '禁用'}")
            st.write(f"- 编码器: {profile.encoder}")
            st.write(f"- 质量预设: {profile.quality_preset}")
            st.write(f"- 兼容性等级: {profile.compatibility_level}/5")
            
    except Exception as e:
        st.error(f"❌ 配置推荐失败: {str(e)}")
    
    # 兼容性报告
    if st.button("🔍 生成详细兼容性报告"):
        try:
            report = FFmpegConfigManager.get_compatibility_report()
            
            st.write("**详细兼容性报告**")
            st.json(report)
            
            # 显示建议
            if report.get("suggestions"):
                st.write("**优化建议**")
                for suggestion in report["suggestions"]:
                    st.write(f"- {suggestion}")
                    
        except Exception as e:
            st.error(f"❌ 生成报告失败: {str(e)}")


def show_ffmpeg_settings():
    """显示 FFmpeg 设置选项"""
    st.subheader("⚙️ FFmpeg 设置")
    
    if FFmpegConfigManager is None:
        st.error("❌ 无法加载配置管理器")
        return
    
    # 配置文件选择
    profiles = FFmpegConfigManager.list_profiles()
    
    # 获取当前推荐配置
    try:
        recommended_profile = FFmpegConfigManager.get_recommended_profile()
    except Exception:
        recommended_profile = "universal_software"
    
    # 配置文件选择器
    selected_profile = st.selectbox(
        "选择 FFmpeg 配置文件",
        options=list(profiles.keys()),
        index=list(profiles.keys()).index(recommended_profile) if recommended_profile in profiles else 0,
        format_func=lambda x: f"{profiles[x]} {'(推荐)' if x == recommended_profile else ''}",
        help="不同的配置文件针对不同的硬件和兼容性需求进行了优化"
    )
    
    # 显示选中配置的详情
    if selected_profile:
        profile = FFmpegConfigManager.get_profile(selected_profile)
        
        st.write("**配置详情**")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"- 硬件加速: {'✅ 启用' if profile.hwaccel_enabled else '❌ 禁用'}")
            st.write(f"- 编码器: {profile.encoder}")
            st.write(f"- 质量预设: {profile.quality_preset}")
        
        with col2:
            st.write(f"- 像素格式: {profile.pixel_format}")
            st.write(f"- 兼容性等级: {profile.compatibility_level}/5")
            if profile.additional_args:
                st.write(f"- 额外参数: {' '.join(profile.additional_args)}")
    
    # 高级设置
    with st.expander("🔧 高级设置"):
        st.write("**强制设置选项**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🚫 强制禁用硬件加速"):
                try:
                    ffmpeg_utils.force_software_encoding()
                    st.success("✅ 已强制禁用硬件加速")
                    st.info("这将使用纯软件编码，兼容性最高但性能较低")
                except Exception as e:
                    st.error(f"❌ 操作失败: {str(e)}")
        
        with col2:
            if st.button("🔄 重置硬件加速检测"):
                try:
                    ffmpeg_utils.reset_hwaccel_detection()
                    st.success("✅ 已重置硬件加速检测")
                    st.info("下次使用时将重新检测硬件加速能力")
                except Exception as e:
                    st.error(f"❌ 操作失败: {str(e)}")
    
    # 测试按钮
    st.write("**测试功能**")
    
    if st.button("🧪 测试 FFmpeg 兼容性"):
        with st.spinner("正在测试 FFmpeg 兼容性..."):
            try:
                # 这里可以调用测试脚本
                st.info("请在终端运行 `python test_video_extraction.py <video_path>` 进行完整测试")
                
                # 简单的兼容性测试
                if ffmpeg_utils and ffmpeg_utils.check_ffmpeg_installation():
                    hwaccel_info = ffmpeg_utils.get_ffmpeg_hwaccel_info()
                    if hwaccel_info.get("available"):
                        st.success("✅ 基础兼容性测试通过")
                    else:
                        st.warning("⚠️ 硬件加速不可用，但软件编码应该可以工作")
                else:
                    st.error("❌ FFmpeg 不可用")
                    
            except Exception as e:
                st.error(f"❌ 测试失败: {str(e)}")


def show_troubleshooting_guide():
    """显示故障排除指南"""
    st.subheader("🆘 故障排除指南")
    
    # 常见问题
    st.write("**常见问题及解决方案**")
    
    with st.expander("❌ 关键帧提取失败 - 滤镜链错误"):
        st.write("""
        **问题描述**: 出现 "Impossible to convert between the formats" 错误
        
        **解决方案**:
        1. 在设置中选择 "兼容性配置" 或 "Windows NVIDIA 优化配置"
        2. 点击 "强制禁用硬件加速" 按钮
        3. 重新尝试关键帧提取
        4. 如果仍然失败，请更新显卡驱动程序
        """)
    
    with st.expander("⚠️ 硬件加速不可用"):
        st.write("""
        **可能原因**:
        - 显卡驱动程序过旧
        - FFmpeg 版本不支持当前硬件
        - 系统缺少必要的运行库
        
        **解决方案**:
        1. 更新显卡驱动程序到最新版本
        2. 对于 NVIDIA 用户，安装 CUDA 工具包
        3. 对于 AMD 用户，安装 AMD Media SDK
        4. 使用软件编码作为备用方案
        """)
    
    with st.expander("🐌 处理速度很慢"):
        st.write("""
        **优化建议**:
        1. 启用硬件加速（如果可用）
        2. 选择 "高性能配置"
        3. 降低视频质量设置
        4. 增加关键帧提取间隔
        5. 关闭其他占用 GPU 的程序
        """)
    
    with st.expander("📁 文件权限问题"):
        st.write("""
        **解决方案**:
        1. 确保对输出目录有写入权限
        2. 以管理员身份运行程序（Windows）
        3. 检查磁盘空间是否充足
        4. 避免使用包含特殊字符的文件路径
        """)
    
    # 联系支持
    st.write("**需要更多帮助？**")
    st.info("""
    如果上述解决方案都无法解决您的问题，请：
    1. 运行 `python test_video_extraction.py` 生成详细的测试报告
    2. 记录具体的错误信息和系统环境
    3. 联系技术支持并提供相关信息
    """)


def render_ffmpeg_diagnostics_page():
    """渲染 FFmpeg 诊断页面"""
    st.title("🔧 FFmpeg 诊断与配置")
    
    # 选项卡
    tab1, tab2, tab3 = st.tabs(["🔍 诊断信息", "⚙️ 配置设置", "🆘 故障排除"])
    
    with tab1:
        show_ffmpeg_diagnostics()
    
    with tab2:
        show_ffmpeg_settings()
    
    with tab3:
        show_troubleshooting_guide()


if __name__ == "__main__":
    render_ffmpeg_diagnostics_page()

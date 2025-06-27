"""
FFmpeg 工具模块 - 提供 FFmpeg 相关的工具函数，特别是硬件加速检测
"""
import os
import platform
import subprocess
from typing import Dict, List, Optional, Tuple, Union
from loguru import logger

# 全局变量，存储检测到的硬件加速信息
_FFMPEG_HW_ACCEL_INFO = {
    "available": False,
    "type": None,
    "encoder": None,
    "hwaccel_args": [],
    "message": "",
    "is_dedicated_gpu": False
}


def check_ffmpeg_installation() -> bool:
    """
    检查ffmpeg是否已安装

    Returns:
        bool: 如果安装则返回True，否则返回False
    """
    try:
        # 在Windows系统上使用UTF-8编码
        is_windows = os.name == 'nt'
        if is_windows:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', check=True)
        else:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("ffmpeg未安装或不在系统PATH中，请安装ffmpeg")
        return False


def detect_hardware_acceleration() -> Dict[str, Union[bool, str, List[str], None]]:
    """
    检测系统可用的硬件加速器，并存储结果到全局变量

    Returns:
        Dict: 包含硬件加速信息的字典
    """
    global _FFMPEG_HW_ACCEL_INFO

    # 如果已经检测过，直接返回结果
    if _FFMPEG_HW_ACCEL_INFO["type"] is not None:
        return _FFMPEG_HW_ACCEL_INFO

    # 检查ffmpeg是否已安装
    if not check_ffmpeg_installation():
        _FFMPEG_HW_ACCEL_INFO["message"] = "FFmpeg未安装或不在系统PATH中"
        return _FFMPEG_HW_ACCEL_INFO

    # 检测操作系统
    system = platform.system().lower()
    logger.debug(f"检测硬件加速 - 操作系统: {system}")

    # 获取FFmpeg支持的硬件加速器列表
    try:
        # 在Windows系统上使用UTF-8编码
        is_windows = os.name == 'nt'
        if is_windows:
            hwaccels_cmd = subprocess.run(
                ['ffmpeg', '-hide_banner', '-hwaccels'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', text=True
            )
        else:
            hwaccels_cmd = subprocess.run(
                ['ffmpeg', '-hide_banner', '-hwaccels'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        supported_hwaccels = hwaccels_cmd.stdout.lower()
    except Exception as e:
        logger.error(f"获取FFmpeg硬件加速器列表失败: {str(e)}")
        supported_hwaccels = ""

    # 根据操作系统检测不同的硬件加速器
    if system == 'darwin':  # macOS
        _detect_macos_acceleration(supported_hwaccels)
    elif system == 'windows':  # Windows
        _detect_windows_acceleration(supported_hwaccels)
    elif system == 'linux':  # Linux
        _detect_linux_acceleration(supported_hwaccels)
    else:
        logger.warning(f"不支持的操作系统: {system}")
        _FFMPEG_HW_ACCEL_INFO["message"] = f"不支持的操作系统: {system}"

    # 记录检测结果已经在启动时输出，这里不再重复输出

    return _FFMPEG_HW_ACCEL_INFO


def _detect_macos_acceleration(supported_hwaccels: str) -> None:
    """
    检测macOS系统的硬件加速

    Args:
        supported_hwaccels: FFmpeg支持的硬件加速器列表
    """
    global _FFMPEG_HW_ACCEL_INFO

    if 'videotoolbox' in supported_hwaccels:
        # 测试videotoolbox
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "videotoolbox", "-i", "/dev/null", "-f", "null", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                check=False,
                timeout=10,
            )
            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "videotoolbox"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_videotoolbox"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "videotoolbox"]
                # macOS的Metal GPU加速通常是集成GPU
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = False
                return
        except Exception as e:
            logger.debug(f"测试videotoolbox失败: {str(e)}")

    _FFMPEG_HW_ACCEL_INFO["message"] = "macOS系统未检测到可用的videotoolbox硬件加速"


def _detect_windows_acceleration(supported_hwaccels: str) -> None:
    """
    检测Windows系统的硬件加速

    Args:
        supported_hwaccels: FFmpeg支持的硬件加速器列表
    """
    global _FFMPEG_HW_ACCEL_INFO

    # 在Windows上，首先检查显卡信息
    gpu_info = _get_windows_gpu_info()
    gpu_lower = gpu_info.lower()
    is_nvidia = 'nvidia' in gpu_lower
    is_amd = 'amd' in gpu_lower or 'radeon' in gpu_lower
    is_intel = 'intel' in gpu_lower

    # 尝试检测AMD AMF加速
    if is_amd:
        try:
            encoders_cmd = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )
            if "h264_amf" in encoders_cmd.stdout.lower():
                test_cmd = subprocess.run(
                    [
                        "ffmpeg",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=black:s=16x16",
                        "-c:v",
                        "h264_amf",
                        "-t",
                        "0.1",
                        "-f",
                        "null",
                        "-",
                    ],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    encoding='utf-8',
                    text=True,
                    check=False,
                    timeout=10,
                )
                if test_cmd.returncode == 0:
                    _FFMPEG_HW_ACCEL_INFO["available"] = True
                    _FFMPEG_HW_ACCEL_INFO["type"] = "amf"
                    _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_amf"
                    _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = []
                    _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                    return
        except Exception as e:
            logger.debug(f"测试AMF失败: {str(e)}")

    # 检查是否为Intel集成显卡
    is_intel_integrated = False
    if is_intel and ('hd graphics' in gpu_lower or 'uhd graphics' in gpu_lower):
        logger.info("检测到Intel集成显卡")
        is_intel_integrated = True

    # 检测NVIDIA CUDA支持
    if 'cuda' in supported_hwaccels and is_nvidia:
        # 添加调试日志
        logger.debug(f"Windows检测到NVIDIA显卡，尝试CUDA加速")
        try:
            # 先检查NVENC编码器是否可用，使用UTF-8编码
            encoders_cmd = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )
            has_nvenc = "h264_nvenc" in encoders_cmd.stdout.lower()
            logger.debug(f"NVENC编码器检测结果: {'可用' if has_nvenc else '不可用'}")

            # 测试CUDA硬件加速，使用UTF-8编码
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "cuda", "-i", "NUL", "-f", "null", "-t", "0.1", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )

            # 记录详细的返回信息以便调试
            logger.debug(f"CUDA测试返回码: {test_cmd.returncode}")
            logger.debug(f"CUDA测试错误输出: {test_cmd.stderr[:200]}..." if len(test_cmd.stderr) > 200 else f"CUDA测试错误输出: {test_cmd.stderr}")

            if test_cmd.returncode == 0 or has_nvenc:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "cuda"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_nvenc"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "cuda"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                return

            # 如果上面的测试失败，尝试另一种方式，使用UTF-8编码
            test_cmd2 = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", "NUL", "-f", "null", "-t", "0.1", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )

            if test_cmd2.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "cuda"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_nvenc"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                return
        except Exception as e:
            logger.debug(f"测试CUDA失败: {str(e)}")

    # 检测Intel QSV支持（如果是Intel显卡）
    if 'qsv' in supported_hwaccels and is_intel:
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "qsv", "-i", "/dev/null", "-f", "null", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                check=False,
                timeout=10,
            )
            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "qsv"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_qsv"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "qsv"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = not is_intel_integrated
                return
        except Exception as e:
            logger.debug(f"测试QSV失败: {str(e)}")

    # 检测D3D11VA支持
    if 'd3d11va' in supported_hwaccels:
        logger.debug("Windows尝试D3D11VA加速")
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "d3d11va", "-i", "NUL", "-f", "null", "-t", "0.1", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )

            # 记录详细的返回信息以便调试
            logger.debug(f"D3D11VA测试返回码: {test_cmd.returncode}")

            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "d3d11va"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264"  # D3D11VA只用于解码，编码仍使用软件编码器
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "d3d11va"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = not is_intel_integrated
                return
        except Exception as e:
            logger.debug(f"测试D3D11VA失败: {str(e)}")

    # 检测DXVA2支持
    if 'dxva2' in supported_hwaccels:
        logger.debug("Windows尝试DXVA2加速")
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "dxva2", "-i", "NUL", "-f", "null", "-t", "0.1", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )

            # 记录详细的返回信息以便调试
            logger.debug(f"DXVA2测试返回码: {test_cmd.returncode}")

            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "dxva2"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264"  # DXVA2只用于解码，编码仍使用软件编码器
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "dxva2"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = not is_intel_integrated
                return
        except Exception as e:
            logger.debug(f"测试DXVA2失败: {str(e)}")

    # 如果检测到NVIDIA显卡但前面的测试都失败，尝试直接使用NVENC编码器
    if is_nvidia:
        logger.debug("Windows检测到NVIDIA显卡，尝试直接使用NVENC编码器")
        try:
            # 检查NVENC编码器是否可用，使用UTF-8编码
            encoders_cmd = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=10,
            )

            if "h264_nvenc" in encoders_cmd.stdout.lower():
                logger.debug("NVENC编码器可用，尝试直接使用")
                # 测试NVENC编码器，使用UTF-8编码
                test_cmd = subprocess.run(
                    ["ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30", "-c:v", "h264_nvenc", "-t", "0.1", "-f", "null", "-"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    encoding='utf-8',
                    text=True,
                    check=False,
                    timeout=10,
                )

                logger.debug(f"NVENC编码器测试返回码: {test_cmd.returncode}")

                if test_cmd.returncode == 0:
                    _FFMPEG_HW_ACCEL_INFO["available"] = True
                    _FFMPEG_HW_ACCEL_INFO["type"] = "nvenc"
                    _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_nvenc"
                    _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = []  # 不使用hwaccel参数，直接使用编码器
                    _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                    return
        except Exception as e:
            logger.debug(f"测试NVENC编码器失败: {str(e)}")

    _FFMPEG_HW_ACCEL_INFO["message"] = f"Windows系统未检测到可用的硬件加速，显卡信息: {gpu_info}"


def _detect_linux_acceleration(supported_hwaccels: str) -> None:
    """
    检测Linux系统的硬件加速

    Args:
        supported_hwaccels: FFmpeg支持的硬件加速器列表
    """
    global _FFMPEG_HW_ACCEL_INFO

    # 获取Linux显卡信息
    gpu_info = _get_linux_gpu_info()
    is_nvidia = 'nvidia' in gpu_info.lower()
    is_intel = 'intel' in gpu_info.lower()
    is_amd = 'amd' in gpu_info.lower() or 'radeon' in gpu_info.lower()

    # 检测NVIDIA CUDA支持
    if 'cuda' in supported_hwaccels and is_nvidia:
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "cuda", "-i", "/dev/null", "-f", "null", "-"],
                stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, check=False, timeout=10
            )
            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "cuda"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_nvenc"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "cuda"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                return
        except Exception as e:
            logger.debug(f"测试CUDA失败: {str(e)}")

    # 某些FFmpeg构建可能未在 -hwaccels 中显示 CUDA，但仍支持 NVENC 编码
    if is_nvidia and not _FFMPEG_HW_ACCEL_INFO["available"]:
        try:
            encoders_cmd = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, check=False, timeout=10
            )
            if "h264_nvenc" in encoders_cmd.stdout.lower():
                test_cmd = subprocess.run(
                    [
                        "ffmpeg",
                        "-f",
                        "lavfi",
                        "-i",
                        "nullsrc=s=16x16",
                        "-c:v",
                        "h264_nvenc",
                        "-t",
                        "0.1",
                        "-f",
                        "null",
                        "-",
                    ],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if test_cmd.returncode == 0:
                    _FFMPEG_HW_ACCEL_INFO["available"] = True
                    _FFMPEG_HW_ACCEL_INFO["type"] = "nvenc"
                    _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_nvenc"
                    _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = []
                    _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = True
                    return
        except Exception as e:
            logger.debug(f"测试NVENC编码器失败: {str(e)}")

    # 检测VAAPI支持
    if 'vaapi' in supported_hwaccels:
        # 检查是否存在渲染设备
        render_devices = ['/dev/dri/renderD128', '/dev/dri/renderD129']
        render_device = None
        for device in render_devices:
            if os.path.exists(device):
                render_device = device
                break

        if render_device:
            try:
                test_cmd = subprocess.run(
                    ["ffmpeg", "-hwaccel", "vaapi", "-vaapi_device", render_device,
                     "-i", "/dev/null", "-f", "null", "-"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if test_cmd.returncode == 0:
                    _FFMPEG_HW_ACCEL_INFO["available"] = True
                    _FFMPEG_HW_ACCEL_INFO["type"] = "vaapi"
                    _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_vaapi"
                    _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "vaapi", "-vaapi_device", render_device]
                    # 根据显卡类型判断是否为独立显卡
                    _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = is_nvidia or (is_amd and not is_intel)
                    return
            except Exception as e:
                logger.debug(f"测试VAAPI失败: {str(e)}")

    # 检测Intel QSV支持
    if 'qsv' in supported_hwaccels and is_intel:
        try:
            test_cmd = subprocess.run(
                ["ffmpeg", "-hwaccel", "qsv", "-i", "/dev/null", "-f", "null", "-"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                check=False,
                timeout=10,
            )
            if test_cmd.returncode == 0:
                _FFMPEG_HW_ACCEL_INFO["available"] = True
                _FFMPEG_HW_ACCEL_INFO["type"] = "qsv"
                _FFMPEG_HW_ACCEL_INFO["encoder"] = "h264_qsv"
                _FFMPEG_HW_ACCEL_INFO["hwaccel_args"] = ["-hwaccel", "qsv"]
                _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"] = False  # Intel QSV通常是集成GPU
                return
        except Exception as e:
            logger.debug(f"测试QSV失败: {str(e)}")

    _FFMPEG_HW_ACCEL_INFO["message"] = f"Linux系统未检测到可用的硬件加速，显卡信息: {gpu_info}"


def _get_windows_gpu_info() -> str:
    """
    获取Windows系统的显卡信息

    Returns:
        str: 显卡信息字符串
    """
    try:
        # 使用PowerShell获取更可靠的显卡信息，并使用UTF-8编码
        gpu_info = subprocess.run(
            ['powershell', '-Command', "Get-WmiObject Win32_VideoController | Select-Object Name | Format-List"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            text=True,
            check=False,
            timeout=5,
        )

        # 如果PowerShell失败，尝试使用wmic
        if not gpu_info.stdout.strip():
            gpu_info = subprocess.run(
                ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                text=True,
                check=False,
                timeout=5,
            )

        # 记录详细的显卡信息以便调试
        logger.debug(f"Windows显卡信息: {gpu_info.stdout}")
        return gpu_info.stdout
    except Exception as e:
        logger.warning(f"获取Windows显卡信息失败: {str(e)}")
        return "Unknown GPU"


def _get_linux_gpu_info() -> str:
    """
    获取Linux系统的显卡信息

    Returns:
        str: 显卡信息字符串
    """
    try:
        # 尝试使用lspci命令
        gpu_info = subprocess.run(
            'lspci -v -nn | grep -i "vga\\|display"',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            check=False,
            timeout=5,
        )
        if gpu_info.stdout:
            return gpu_info.stdout

        # 如果lspci命令失败，尝试使用glxinfo
        gpu_info = subprocess.run(
            'glxinfo | grep -i "vendor\\|renderer"',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            check=False,
            timeout=5,
        )
        if gpu_info.stdout:
            return gpu_info.stdout

        return "Unknown GPU"
    except Exception as e:
        logger.warning(f"获取Linux显卡信息失败: {str(e)}")
        return "Unknown GPU"


def get_ffmpeg_hwaccel_args() -> List[str]:
    """
    获取FFmpeg硬件加速参数

    Returns:
        List[str]: FFmpeg硬件加速参数列表
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO["hwaccel_args"]


def get_ffmpeg_hwaccel_type() -> Optional[str]:
    """
    获取FFmpeg硬件加速类型

    Returns:
        Optional[str]: 硬件加速类型，如果不支持则返回None
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO["type"] if _FFMPEG_HW_ACCEL_INFO["available"] else None


def get_ffmpeg_hwaccel_encoder() -> Optional[str]:
    """
    获取FFmpeg硬件加速编码器

    Returns:
        Optional[str]: 硬件加速编码器，如果不支持则返回None
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO["encoder"] if _FFMPEG_HW_ACCEL_INFO["available"] else None


def get_ffmpeg_hwaccel_info() -> Dict[str, Union[bool, str, List[str], None]]:
    """
    获取FFmpeg硬件加速信息

    Returns:
        Dict: 包含硬件加速信息的字典
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO


def is_ffmpeg_hwaccel_available() -> bool:
    """
    检查是否有可用的FFmpeg硬件加速

    Returns:
        bool: 如果有可用的硬件加速则返回True，否则返回False
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO["available"]


def is_dedicated_gpu() -> bool:
    """
    检查是否使用独立显卡进行硬件加速

    Returns:
        bool: 如果使用独立显卡则返回True，否则返回False
    """
    # 如果还没有检测过，先进行检测
    if _FFMPEG_HW_ACCEL_INFO["type"] is None:
        detect_hardware_acceleration()

    return _FFMPEG_HW_ACCEL_INFO["is_dedicated_gpu"]

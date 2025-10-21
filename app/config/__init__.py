import os
import sys

from loguru import logger

from app.config import config
from app.utils import utils


def __init_logger():
    # _log_file = utils.storage_dir("logs/server.log")
    _lvl = config.log_level
    root_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    )

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    def log_filter(record):
        """过滤不必要的日志消息"""
        # 过滤掉模板注册等 DEBUG 级别的噪音日志
        ignore_patterns = [
            "已注册模板过滤器",
            "已注册提示词",
            "注册视觉模型提供商",
            "注册文本模型提供商",
            "LLM服务提供商注册",
            "FFmpeg支持的硬件加速器",
            "硬件加速测试优先级",
            "硬件加速方法",
        ]

        # 如果是 DEBUG 级别且包含过滤模式，则不显示
        if record["level"].name == "DEBUG":
            return not any(pattern in record["message"] for pattern in ignore_patterns)

        return True

    logger.remove()

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
        filter=log_filter
    )

    # logger.add(
    #     _log_file,
    #     level=_lvl,
    #     format=format_record,
    #     rotation="00:00",
    #     retention="3 days",
    #     backtrace=True,
    #     diagnose=True,
    #     enqueue=True,
    # )


__init_logger()

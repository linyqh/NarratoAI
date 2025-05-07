# import psutil
import os
from loguru import logger

class PerformanceMonitor:
    @staticmethod
    def monitor_memory():
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        logger.debug(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")
        
        # 延迟导入torch并检查CUDA
        try:
            import torch
            if torch.cuda.is_available():
                gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
                logger.debug(f"GPU Memory usage: {gpu_memory:.2f} MB")
        except (ImportError, RuntimeError) as e:
            # 无法导入torch或触发CUDA相关错误时，静默处理
            logger.debug(f"无法获取GPU内存信息: {e}")
    
    @staticmethod
    def cleanup_resources():
        # 延迟导入torch并清理CUDA
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("CUDA缓存已清理")
        except (ImportError, RuntimeError) as e:
            # 无法导入torch或触发CUDA相关错误时，静默处理
            logger.debug(f"无法清理CUDA资源: {e}")
        
        import gc
        gc.collect()
        
        # 仅报告进程内存，不尝试获取GPU内存
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logger.debug(f"Memory usage after cleanup: {memory_info.rss / 1024 / 1024:.2f} MB")

def monitor_performance(func):
    """性能监控装饰器"""
    def wrapper(*args, **kwargs):
        try:
            PerformanceMonitor.monitor_memory()
            result = func(*args, **kwargs)
            return result
        finally:
            PerformanceMonitor.cleanup_resources()
    return wrapper
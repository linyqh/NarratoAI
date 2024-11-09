import psutil
import os
from loguru import logger
import torch

class PerformanceMonitor:
    @staticmethod
    def monitor_memory():
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        logger.debug(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")
        
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
            logger.debug(f"GPU Memory usage: {gpu_memory:.2f} MB")
    
    @staticmethod
    def cleanup_resources():
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        import gc
        gc.collect()
        
        PerformanceMonitor.monitor_memory()

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
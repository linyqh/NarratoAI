import time
from loguru import logger

try:
    import psutil
    ENABLE_PERFORMANCE_MONITORING = True
except ImportError:
    ENABLE_PERFORMANCE_MONITORING = False
    logger.warning("psutil not installed. Performance monitoring is disabled.")

def monitor_performance():
    if not ENABLE_PERFORMANCE_MONITORING:
        return {'execution_time': 0, 'memory_usage': 0}
    
    start_time = time.time()
    try:
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
    except:
        memory_usage = 0
    
    return {
        'execution_time': time.time() - start_time,
        'memory_usage': memory_usage
    } 
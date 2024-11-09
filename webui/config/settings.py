import os
import tomli
from loguru import logger
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class WebUIConfig:
    """WebUI配置类"""
    # UI配置
    ui: Dict[str, Any] = None
    # 代理配置
    proxy: Dict[str, str] = None
    # 应用配置
    app: Dict[str, Any] = None
    # Azure配置
    azure: Dict[str, str] = None
    # 项目版本
    project_version: str = "0.1.0"
    # 项目根目录
    root_dir: str = None
    # Gemini API Key
    gemini_api_key: str = ""
    # 每批处理的图片数量
    vision_batch_size: int = 5
    # 提示词
    vision_prompt: str = """..."""
    # Narrato API 配置
    narrato_api_url: str = "http://127.0.0.1:8000/api/v1/video/analyze"
    narrato_api_key: str = ""
    narrato_batch_size: int = 10
    narrato_vision_model: str = "gemini-1.5-flash"
    narrato_llm_model: str = "qwen-plus"
    
    def __post_init__(self):
        """初始化默认值"""
        self.ui = self.ui or {}
        self.proxy = self.proxy or {}
        self.app = self.app or {}
        self.azure = self.azure or {}
        self.root_dir = self.root_dir or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def load_config(config_path: Optional[str] = None) -> WebUIConfig:
    """加载配置文件
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
    Returns:
        WebUIConfig: 配置对象
    """
    try:
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                ".streamlit",
                "webui.toml"
            )
        
        # 如果配置文件不存在，使用示例配置
        if not os.path.exists(config_path):
            example_config = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config.example.toml"
            )
            if os.path.exists(example_config):
                config_path = example_config
            else:
                logger.warning(f"配置文件不存在: {config_path}")
                return WebUIConfig()
        
        # 读取配置文件
        with open(config_path, "rb") as f:
            config_dict = tomli.load(f)
            
        # 创建配置对象
        config = WebUIConfig(
            ui=config_dict.get("ui", {}),
            proxy=config_dict.get("proxy", {}),
            app=config_dict.get("app", {}),
            azure=config_dict.get("azure", {}),
            project_version=config_dict.get("project_version", "0.1.0")
        )
        
        return config
    
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return WebUIConfig()

def save_config(config: WebUIConfig, config_path: Optional[str] = None) -> bool:
    """保存配置到文件
    Args:
        config: 配置对象
        config_path: 配置文件路径，如果为None则使用默认路径
    Returns:
        bool: 是否保存成功
    """
    try:
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                ".streamlit",
                "webui.toml"
            )
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 转换为字典
        config_dict = {
            "ui": config.ui,
            "proxy": config.proxy,
            "app": config.app,
            "azure": config.azure,
            "project_version": config.project_version
        }
        
        # 保存配置
        with open(config_path, "w", encoding="utf-8") as f:
            import tomli_w
            tomli_w.dump(config_dict, f)
        
        return True
    
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False

def get_config() -> WebUIConfig:
    """获取全局配置对象
    Returns:
        WebUIConfig: 配置对象
    """
    if not hasattr(get_config, "_config"):
        get_config._config = load_config()
    return get_config._config

def update_config(config_dict: Dict[str, Any]) -> bool:
    """更新配置
    Args:
        config_dict: 配置字典
    Returns:
        bool: 是否更新成功
    """
    try:
        config = get_config()
        
        # 更新配置
        if "ui" in config_dict:
            config.ui.update(config_dict["ui"])
        if "proxy" in config_dict:
            config.proxy.update(config_dict["proxy"])
        if "app" in config_dict:
            config.app.update(config_dict["app"])
        if "azure" in config_dict:
            config.azure.update(config_dict["azure"])
        if "project_version" in config_dict:
            config.project_version = config_dict["project_version"]
        
        # 保存配置
        return save_config(config)
    
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return False

# 导出全局配置对象
config = get_config() 
import logging
from typing import List, Dict, Any, Optional
from app.utils import gemini_analyzer, qwenvl_analyzer

logger = logging.getLogger(__name__)

class VisionAnalyzer:
    def __init__(self):
        self.provider = None
        self.api_key = None
        self.model = None
        self.base_url = None
        self.analyzer = None
        
    def initialize_gemini(self, api_key: str, model: str, base_url: str) -> None:
        """
        初始化Gemini视觉分析器
        
        Args:
            api_key: Gemini API密钥
            model: 模型名称
            base_url: API基础URL
        """
        self.provider = 'gemini'
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.analyzer = gemini_analyzer.VisionAnalyzer(
            model_name=model,
            api_key=api_key
        )

    def initialize_qwenvl(self, api_key: str, model: str, base_url: str) -> None:
        """
        初始化QwenVL视觉分析器
        
        Args:
            api_key: 阿里云API密钥
            model: 模型名称
            base_url: API基础URL
        """
        self.provider = 'qwenvl'
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.analyzer = qwenvl_analyzer.QwenAnalyzer(
            model_name=model,
            api_key=api_key
        )
        
    async def analyze_images(self, images: List[str], prompt: str, batch_size: int = 5) -> Dict[str, Any]:
        """
        分析图片内容
        
        Args:
            images: 图片路径列表
            prompt: 分析提示词
            batch_size: 每批处理的图片数量，默认为5
            
        Returns:
            Dict: 分析结果
        """
        if not self.analyzer:
            raise ValueError("未初始化视觉分析器")
            
        return await self.analyzer.analyze_images(
            images=images,
            prompt=prompt,
            batch_size=batch_size
        )

def create_vision_analyzer(provider: str, **kwargs) -> VisionAnalyzer:
    """
    创建视觉分析器实例
    
    Args:
        provider: 提供商名称 ('gemini' 或 'qwenvl')
        **kwargs: 提供商特定的配置参数
        
    Returns:
        VisionAnalyzer: 配置好的视觉分析器实例
    """
    analyzer = VisionAnalyzer()
    
    if provider.lower() == 'gemini':
        analyzer.initialize_gemini(
            api_key=kwargs.get('api_key'),
            model=kwargs.get('model'),
            base_url=kwargs.get('base_url')
        )
    elif provider.lower() == 'qwenvl':
        analyzer.initialize_qwenvl(
            api_key=kwargs.get('api_key'),
            model=kwargs.get('model'),
            base_url=kwargs.get('base_url')
        )
    else:
        raise ValueError(f"不支持的视觉分析提供商: {provider}")
        
    return analyzer
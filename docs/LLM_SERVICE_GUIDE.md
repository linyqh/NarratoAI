# NarratoAI 大模型服务使用指南

## 📖 概述

NarratoAI 项目已完成大模型服务的全面重构，提供了统一、模块化、可扩展的大模型集成架构。新架构支持多种大模型供应商，具有严格的输出格式验证和完善的错误处理机制。

## 🏗️ 架构概览

### 核心组件

```
app/services/llm/
├── __init__.py              # 模块入口
├── base.py                  # 抽象基类
├── manager.py               # 服务管理器
├── unified_service.py       # 统一服务接口
├── validators.py            # 输出格式验证器
├── exceptions.py            # 异常类定义
├── migration_adapter.py     # 迁移适配器
├── config_validator.py      # 配置验证器
├── test_llm_service.py      # 测试脚本
└── providers/               # 提供商实现
    ├── __init__.py
    ├── gemini_provider.py
    ├── gemini_openai_provider.py
    ├── openai_provider.py
    ├── qwen_provider.py
    ├── deepseek_provider.py
    └── siliconflow_provider.py
```

### 支持的供应商

#### 视觉模型供应商
- **Gemini** (原生API + OpenAI兼容)
- **QwenVL** (通义千问视觉)
- **Siliconflow** (硅基流动)

#### 文本生成模型供应商
- **OpenAI** (标准OpenAI API)
- **Gemini** (原生API + OpenAI兼容)
- **DeepSeek** (深度求索)
- **Qwen** (通义千问)
- **Siliconflow** (硅基流动)

## ⚙️ 配置说明

### 配置文件格式

在 `config.toml` 中配置大模型服务：

```toml
[app]
    # 视觉模型提供商配置
    vision_llm_provider = "gemini"
    
    # Gemini 视觉模型
    vision_gemini_api_key = "your_gemini_api_key"
    vision_gemini_model_name = "gemini-2.0-flash-lite"
    vision_gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    # QwenVL 视觉模型
    vision_qwenvl_api_key = "your_qwen_api_key"
    vision_qwenvl_model_name = "qwen2.5-vl-32b-instruct"
    vision_qwenvl_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    # 文本模型提供商配置
    text_llm_provider = "openai"
    
    # OpenAI 文本模型
    text_openai_api_key = "your_openai_api_key"
    text_openai_model_name = "gpt-4o-mini"
    text_openai_base_url = "https://api.openai.com/v1"
    
    # DeepSeek 文本模型
    text_deepseek_api_key = "your_deepseek_api_key"
    text_deepseek_model_name = "deepseek-chat"
    text_deepseek_base_url = "https://api.deepseek.com"
```

### 配置验证

使用配置验证器检查配置是否正确：

```python
from app.services.llm.config_validator import LLMConfigValidator

# 验证所有配置
results = LLMConfigValidator.validate_all_configs()

# 打印验证报告
LLMConfigValidator.print_validation_report(results)

# 获取配置建议
suggestions = LLMConfigValidator.get_config_suggestions()
```

## 🚀 使用方法

### 1. 统一服务接口（推荐）

```python
from app.services.llm.unified_service import UnifiedLLMService

# 图片分析
results = await UnifiedLLMService.analyze_images(
    images=["path/to/image1.jpg", "path/to/image2.jpg"],
    prompt="请描述这些图片的内容",
    provider="gemini",  # 可选，不指定则使用配置中的默认值
    batch_size=10
)

# 文本生成
text = await UnifiedLLMService.generate_text(
    prompt="请介绍人工智能的发展历史",
    system_prompt="你是一个专业的AI专家",
    provider="openai",  # 可选
    temperature=0.7,
    response_format="json"  # 可选，支持JSON格式输出
)

# 解说文案生成（带验证）
narration_items = await UnifiedLLMService.generate_narration_script(
    prompt="根据视频内容生成解说文案...",
    validate_output=True  # 自动验证输出格式
)

# 字幕分析
analysis = await UnifiedLLMService.analyze_subtitle(
    subtitle_content="字幕内容...",
    validate_output=True
)
```

### 2. 直接使用服务管理器

```python
from app.services.llm.manager import LLMServiceManager

# 获取视觉模型提供商
vision_provider = LLMServiceManager.get_vision_provider("gemini")
results = await vision_provider.analyze_images(images, prompt)

# 获取文本模型提供商
text_provider = LLMServiceManager.get_text_provider("openai")
text = await text_provider.generate_text(prompt)
```

### 3. 迁移适配器（向后兼容）

```python
from app.services.llm.migration_adapter import create_vision_analyzer

# 兼容旧的接口
analyzer = create_vision_analyzer("gemini", api_key, model, base_url)
results = await analyzer.analyze_images(images, prompt)
```

## 🔍 输出格式验证

### 解说文案验证

```python
from app.services.llm.validators import OutputValidator

# 验证解说文案格式
try:
    narration_items = OutputValidator.validate_narration_script(output)
    print(f"验证成功，共 {len(narration_items)} 个片段")
except ValidationError as e:
    print(f"验证失败: {e.message}")
```

### JSON输出验证

```python
# 验证JSON格式
try:
    data = OutputValidator.validate_json_output(output)
    print("JSON格式验证成功")
except ValidationError as e:
    print(f"JSON验证失败: {e.message}")
```

## 🧪 测试和调试

### 运行测试脚本

```bash
# 运行完整的LLM服务测试
python app/services/llm/test_llm_service.py
```

测试脚本会验证：
- 配置有效性
- 提供商信息获取
- 文本生成功能
- JSON格式生成
- 字幕分析功能
- 解说文案生成功能

### 调试技巧

1. **启用详细日志**：
```python
from loguru import logger
logger.add("llm_service.log", level="DEBUG")
```

2. **清空提供商缓存**：
```python
UnifiedLLMService.clear_cache()
```

3. **检查提供商信息**：
```python
info = UnifiedLLMService.get_provider_info()
print(info)
```

## ⚠️ 注意事项

### 1. API密钥安全
- 不要在代码中硬编码API密钥
- 使用环境变量或配置文件管理密钥
- 定期轮换API密钥

### 2. 错误处理
- 所有LLM服务调用都应该包装在try-catch中
- 使用适当的异常类型进行错误处理
- 实现重试机制处理临时性错误

### 3. 性能优化
- 合理设置批处理大小
- 使用缓存避免重复调用
- 监控API调用频率和成本

### 4. 模型选择
- 根据任务类型选择合适的模型
- 考虑成本和性能的平衡
- 定期更新到最新的模型版本

## 🔧 扩展新供应商

### 1. 创建提供商类

```python
# app/services/llm/providers/new_provider.py
from ..base import TextModelProvider

class NewTextProvider(TextModelProvider):
    @property
    def provider_name(self) -> str:
        return "new_provider"
    
    @property
    def supported_models(self) -> List[str]:
        return ["model-1", "model-2"]
    
    async def generate_text(self, prompt: str, **kwargs) -> str:
        # 实现具体的API调用逻辑
        pass
```

### 2. 注册提供商

```python
# app/services/llm/providers/__init__.py
from .new_provider import NewTextProvider

LLMServiceManager.register_text_provider('new_provider', NewTextProvider)
```

### 3. 添加配置支持

```toml
# config.toml
text_new_provider_api_key = "your_api_key"
text_new_provider_model_name = "model-1"
text_new_provider_base_url = "https://api.newprovider.com/v1"
```

## 📞 技术支持

如果在使用过程中遇到问题：

1. 首先运行测试脚本检查配置
2. 查看日志文件了解详细错误信息
3. 检查API密钥和网络连接
4. 参考本文档的故障排除部分

---

*最后更新: 2025-01-07*

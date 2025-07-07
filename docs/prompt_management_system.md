# 提示词管理系统文档

## 概述

本项目实现了统一的提示词管理系统，用于集中管理三个核心功能的提示词：
- **纪录片解说** - 视频帧分析和解说文案生成
- **短剧混剪** - 字幕分析和爆点提取
- **短剧解说** - 剧情分析和解说脚本生成

## 系统架构

```
app/services/prompts/
├── __init__.py                 # 模块初始化
├── base.py                     # 基础提示词类
├── manager.py                  # 提示词管理器
├── registry.py                 # 提示词注册机制
├── template.py                 # 模板渲染引擎
├── validators.py               # 输出验证器
├── exceptions.py               # 异常定义
├── documentary/                # 纪录片解说提示词
│   ├── __init__.py
│   ├── frame_analysis.py       # 视频帧分析
│   └── narration_generation.py # 解说文案生成
├── short_drama_editing/        # 短剧混剪提示词
│   ├── __init__.py
│   ├── subtitle_analysis.py    # 字幕分析
│   └── plot_extraction.py      # 爆点提取
└── short_drama_narration/      # 短剧解说提示词
    ├── __init__.py
    ├── plot_analysis.py        # 剧情分析
    └── script_generation.py    # 解说脚本生成
```

## 核心特性

### 1. 统一管理
- 所有提示词集中在 `app/services/prompts/` 模块中
- 按功能模块分类组织
- 支持版本控制和回滚

### 2. 模型类型适配
- **TextPrompt**: 文本模型专用
- **VisionPrompt**: 视觉模型专用
- **ParameterizedPrompt**: 支持参数化

### 3. 参数化支持
- 动态参数替换
- 参数验证
- 模板渲染

### 4. 输出验证
- 严格的JSON格式验证
- 特定业务场景验证（解说文案、剧情分析等）
- 自定义验证规则

## 使用方法

### 基本用法

```python
from app.services.prompts import PromptManager

# 获取纪录片解说的视频帧分析提示词
prompt = PromptManager.get_prompt(
    category="documentary",
    name="frame_analysis",
    parameters={
        "video_theme": "荒野建造",
        "custom_instructions": "请特别关注建造过程的细节"
    }
)

# 获取短剧解说的剧情分析提示词
prompt = PromptManager.get_prompt(
    category="short_drama_narration", 
    name="plot_analysis",
    parameters={"subtitle_content": "字幕内容..."}
)
```

### 高级功能

```python
# 搜索提示词
results = PromptManager.search_prompts(
    keyword="分析",
    model_type=ModelType.TEXT
)

# 获取提示词详细信息
info = PromptManager.get_prompt_info(
    category="documentary",
    name="narration_generation"
)

# 验证输出
validated_data = PromptManager.validate_output(
    output=llm_response,
    category="documentary",
    name="narration_generation"
)
```

## 已注册的提示词

### 纪录片解说 (documentary)
- `frame_analysis` - 视频帧分析提示词
- `narration_generation` - 解说文案生成提示词

### 短剧混剪 (short_drama_editing)
- `subtitle_analysis` - 字幕分析提示词
- `plot_extraction` - 爆点提取提示词

### 短剧解说 (short_drama_narration)
- `plot_analysis` - 剧情分析提示词
- `script_generation` - 解说脚本生成提示词

## 迁移指南

### 旧代码迁移

**之前的用法：**
```python
from app.services.SDE.prompt import subtitle_plot_analysis_v1
prompt = subtitle_plot_analysis_v1
```

**新的用法：**
```python
from app.services.prompts import PromptManager
prompt = PromptManager.get_prompt(
    category="short_drama_narration",
    name="plot_analysis",
    parameters={"subtitle_content": content}
)
```

### 已更新的文件
- `app/services/SDE/short_drama_explanation.py`
- `app/services/SDP/utils/step1_subtitle_analyzer_openai.py`
- `app/services/generate_narration_script.py`

## 扩展指南

### 添加新提示词

1. 在相应分类目录下创建新的提示词类：

```python
from ..base import TextPrompt, PromptMetadata, ModelType, OutputFormat

class NewPrompt(TextPrompt):
    def __init__(self):
        metadata = PromptMetadata(
            name="new_prompt",
            category="your_category",
            version="v1.0",
            description="提示词描述",
            model_type=ModelType.TEXT,
            output_format=OutputFormat.JSON,
            parameters=["param1", "param2"]
        )
        super().__init__(metadata)
        
    def get_template(self) -> str:
        return "您的提示词模板内容..."
```

2. 在 `__init__.py` 中注册：

```python
def register_prompts():
    new_prompt = NewPrompt()
    PromptManager.register_prompt(new_prompt, is_default=True)
```

### 添加新分类

1. 创建新的分类目录
2. 实现提示词类
3. 在主模块的 `__init__.py` 中导入并注册

## 测试

运行测试脚本验证系统功能：

```bash
python test_prompt_system.py
```

## 注意事项

1. **模板参数**: 使用 `${parameter_name}` 格式
2. **JSON格式**: 模板中的JSON示例使用标准格式 `{` 和 `}`，不要使用双大括号
3. **参数验证**: 必需参数会自动验证
4. **版本管理**: 支持多版本共存，默认使用最新版本
5. **输出验证**: 建议对LLM输出进行验证以确保格式正确
6. **JSON解析**: 系统提供强大的JSON解析兼容性，自动处理各种格式问题

## JSON解析优化

系统提供了强大的JSON解析兼容性，能够处理LLM生成的各种格式问题：

### 支持的格式修复

1. **双大括号修复**: 自动将 `{{` 和 `}}` 转换为标准的 `{` 和 `}`
2. **代码块提取**: 自动从 ````json` 代码块中提取JSON内容
3. **额外文本处理**: 自动提取大括号包围的JSON内容，忽略前后的额外文本
4. **尾随逗号修复**: 自动移除对象和数组末尾的多余逗号
5. **注释移除**: 自动移除 `//` 和 `#` 注释
6. **引号修复**: 自动修复单引号和缺失的属性名引号

### 解析策略

系统采用多重解析策略，按优先级依次尝试：

```python
strategies = [
    ("直接解析", lambda s: json.loads(s)),
    ("修复双大括号", _fix_double_braces),
    ("提取代码块", _extract_code_block),
    ("提取大括号内容", _extract_braces_content),
    ("修复常见格式问题", _fix_common_json_issues),
    ("修复引号问题", _fix_quote_issues),
    ("修复尾随逗号", _fix_trailing_commas),
    ("强制修复", _force_fix_json),
]
```

### 使用示例

```python
from webui.tools.generate_short_summary import parse_and_fix_json

# 处理双大括号JSON
json_str = '{{ "items": [{{ "_id": 1, "name": "test" }}] }}'
result = parse_and_fix_json(json_str)  # 自动修复并解析

# 处理有额外文本的JSON
json_str = '这是一些文本\n{"items": []}\n更多文本'
result = parse_and_fix_json(json_str)  # 自动提取JSON部分
```

## 性能优化

- 提示词模板会被缓存
- 支持批量操作
- 异步渲染支持（未来版本）
- JSON解析采用多策略优化，确保高成功率

## 故障排除

### 常见问题

1. **模板渲染错误**: 检查参数名称和格式
2. **提示词未找到**: 确认分类、名称和版本正确
3. **输出验证失败**: 检查LLM输出格式是否符合要求

### 日志调试

系统使用 loguru 记录详细日志，可通过日志排查问题：

```python
from loguru import logger
logger.debug("调试信息")
```

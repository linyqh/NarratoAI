# 短剧解说功能优化说明

## 概述

本次优化解决了短剧解说功能中原始字幕信息缺失的问题，确保生成的解说文案与视频时间戳正确匹配。

## 问题分析

### 原始问题
1. **参数化调用错误**：`SubtitleAnalyzer` 在获取 `PlotAnalysisPrompt` 时传入空参数字典，导致模板中的占位符无法被正确替换
2. **数据传递链断裂**：解说脚本生成阶段无法直接访问原始字幕的时间戳信息
3. **时间戳信息丢失**：生成的解说文案与视频画面时间戳不匹配

### 根本原因
- 提示词模板期望参数化方式接收字幕内容，但实际使用了简单的字符串拼接
- 解说脚本生成时只能访问剧情分析结果，无法获取原始字幕的准确时间戳

## 解决方案

### 1. 修复参数化调用问题

**修改文件**: `app/services/SDE/short_drama_explanation.py`

**修改内容**:
```python
# 修改前
self.prompt_template = PromptManager.get_prompt(
    category="short_drama_narration",
    name="plot_analysis",
    parameters={}  # 空参数字典
)
prompt = f"{self.prompt_template}\n\n{subtitle_content}"  # 字符串拼接

# 修改后
if self.custom_prompt:
    prompt = f"{self.custom_prompt}\n\n{subtitle_content}"
else:
    prompt = PromptManager.get_prompt(
        category="short_drama_narration",
        name="plot_analysis",
        parameters={"subtitle_content": subtitle_content}  # 正确传入参数
    )
```

### 2. 增强解说脚本生成的数据访问

**修改文件**: `app/services/prompts/short_drama_narration/script_generation.py`

**修改内容**:
```python
# 添加 subtitle_content 参数支持
parameters=["drama_name", "plot_analysis", "subtitle_content"]

# 优化提示词模板，添加原始字幕信息
template = """
下面<plot>中的内容是短剧的剧情概述：
<plot>
${plot_analysis}
</plot>

下面<subtitles>中的内容是短剧的原始字幕（包含准确的时间戳信息）：
<subtitles>
${subtitle_content}
</subtitles>

重要要求：
6. **时间戳必须严格基于<subtitles>中的原始时间戳**，确保与视频画面精确匹配
11. **确保每个解说片段的时间戳都能在原始字幕中找到对应的时间范围**
"""
```

### 3. 更新方法签名和调用

**修改内容**:
```python
# 方法签名更新
def generate_narration_script(
    self, 
    short_name: str, 
    plot_analysis: str, 
    subtitle_content: str = "",  # 新增参数
    temperature: float = 0.7
) -> Dict[str, Any]:

# 调用时传入原始字幕内容
prompt = PromptManager.get_prompt(
    category="short_drama_narration",
    name="script_generation",
    parameters={
        "drama_name": short_name,
        "plot_analysis": plot_analysis,
        "subtitle_content": subtitle_content  # 传入原始字幕
    }
)
```

## 使用方法

### 基本用法

```python
from app.services.SDE.short_drama_explanation import analyze_subtitle, generate_narration_script

# 1. 分析字幕
analysis_result = analyze_subtitle(
    subtitle_file_path="path/to/subtitle.srt",
    api_key="your_api_key",
    model="your_model",
    base_url="your_base_url"
)

# 2. 读取原始字幕内容
with open("path/to/subtitle.srt", 'r', encoding='utf-8') as f:
    subtitle_content = f.read()

# 3. 生成解说脚本（现在包含原始字幕信息）
narration_result = generate_narration_script(
    short_name="短剧名称",
    plot_analysis=analysis_result["analysis"],
    subtitle_content=subtitle_content,  # 传入原始字幕内容
    api_key="your_api_key",
    model="your_model",
    base_url="your_base_url"
)
```

### 完整示例

```python
# 完整的短剧解说生成流程
subtitle_path = "path/to/your/subtitle.srt"

# 步骤1：分析字幕
analysis_result = analyze_subtitle(
    subtitle_file_path=subtitle_path,
    api_key="your_api_key",
    model="gemini-2.0-flash",
    base_url="https://api.narratoai.cn/v1/chat/completions",
    save_result=True
)

if analysis_result["status"] == "success":
    # 步骤2：读取原始字幕内容
    with open(subtitle_path, 'r', encoding='utf-8') as f:
        subtitle_content = f.read()
    
    # 步骤3：生成解说脚本
    narration_result = generate_narration_script(
        short_name="我的短剧",
        plot_analysis=analysis_result["analysis"],
        subtitle_content=subtitle_content,  # 关键：传入原始字幕
        api_key="your_api_key",
        model="gemini-2.0-flash",
        base_url="https://api.narratoai.cn/v1/chat/completions",
        save_result=True
    )
    
    if narration_result["status"] == "success":
        print("解说脚本生成成功！")
        print(narration_result["narration_script"])
```

## 优化效果

### 修改前
- ❌ 字幕内容无法正确嵌入提示词
- ❌ 解说脚本生成时缺少原始时间戳信息
- ❌ 生成的时间戳可能不准确或缺失

### 修改后
- ✅ 字幕内容正确嵌入到剧情分析提示词中
- ✅ 解说脚本生成时可访问完整的原始字幕信息
- ✅ 生成的解说文案时间戳与视频画面精确匹配
- ✅ 保持时间连续性和逻辑顺序
- ✅ 支持时间片段的合理拆分

## 测试验证

运行测试脚本验证修改效果：

```bash
python3 test_short_drama_narration.py
```

测试覆盖：
1. ✅ 剧情分析提示词参数化功能
2. ✅ 解说脚本生成提示词参数化功能  
3. ✅ SubtitleAnalyzer集成功能

## 注意事项

1. **向后兼容性**：修改保持了原有API的向后兼容性
2. **参数传递**：确保在调用 `generate_narration_script` 时传入 `subtitle_content` 参数
3. **时间戳准确性**：生成的解说文案时间戳现在严格基于原始字幕
4. **模块化设计**：保持了提示词管理系统的模块化架构

## 相关文件

- `app/services/SDE/short_drama_explanation.py` - 主要功能实现
- `app/services/prompts/short_drama_narration/plot_analysis.py` - 剧情分析提示词
- `app/services/prompts/short_drama_narration/script_generation.py` - 解说脚本生成提示词
- `test_short_drama_narration.py` - 测试脚本

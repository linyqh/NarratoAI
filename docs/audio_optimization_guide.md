# 音频音量平衡优化指南

## 问题描述

在视频剪辑后台任务中，经常出现视频原声音量比TTS生成的解说声音音量小很多的问题。即使设置了视频原声为1.0，解说音量为0.7，原声依然听起来比较小。

## 原因分析

1. **音频响度差异**：TTS生成的音频通常具有较高且一致的响度，而视频原声的音量可能本身就比较低，或者动态范围较大。

2. **缺乏音频标准化**：之前的代码只是简单地通过乘法器调整音量，没有进行音频响度分析和标准化处理。

3. **音频混合方式**：使用 `CompositeAudioClip` 进行音频混合时，不同音频轨道的响度差异会被保留。

## 解决方案

### 1. 音频标准化工具 (`audio_normalizer.py`)

实现了 `AudioNormalizer` 类，提供以下功能：

- **LUFS响度分析**：使用FFmpeg的loudnorm滤镜分析音频的LUFS响度
- **RMS音量计算**：作为LUFS分析的备用方案
- **音频标准化**：将音频标准化到目标响度
- **智能音量调整**：分析TTS和原声的响度差异，计算合适的音量调整系数

### 2. 音频配置管理 (`audio_config.py`)

实现了 `AudioConfig` 类，提供：

- **默认音量配置**：优化后的默认音量设置
- **视频类型配置**：针对不同类型视频的音量配置
- **预设配置文件**：balanced、voice_focused、original_focused等
- **内容类型推荐**：根据内容类型推荐音量设置

### 3. 智能音量调整

在 `generate_video.py` 中集成了智能音量调整功能：

- 自动分析TTS和原声的响度差异
- 计算合适的音量调整系数
- 保留用户设置的相对比例
- 限制调整范围，避免过度调整

## 配置更新

### 默认音量设置

```python
# 原来的设置
ORIGINAL_VOLUME = 0.7

# 优化后的设置
ORIGINAL_VOLUME = 1.2  # 提高原声音量
MAX_VOLUME = 2.0       # 允许原声音量超过1.0
```

### 推荐音量配置

```python
# 混合内容（默认）
'mixed': {
    'tts_volume': 0.8,
    'original_volume': 1.3,
    'bgm_volume': 0.3,
}

# 原声为主的内容
'original_heavy': {
    'tts_volume': 0.6,
    'original_volume': 1.6,
    'bgm_volume': 0.1,
}
```

## 使用方法

### 1. 自动优化（推荐）

系统会自动应用优化的音量配置：

```python
# 在 task.py 中自动应用
optimized_volumes = get_recommended_volumes_for_content('mixed')
```

### 2. 手动配置

可以通过配置文件或参数手动设置：

```python
# 应用预设配置文件
volumes = AudioConfig.apply_volume_profile('original_focused')

# 根据视频类型获取配置
volumes = AudioConfig.get_optimized_volumes('entertainment')
```

### 3. 智能分析

启用智能音量分析（默认开启）：

```python
# 在 schema.py 中控制
ENABLE_SMART_VOLUME = True
```

## 测试验证

运行测试脚本验证功能：

```bash
source .venv/bin/activate
python test_audio_optimization.py
```

测试结果显示：
- TTS测试音频LUFS: -24.15
- 原声测试音频LUFS: -32.95
- 建议调整系数：TTS 1.61, 原声 3.00

## 效果对比

### 优化前
- TTS音量：0.7
- 原声音量：1.0
- 问题：原声明显比TTS小

### 优化后
- TTS音量：0.8（智能调整）
- 原声音量：1.3（智能调整）
- 效果：音量平衡，听感自然

## 注意事项

1. **FFmpeg依赖**：音频分析功能需要FFmpeg支持loudnorm滤镜
2. **性能影响**：智能分析会增加少量处理时间
3. **音质保持**：所有调整都保持音频质量不变
4. **兼容性**：向后兼容现有的音量设置

## 故障排除

### 1. LUFS分析失败
- 检查FFmpeg是否安装
- 确认音频文件格式支持
- 自动降级到RMS分析

### 2. 音量调整过度
- 检查音量限制设置
- 调整目标LUFS值
- 使用预设配置文件

### 3. 性能问题
- 关闭智能分析：`ENABLE_SMART_VOLUME = False`
- 使用简单音量配置
- 减少音频分析频率

## 未来改进

1. **机器学习优化**：基于用户反馈学习最佳音量配置
2. **实时预览**：在UI中提供音量调整预览
3. **批量处理**：支持批量音频标准化
4. **更多音频格式**：扩展支持的音频格式

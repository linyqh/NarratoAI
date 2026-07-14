# NarratoAI Core

NarratoAI 是用于影视解说、脚本生成、字幕处理、语音合成和视频剪辑的 Python 核心服务。

本分支已剥离原有 Streamlit 前端控制台。仓库不再启动 Web 页面，也不再占用 `8501` 端口；你可以在 `app` 包之上自行实现 HTTP API、桌面端或其他前端。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg / FFprobe
- ImageMagick

## 初始化

```bash
uv sync
cp config.example.toml config.toml
```

编辑 `config.toml`，填写文本模型、视觉模型以及所需的 TTS 配置。配置文件默认不会提交到 Git。

验证核心包：

```bash
uv run python -m app
```

成功时会输出一段 JSON，其中 `mode` 为 `headless`。这只是自检命令，不会启动常驻服务。

## 接入自己的服务层

文本模型调用示例：

```python
import asyncio

from app.services.llm.unified_service import UnifiedLLMService


async def main():
    result = await UnifiedLLMService.generate_text("你好，请介绍 NarratoAI")
    print(result)


asyncio.run(main())
```

常用核心入口：

- `app.services.llm.unified_service.UnifiedLLMService`：文本与视觉模型
- `app.services.documentary.frame_analysis_service.DocumentaryFrameAnalysisService`：纪录片逐帧分析与脚本生成
- `app.services.video_service.VideoService`：视频裁剪
- `app.services.task`：完整视频任务编排
- `app.services.voice`：语音合成
- `app.services.subtitle`：字幕处理
- `app.models.schema.VideoClipParams`：视频任务参数模型

核心层不再依赖前端生命周期。LLM provider 会在首次调用时自动注册，进度信息通过服务函数的 `progress_callback` 参数传出。

## 测试

```bash
uv run pytest -q
```

## Docker 核心镜像

```bash
docker build -t narratoai-core .
docker run --rm narratoai-core
```

镜像默认执行 `python -m app` 自检后退出。实现新的 API 服务后，在镜像或部署配置中覆盖 `CMD` 即可。

## 许可证

参见 [LICENSE](LICENSE)。

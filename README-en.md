# NarratoAI Core

NarratoAI Core provides reusable Python services for film narration, script generation, subtitle processing, speech synthesis, and video editing.

The bundled Streamlit console has been removed from this branch. The repository no longer starts a web page or listens on port `8501`; build your own HTTP API, desktop UI, or other presentation layer on top of the `app` package.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- FFmpeg / FFprobe
- ImageMagick

## Setup

```bash
uv sync
cp config.example.toml config.toml
```

Edit `config.toml` and provide the text, vision, and TTS settings required by your workflow. The local configuration file is ignored by Git.

Run the core smoke check:

```bash
uv run python -m app
```

A successful check prints JSON with `mode` set to `headless`. It does not start a long-running server.

## Integrating a New Service Layer

```python
import asyncio

from app.services.llm.unified_service import UnifiedLLMService


async def main():
    result = await UnifiedLLMService.generate_text("Hello from NarratoAI")
    print(result)


asyncio.run(main())
```

Useful core entry points:

- `app.services.llm.unified_service.UnifiedLLMService`: text and vision models
- `app.services.documentary.frame_analysis_service.DocumentaryFrameAnalysisService`: frame analysis and documentary scripts
- `app.services.video_service.VideoService`: video clipping
- `app.services.task`: end-to-end video task orchestration
- `app.services.voice`: speech synthesis
- `app.services.subtitle`: subtitle processing
- `app.models.schema.VideoClipParams`: video task parameters

The core no longer depends on a UI lifecycle. LLM providers register lazily on first use, and service progress is exposed through `progress_callback` arguments.

## Tests

```bash
uv run pytest -q
```

## Core Docker Image

```bash
docker build -t narratoai-core .
docker run --rm narratoai-core
```

The image runs `python -m app` as a smoke check and exits. Override `CMD` after adding your new API service.

## License

See [LICENSE](LICENSE).

# 批量视频处理与 AI 解说后端开发计划

> 需求来源：[`batch_deduplication_design.md`](./batch_deduplication_design.md)
> 配套接口：[`backend_api.md`](./backend_api.md)
> 文档状态：Draft 1.0
> 适用范围：用户拥有版权或已获授权的视频素材处理。内容变换不能保证通过任何平台审核，也不应被用于规避版权、原创度或社区规则检查。

## 1. 建设目标

在当前无 WebUI 的 NarratoAI 核心能力之上，新增一个可供任意前端调用的批量视频处理后端，完成以下闭环：

1. 多视频上传与安全落盘。
2. 创建批次并限制批次级并发数。
3. 对每个视频独立执行内容变换，支持重新编码、色彩微调、弱噪声、边框、贴图、字幕遮罩、裁剪/缩放、镜像和轻微变速。
4. 可选执行“关键帧分析 → 解说脚本 → TTS → 字幕 → 音视频合成”。
5. 提供批次、单任务进度、失败原因、取消、重试和产物下载接口。
6. 记录实际采用的随机参数、模型、输入摘要和输出摘要，使任务可审计、可复现。

## 2. 不在本期范围

- 不恢复 Streamlit 或其他绑定框架的前端页面。
- 不实现用户、计费、套餐和多租户资源隔离。
- 不承诺任何平台的“去重成功率”或审核结果。
- 不将 API Key、服务器任意目录或原始异常堆栈暴露给前端。
- 不在首期实现分布式任务调度；先提供单机可靠实现，预留队列适配层。

## 3. 现有能力与差距

| 能力 | 当前状态 | 本期处理方式 |
| --- | --- | --- |
| FFmpeg / MoviePy 视频合成 | 已有，`generate_video.merge_materials()` | 复用，并把内容变换独立成 FFmpeg 服务 |
| 字幕遮罩、字幕烧录 | 已有 | 复用参数解析和合成路径 |
| 统一剪辑、TTS、字幕合成 | 已有，`task.start_subclip_unified()` | 抽出任务上下文后复用 |
| 关键帧分析和解说脚本 | 已有，支持 OpenAI 兼容视觉接口 | 配置火山 Ark 的 base URL、模型和密钥后复用 |
| 豆包 TTS | 仅有旧版 `/api/v1/tts` 适配 | 新增独立的 Seed Audio v3 适配器；旧适配器继续兼容 |
| 批量调度 | 缺失 | 新增 `BatchProcessor` 和有界线程池 |
| HTTP API | 缺失 | 新增 FastAPI 应用和 REST/SSE 接口 |
| 持久化任务状态 | 仅内存，Redis 为可选实现 | 默认 SQLite，保留 Redis/外部队列扩展点 |
| 内容变换滤镜链 | 大部分缺失 | 新增参数校验、滤镜构建和执行模块 |
| 上传与产物管理 | 仅有路径校验工具 | 新增文件 ID、受控目录和产物下载能力 |

特别注意：`task.py` 目前使用模块级 `merged_audio_path`、`merged_subtitle_path`，不适合多任务并发。本期必须先将这些变量收进单次任务上下文或函数局部变量，再开放批量并发。

## 4. 技术方案

### 4.1 技术选型

- API：FastAPI + Uvicorn。
- 请求模型：Pydantic，沿用项目现有依赖体系。
- 文件上传：`python-multipart`。
- 任务执行：单进程有界 `ThreadPoolExecutor`；FFmpeg 以子进程运行。
- 状态持久化：SQLite 默认实现，Repository 接口隔离存储细节。
- 实时进度：SSE；轮询接口始终可用，SSE 作为体验增强。
- 媒体探测与处理：`ffprobe`、FFmpeg；MoviePy 仅作为已有兼容回退。
- 密钥：仅从环境变量或本机 `config.toml` 读取，任务请求不得携带供应商密钥。

SQLite 实现必须启用 WAL、设置 `busy_timeout`，并使用“每线程/每请求独立连接”或等价的安全连接管理；禁止在线程之间共享默认 SQLite connection。事务应保持短小，媒体文件本身不写入数据库。

需要新增运行依赖：

```toml
fastapi = "..."
uvicorn = { version = "...", extras = ["standard"] }
python-multipart = "..."
```

版本号在实现时通过 `uv add` 锁定，文档不预先写死未经验证的版本。

### 4.2 模块划分

```text
app/
├── api/
│   ├── main.py                    # FastAPI 应用、生命周期与异常处理
│   ├── dependencies.py            # Repository、Processor、鉴权依赖
│   └── routes/
│       ├── health.py
│       ├── capabilities.py
│       ├── uploads.py
│       ├── batches.py
│       └── artifacts.py
├── models/
│   ├── schema.py                  # 扩展内部视频参数（保持兼容）
│   └── batch_schema.py            # API DTO、领域枚举和严格校验
├── repositories/
│   ├── task_repository.py         # 状态存储协议
│   └── sqlite_task_repository.py  # 默认持久化实现
└── services/
    ├── batch_processor.py         # 批次调度、取消、重试、进度汇总
    ├── deduplication_service.py   # FFmpeg 滤镜链构建与单文件处理
    ├── artifact_service.py        # 上传、任务目录、产物清单与下载
    ├── narration_pipeline.py      # 视觉、脚本、TTS、字幕、合成编排
    └── tts/
        └── seed_audio_provider.py # Seed Audio v3 适配器
```

测试文件与模块同目录放置，命名遵循项目现有的 `test_*_unittest.py` 习惯。

### 4.3 领域模型

#### Upload

- `id`：不可预测 UUID。
- `original_name`：仅展示，不参与服务器路径拼接。
- `stored_path`：服务端受控路径。
- `size_bytes`、`sha256`、`media_info`。
- `status`：`ready | rejected | deleted`。

#### Batch

- `id`、`status`、`progress`。
- `concurrency`：用户请求值经过服务端上限裁剪。
- `options_snapshot`：本次任务的完整配置快照。
- `total/succeeded/failed/cancelled`。
- `created_at/started_at/finished_at`。

#### VideoJob

- `id`、`batch_id`、`upload_id`。
- `status`：`queued | running | succeeded | failed | cancelling | cancelled`。
- `stage`：`probing | analyzing | scripting | synthesizing | composing | transforming | finalizing`。
- `progress`、`message`、`error`。
- `random_seed` 和 `effective_options`。
- `artifacts`：成片、字幕、脚本、分析结果和处理清单。

#### Artifact

- `id`、`job_id`、`kind`、`file_name`、`size_bytes`、`sha256`。
- 服务端真实路径只保存在 Repository 中，不通过 JSON 返回。

### 4.4 内容变换参数

新增独立 `DeduplicationOptions`，不建议把所有批处理字段继续堆入 `VideoClipParams`。进入已有剪辑流程时，由适配器转换为内部参数。

| 字段 | 类型/默认值 | 约束 |
| --- | --- | --- |
| `enabled` | `bool / true` | 内容变换总开关 |
| `change_file_hash` | `bool / true` | 只表示输出二进制摘要变化，不宣称改变内容判定 |
| `hash_strategy` | `metadata_remux` | `metadata_remux` 优先；`append_bytes` 仅兼容模式 |
| `reencode` | `bool / true` | 有视频滤镜时强制为 true |
| `color_tweak` | `bool / false` | 参数必须在服务端安全范围内随机 |
| `noise` | `bool / false` | 限制为轻量噪声，避免明显损伤画质 |
| `border_mode` | `none` | `none | solid | blurred` |
| `sticker` | `bool / false` | 仅允许资源目录内白名单 PNG |
| `subtitle_mask` | `bool / false` | 复用现有横竖屏百分比配置 |
| `crop_scale` | `bool / false` | 裁剪比例限定在 `[0.005, 0.015]` |
| `mirror_probability` | `float / 0` | `[0, 1]`，实际结果写入清单 |
| `speed_tweak` | `bool / false` | 视频与音频必须同步变速 |
| `speed_range` | `[0.99, 1.01]` | 最小值必须小于等于最大值 |
| `random_seed` | 可空整数 | 不提供时由服务端生成并返回 |

滤镜采用纯函数构建：

```python
def build_filter_plan(
    media_info: MediaInfo,
    options: DeduplicationOptions,
    seed: int,
) -> EffectiveFilterPlan:
    """只生成确定性的有效参数与 FFmpeg filter graph，不执行命令。"""
```

实际执行接口：

```python
def apply_direct_deduplication(
    input_path: str,
    output_path: str,
    options: DeduplicationOptions,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> DeduplicationResult:
    """执行转码并返回产物信息；失败时抛出领域异常。"""
```

### 4.5 AI 解说流水线

启用 AI 解说时，每个视频依次执行：

1. `ffprobe` 校验媒体并获取时长、分辨率、音轨。
2. `DocumentaryFrameAnalysisService` 按间隔抽帧。
3. 通过 OpenAI 兼容视觉 Provider 调用火山 Ark：
   - base URL：`https://ark.cn-beijing.volces.com/api/v3`
   - model：`doubao-seed-2-1-turbo-260628`
   - API Key：服务端配置。
4. 通过文本模型生成带 `timestamp/narration/OST` 的剪辑脚本，并写入任务目录。
5. 通过新 `SeedAudioProvider` 调用需求指定的 TTS 服务，生成解说音频及可用于字幕对齐的时间信息。
6. 复用现有裁剪、字幕和合成能力产出解说版视频。
7. 在最终视频上执行内容变换滤镜链；若滤镜链已包含字幕遮罩，应确保遮罩发生在新字幕烧录之前。
8. 写入处理清单并计算 SHA-256。

供应商接口的请求体、异步查询方式、音频返回形式和时间戳能力需要在开发第一阶段用官方文档/沙箱请求确认。当前代码中的豆包旧版适配器不能直接替代 Seed Audio v3。

服务端配置应至少包含以下项，真实密钥优先通过环境变量注入：

| 配置项 | 默认/示例值 | 说明 |
| --- | --- | --- |
| `vision_openai_base_url` | `https://ark.cn-beijing.volces.com/api/v3` | OpenAI 兼容客户端会调用其 `chat/completions` |
| `vision_openai_model_name` | `doubao-seed-2-1-turbo-260628` | 视觉分析模型 |
| `vision_openai_api_key` | `${VOLCANO_ARK_API_KEY}` | 不得写入日志或任务快照 |
| `seed_audio_api_url` | `https://openspeech.bytedance.com/api/v3/tts/create` | 需求指定的 Seed Audio v3 地址 |
| `seed_audio_model` | `seed-audio-1.0` | TTS 模型 |
| `seed_audio_api_key` | `${SEED_AUDIO_API_KEY}` | 请求时映射到 `X-Api-Key` |
| `batch_max_workers` | `2` | 全局视频任务并发上限 |
| `batch_output_root` | `storage/tasks` | 产物受控根目录 |

### 4.6 批量调度与资源控制

- API 接收请求后立即返回 `202`，不得在请求线程同步完成视频处理。
- 使用单个应用级有界线程池，`max_workers` 由服务器配置控制。
- 批次的 `concurrency` 只是该批次的并发上限，实际并发为：

```text
min(批次请求并发, 服务端全局上限, 当前可用工作槽)
```

- 区分“视频任务并发数”和单个 FFmpeg 的 `-threads`，避免 CPU 过度订阅。
- AI Provider 使用单独信号量与退避重试，避免并行视频同时触发限流。
- 取消运行中的 FFmpeg 时先发送正常终止信号，超时后再强制终止；已成功产物不删除。
- 应用重启后：`running/cancelling` 任务恢复成 `failed`（错误码 `WORKER_INTERRUPTED`），允许用户重试。
- 一个任务的异常不能导致同批其他任务取消。
- 服务关闭时先停止接收新批次，再给运行任务一个可配置的优雅退出窗口；超时任务按中断恢复策略落库。

### 4.7 存储布局

```text
storage/
├── uploads/{upload_id}/source.ext
├── tasks/{batch_id}/{job_id}/
│   ├── analysis.json
│   ├── script.json
│   ├── narration.mp3
│   ├── subtitle.srt
│   ├── output.mp4
│   └── manifest.json
└── state/narratoai.sqlite3
```

前端传入的是 `upload_id` 和可选 `output_name`，不是服务器绝对路径。导出根目录由服务端配置，防止目录穿越和浏览器/服务器路径语义混乱。

## 5. 开发阶段

### 阶段 0：基线与技术验证

- 补充 FastAPI、Uvicorn 和 multipart 依赖。
- 验证 FFmpeg 所需滤镜和编码器，形成 `/capabilities` 输出。
- 用最小请求验证 Ark 视觉模型请求格式和 Seed Audio v3 返回格式。
- 固定测试样例：有声/无声、横屏/竖屏、带硬字幕、短视频各一份。

交付标准：服务可启动，健康检查成功，供应商接口差异形成记录。

### 阶段 1：领域模型、存储和上传

- 新增 API DTO、错误码和状态枚举。
- 实现 SQLite Repository 与数据库初始化。
- 实现分块上传落盘、扩展名/MIME/ffprobe 三层校验。
- 实现 ArtifactService 和安全下载。

交付标准：上传、查询、删除、下载接口通过单元和集成测试。

### 阶段 2：单视频内容变换引擎

- 实现确定性随机参数生成。
- 实现 FFmpeg filter graph 构建器。
- 实现重新编码、色彩、噪声、边框、贴图、遮罩、裁剪、镜像和同步变速。
- 默认以 metadata remux 改变文件摘要；append bytes 作为显式兼容选项。
- 输出 `manifest.json`，保存命令的脱敏版本和实际参数。

交付标准：所有开关可独立及组合执行，输出能通过 `ffprobe` 并完整解码。

### 阶段 3：AI 解说适配

- 配置 Volcano Ark 视觉 Provider。
- 新增 `SeedAudioProvider`，保留旧 `doubaotts` 行为不变。
- 将现有 `task.py` 的模块级任务变量改为局部上下文。
- 新增 NarrationPipeline，完成脚本、音频、字幕与视频的串联。
- 为外部调用增加超时、限流、指数退避和脱敏日志。

交付标准：开启 AI 时可生成脚本、音频、SRT 和最终视频；关闭时不调用任何 AI/TTS 服务。

### 阶段 4：批量调度与 API

- 实现 BatchProcessor、有界并发、取消和失败重试。
- 实现批次 REST API 和 SSE 进度推送。
- 实现状态聚合和应用重启后的任务恢复策略。
- 添加可选本地 Bearer Token 鉴权及 CORS 白名单。

交付标准：多视频批次能并发执行，单任务失败不影响其他任务，前端只依赖文档中的公共接口。

### 阶段 5：质量、性能和交付

- 完成组合滤镜、异常、并发、取消、重启和安全测试。
- 对 1、2、4 个并发任务进行 CPU、内存和磁盘基准测试。
- 给出 `.env.example`/`config.example.toml` 新配置项，不提交真实密钥。
- 更新 README 启动命令和 API 文档。

交付标准：测试全绿，样例批次验收通过，敏感信息扫描无泄漏。

## 6. 测试计划

### 6.1 单元测试

- 参数边界和非法组合。
- 随机种子相同时得到相同 `EffectiveFilterPlan`。
- FFmpeg 参数以数组传递，不经过 shell 字符串拼接。
- 路径净化、文件名碰撞、扩展名伪造和超限上传。
- Repository 状态迁移和进度聚合。
- Ark 与 Seed Audio 使用 mock server 验证请求头、超时、限流和错误映射。

### 6.2 媒体集成测试

- 每个单独滤镜以及常用组合。
- 横屏、竖屏、奇数尺寸、有声、无声、可变帧率视频。
- 0.99x 与 1.01x 下音视频时长误差不超过 100ms 或总时长的 0.5%。
- 输出文件 `ffprobe` 成功，完整解码无错误，音频轨/字幕符合选项。
- 输入文件不被修改；输出 SHA-256 与输入不同。

### 6.3 API 与并发测试

- 批量上传、创建、轮询、SSE、取消、重试和下载完整链路。
- 并发值超过上限时被裁剪或返回明确错误。
- 一个 Job 失败时其他 Job 正常完成。
- 客户端断开 SSE 不影响后台任务。
- 重复 `Idempotency-Key` 不创建重复批次。

## 7. 验收标准

1. 一次请求可提交至少 20 个已上传视频，服务端按照配置的上限调度。
2. 关闭 AI 后不产生外部模型请求，保留原声并输出有效视频。
3. 开启 AI 后产出视频、脚本、字幕、配音和处理清单。
4. 每个任务提供可查询的阶段、进度、结果或结构化失败原因。
5. 所有处理开关都能独立启用或关闭，实际随机参数可追溯。
6. 任务请求和日志中不出现供应商密钥，下载接口不能访问任务目录以外的文件。
7. 批次取消、失败重试、应用异常重启均有确定行为。
8. API 与实现保持兼容；破坏性变更必须使用新的 API 主版本。

## 8. 风险与待确认事项

| 风险/问题 | 处理建议 |
| --- | --- |
| Seed Audio v3 的准确请求体和时间戳返回未在现有代码验证 | 阶段 0 用官方文档和沙箱请求确认，Provider 内隔离差异 |
| 视觉模型是否支持单请求多图、图片数量和大小上限 | 继续使用批次抽帧，并配置批大小和并发上限 |
| `task.py` 全局变量导致并发串任务 | 阶段 3 前必须完成上下文隔离 |
| MoviePy 路径耗时和内存占用较高 | 新内容变换坚持 FFmpeg 优先，MoviePy 仅兼容回退 |
| 任意输出目录带来目录穿越和权限问题 | 只允许服务端配置输出根目录和安全子目录 |
| 追加随机字节可能影响严格容器解析器 | 默认使用 metadata remux，append bytes 仅显式兼容模式 |
| 多任务同时请求模型易触发限流 | Provider 级信号量、退避重试和可配置 QPS |
| 平台审核规则不可控 | 产品文案不承诺规避检测，只陈述可验证的视频处理效果 |

待产品/供应商确认：

1. Seed Audio 使用预置音色还是声音克隆；若为克隆，参考音频如何授权和保存。
2. TTS 是否直接返回字/句级时间戳；若不返回，采用文本分段时长还是 ASR 回标。
3. 单文件和单批次的大小、数量、总时长上限。
4. 上传文件、失败中间件和成功产物的保留天数。
5. 首期是否需要公网部署；若需要，必须增加正式鉴权、TLS、速率限制和对象存储。

# 批量视频处理后端 API 接口文档

> 版本：v1 Draft
> Base URL：`http://127.0.0.1:8080/api/v1`
> 开发计划：[`backend_plan.md`](./backend_plan.md)

## 1. 通用约定

### 1.1 数据格式

- 除文件上传和下载外，请求与响应均为 `application/json; charset=utf-8`。
- 时间使用 UTC ISO 8601，例如 `2026-07-14T08:30:00Z`。
- ID 为服务端生成的 UUID 字符串，客户端不得从 ID 推断服务器路径。
- 任务创建为异步操作，成功接收返回 HTTP `202 Accepted`。
- JSON 字段使用 `snake_case`。

### 1.2 鉴权

本地开发可关闭鉴权。启用后所有 `/api/v1` 请求都必须携带：

```http
Authorization: Bearer <NARRATO_API_TOKEN>
```

供应商的 Ark、Seed Audio 等 API Key 只配置在服务端，不能放在业务请求中。

### 1.3 幂等

创建批次时建议携带：

```http
Idempotency-Key: <客户端生成的唯一值>
```

相同身份、相同 Key 在保留期内重复请求时，服务端返回第一次创建的批次，不重复执行。

### 1.4 成功响应

```json
{
  "data": {},
  "request_id": "2ec255f7-8bdf-46ce-a748-3a927582f828"
}
```

### 1.5 错误响应

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "speed_range 的最小值不能大于最大值",
    "details": [
      {
        "field": "deduplication.speed_range",
        "reason": "invalid_range"
      }
    ],
    "retryable": false
  },
  "request_id": "2ec255f7-8bdf-46ce-a748-3a927582f828"
}
```

常用状态码：

| HTTP | 场景 |
| --- | --- |
| `200` | 查询、取消或删除成功 |
| `201` | 上传成功 |
| `202` | 批次已受理 |
| `400` | 参数或媒体内容无效 |
| `401` | 未鉴权或 Token 无效 |
| `404` | 资源不存在 |
| `409` | 当前状态不允许操作 |
| `413` | 文件或批次超过上限 |
| `422` | JSON 字段校验失败 |
| `429` | 客户端请求过快或任务容量已满 |
| `500` | 未预期的服务端错误 |
| `502` | 上游 AI/TTS 服务异常 |
| `503` | FFmpeg、磁盘或工作池暂不可用 |

## 2. 状态与枚举

### 2.1 批次状态 `BatchStatus`

```text
queued | running | partially_succeeded | succeeded | failed | cancelling | cancelled
```

### 2.2 单视频任务状态 `JobStatus`

```text
queued | running | succeeded | failed | cancelling | cancelled
```

### 2.3 执行阶段 `JobStage`

```text
queued
probing
analyzing
scripting
synthesizing
composing
transforming
finalizing
completed
```

### 2.4 产物类型 `ArtifactKind`

```text
video | subtitle | script | analysis | narration_audio | manifest
```

## 3. 健康检查与能力

### 3.1 存活检查

```http
GET /health/live
```

响应：

```json
{
  "data": {
    "status": "ok"
  },
  "request_id": "..."
}
```

### 3.2 就绪检查

```http
GET /health/ready
```

响应示例：

```json
{
  "data": {
    "status": "ready",
    "checks": {
      "database": "ok",
      "storage": "ok",
      "ffmpeg": "ok",
      "ffprobe": "ok"
    }
  },
  "request_id": "..."
}
```

就绪检查只验证本地依赖，不通过真实 AI/TTS 请求消耗额度。

### 3.3 查询服务能力

```http
GET /capabilities
```

响应示例：

```json
{
  "data": {
    "accepted_video_extensions": ["mp4", "mov", "mkv", "webm"],
    "max_upload_size_bytes": 2147483648,
    "max_files_per_batch": 20,
    "max_batch_concurrency": 4,
    "deduplication": {
      "reencode": true,
      "color_tweak": true,
      "noise": true,
      "border_modes": ["none", "solid", "blurred"],
      "sticker": true,
      "subtitle_mask": true,
      "crop_scale": true,
      "mirror": true,
      "speed_tweak": true
    },
    "narration": {
      "available": true,
      "vision_provider": "openai",
      "vision_model": "doubao-seed-2-1-turbo-260628",
      "tts_provider": "seed_audio",
      "tts_model": "seed-audio-1.0"
    }
  },
  "request_id": "..."
}
```

`narration.available=false` 表示服务端缺少模型配置；响应不会返回 Key。

## 4. 视频上传

### 4.1 上传一个或多个视频

```http
POST /uploads/videos
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `files` | file[] | 是 | 可重复字段，多视频上传 |

示例：

```bash
curl -X POST 'http://127.0.0.1:8080/api/v1/uploads/videos' \
  -H 'Authorization: Bearer local-token' \
  -F 'files=@/path/a.mp4' \
  -F 'files=@/path/b.mov'
```

响应：`201 Created`

```json
{
  "data": {
    "uploads": [
      {
        "id": "7299805d-e188-481e-9ef4-f6915af55bd0",
        "original_name": "a.mp4",
        "size_bytes": 38290122,
        "sha256": "7b6d...",
        "status": "ready",
        "media_info": {
          "duration_seconds": 32.42,
          "width": 1080,
          "height": 1920,
          "fps": 30.0,
          "has_audio": true,
          "video_codec": "h264",
          "audio_codec": "aac"
        }
      }
    ]
  },
  "request_id": "..."
}
```

服务端必须以文件签名和 `ffprobe` 结果校验媒体，不能只信任文件名或 MIME。

### 4.2 查询上传文件

```http
GET /uploads/{upload_id}
```

返回结构与上传响应中的单个 Upload 相同。

### 4.3 删除上传文件

```http
DELETE /uploads/{upload_id}
```

只有未被运行中任务引用的上传文件可以删除；否则返回 `409 UPLOAD_IN_USE`。

成功响应：

```json
{
  "data": {
    "id": "7299805d-e188-481e-9ef4-f6915af55bd0",
    "deleted": true
  },
  "request_id": "..."
}
```

## 5. 创建批处理任务

### 5.1 创建批次

```http
POST /batches
Idempotency-Key: batch-20260714-001
```

完整请求示例：

```json
{
  "upload_ids": [
    "7299805d-e188-481e-9ef4-f6915af55bd0",
    "9fbfcd61-9519-4513-b234-8ff483e452b3"
  ],
  "output_subdir": "campaign-20260714",
  "concurrency": 2,
  "narration": {
    "enabled": true,
    "language": "zh-TW",
    "video_theme": "悬疑影视解说",
    "prompt": "叙述自然，保持事实准确，不虚构未出现的剧情",
    "frame_interval_seconds": 5,
    "vision_batch_size": 10,
    "voice_id": "zh_tw_male_mature",
    "voice_prompt": "成熟、克制、略带悬疑感",
    "voice_rate": 1.0,
    "voice_volume": 1.0,
    "original_audio_volume": 0.25,
    "subtitle_enabled": true
  },
  "deduplication": {
    "enabled": true,
    "change_file_hash": true,
    "hash_strategy": "metadata_remux",
    "reencode": true,
    "color_tweak": true,
    "noise": true,
    "border_mode": "blurred",
    "sticker": false,
    "subtitle_mask": true,
    "crop_scale": true,
    "crop_ratio_range": [0.005, 0.015],
    "mirror_probability": 0.2,
    "speed_tweak": true,
    "speed_range": [0.99, 1.01],
    "random_seed": null
  }
}
```

字段定义：

#### 顶层字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `upload_ids` | string[] | 是 | - | 1 至服务端上限个 Upload ID，不可重复 |
| `output_subdir` | string | 否 | 批次 ID | 只允许安全相对名称，不接受绝对路径或 `..` |
| `concurrency` | integer | 否 | `1` | `[1, 服务端上限]` |
| `narration` | object | 否 | `enabled=false` | AI 解说参数 |
| `deduplication` | object | 否 | `enabled=true` | 内容变换参数 |

#### `narration`

| 字段 | 类型 | 默认值 | 约束/说明 |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | false 时不调用视觉、文本或 TTS 服务 |
| `language` | string | `zh-CN` | BCP 47 语言标签 |
| `video_theme` | string | `""` | 最长 200 字符 |
| `prompt` | string | `""` | 最长 2000 字符 |
| `frame_interval_seconds` | number | 服务端配置 | `[1, 60]` |
| `vision_batch_size` | integer | 服务端配置 | `[1, 服务端上限]` |
| `voice_id` | string | 服务端默认音色 | 必须来自 `/capabilities` 白名单 |
| `voice_prompt` | string | `""` | 最长 500 字符；供应商不支持时返回校验错误 |
| `voice_rate` | number | `1.0` | `[0.5, 2.0]`，最终受供应商能力约束 |
| `voice_volume` | number | `1.0` | `[0, 2]` |
| `original_audio_volume` | number | `0.25` | `[0, 2]` |
| `subtitle_enabled` | boolean | `true` | 是否生成并烧录新字幕 |

#### `deduplication`

| 字段 | 类型 | 默认值 | 约束/说明 |
| --- | --- | --- | --- |
| `enabled` | boolean | `true` | 总开关 |
| `change_file_hash` | boolean | `true` | 确保输出摘要变化 |
| `hash_strategy` | string | `metadata_remux` | `metadata_remux | append_bytes` |
| `reencode` | boolean | `true` | 开启视频滤镜时自动强制 true |
| `color_tweak` | boolean | `false` | 服务端在安全范围内生成实际值 |
| `noise` | boolean | `false` | 弱噪声 |
| `border_mode` | string | `none` | `none | solid | blurred` |
| `sticker` | boolean | `false` | 从服务端白名单资源中选取 |
| `subtitle_mask` | boolean | `false` | 使用服务端横/竖屏遮罩配置 |
| `crop_scale` | boolean | `false` | 轻微裁剪后缩放回输出尺寸 |
| `crop_ratio_range` | number[2] | `[0.005,0.015]` | 两项均在 `[0,0.05]` |
| `mirror_probability` | number | `0` | `[0,1]` |
| `speed_tweak` | boolean | `false` | 音视频同步变速 |
| `speed_range` | number[2] | `[0.99,1.01]` | 两项均在 `[0.9,1.1]` |
| `random_seed` | integer/null | `null` | null 时服务端生成；结果中返回 |

响应：`202 Accepted`

```json
{
  "data": {
    "batch_id": "cc0ab617-6362-44da-a0df-f3ce0d2d36ed",
    "status": "queued",
    "progress": 0,
    "total": 2,
    "status_url": "/api/v1/batches/cc0ab617-6362-44da-a0df-f3ce0d2d36ed",
    "events_url": "/api/v1/batches/cc0ab617-6362-44da-a0df-f3ce0d2d36ed/events"
  },
  "request_id": "..."
}
```

## 6. 查询与控制批次

### 6.1 查询批次详情

```http
GET /batches/{batch_id}
```

响应示例：

```json
{
  "data": {
    "id": "cc0ab617-6362-44da-a0df-f3ce0d2d36ed",
    "status": "running",
    "progress": 63,
    "total": 2,
    "queued": 0,
    "running": 1,
    "succeeded": 1,
    "failed": 0,
    "cancelled": 0,
    "created_at": "2026-07-14T08:30:00Z",
    "started_at": "2026-07-14T08:30:02Z",
    "finished_at": null,
    "jobs": [
      {
        "id": "6f0af7dc-7634-4098-a07a-1f9af31e0c99",
        "upload_id": "7299805d-e188-481e-9ef4-f6915af55bd0",
        "source_name": "a.mp4",
        "status": "succeeded",
        "stage": "completed",
        "progress": 100,
        "message": "处理完成",
        "random_seed": 18273641,
        "artifacts": [
          {
            "id": "525ed523-ebdc-4be3-a9a3-6292bf9566c1",
            "kind": "video",
            "file_name": "a_processed.mp4",
            "size_bytes": 40192833,
            "sha256": "c9d2...",
            "download_url": "/api/v1/artifacts/525ed523-ebdc-4be3-a9a3-6292bf9566c1/download"
          }
        ],
        "error": null
      },
      {
        "id": "a52177c4-545d-4d64-b9b8-7ad59e8a04df",
        "upload_id": "9fbfcd61-9519-4513-b234-8ff483e452b3",
        "source_name": "b.mov",
        "status": "running",
        "stage": "synthesizing",
        "progress": 46,
        "message": "正在生成第 3/8 段解说音频",
        "random_seed": 89172311,
        "artifacts": [],
        "error": null
      }
    ]
  },
  "request_id": "..."
}
```

批次进度按所有 Job 等权聚合；单个 Job 的阶段进度必须单调不下降。

### 6.2 列出批次

```http
GET /batches?status=running&limit=20&cursor=<opaque_cursor>
```

响应：

```json
{
  "data": {
    "items": [],
    "next_cursor": null
  },
  "request_id": "..."
}
```

### 6.3 取消批次

```http
POST /batches/{batch_id}/cancel
```

语义：

- `queued` Job 直接变为 `cancelled`。
- `running` Job 变为 `cancelling`，在安全中断点终止。
- 已成功或失败的 Job 保持原状态，成功产物继续可下载。
- 对终态批次重复取消是幂等操作。

响应：

```json
{
  "data": {
    "id": "cc0ab617-6362-44da-a0df-f3ce0d2d36ed",
    "status": "cancelling"
  },
  "request_id": "..."
}
```

### 6.4 重试失败任务

```http
POST /batches/{batch_id}/jobs/{job_id}/retry
```

可选请求体：

```json
{
  "reuse_random_seed": true
}
```

响应 `202 Accepted`，返回新 Job ID；旧 Job 保留用于审计。

```json
{
  "data": {
    "job_id": "30252ef4-1ea4-4ea4-a9c7-556717f7150b",
    "retry_of": "a52177c4-545d-4d64-b9b8-7ad59e8a04df",
    "status": "queued"
  },
  "request_id": "..."
}
```

## 7. 实时进度事件

```http
GET /batches/{batch_id}/events
Accept: text/event-stream
```

事件示例：

```text
id: 148
event: job.progress
data: {"batch_id":"cc0ab617-6362-44da-a0df-f3ce0d2d36ed","job_id":"a52177c4-545d-4d64-b9b8-7ad59e8a04df","status":"running","stage":"synthesizing","progress":46,"message":"正在生成第 3/8 段解说音频","occurred_at":"2026-07-14T08:31:20Z"}

id: 149
event: batch.progress
data: {"batch_id":"cc0ab617-6362-44da-a0df-f3ce0d2d36ed","status":"running","progress":63,"succeeded":1,"failed":0,"total":2,"occurred_at":"2026-07-14T08:31:20Z"}
```

事件类型：

```text
batch.created
batch.started
batch.progress
batch.completed
job.started
job.progress
job.completed
job.failed
job.cancelled
heartbeat
```

客户端重连时可以携带标准 `Last-Event-ID`。若事件已超过服务端保留窗口，服务端发送当前快照，客户端再通过批次详情接口校准状态。

启用 Bearer Token 时，浏览器端应使用支持自定义请求头的 `fetch()` 流式读取 SSE；原生 `EventSource` 无法设置 `Authorization` 请求头。禁止把 Token 放进 URL 查询参数。若未来采用同源 HttpOnly Cookie 鉴权，可再开放原生 `EventSource` 用法。

## 8. 产物接口

### 8.1 查询产物元数据

```http
GET /artifacts/{artifact_id}
```

```json
{
  "data": {
    "id": "525ed523-ebdc-4be3-a9a3-6292bf9566c1",
    "job_id": "6f0af7dc-7634-4098-a07a-1f9af31e0c99",
    "kind": "video",
    "file_name": "a_processed.mp4",
    "content_type": "video/mp4",
    "size_bytes": 40192833,
    "sha256": "c9d2...",
    "created_at": "2026-07-14T08:32:01Z",
    "download_url": "/api/v1/artifacts/525ed523-ebdc-4be3-a9a3-6292bf9566c1/download"
  },
  "request_id": "..."
}
```

### 8.2 下载产物

```http
GET /artifacts/{artifact_id}/download
```

响应使用正确的 `Content-Type`、`Content-Length` 和安全的 `Content-Disposition`。视频下载应支持 HTTP Range 请求。

服务器绝对路径不属于公共接口。前端应显示 `file_name`，并使用 `download_url` 下载或播放。

## 9. 处理清单 `manifest.json`

每个成功 Job 至少生成一份清单：

```json
{
  "schema_version": "1.0",
  "job_id": "6f0af7dc-7634-4098-a07a-1f9af31e0c99",
  "source": {
    "upload_id": "7299805d-e188-481e-9ef4-f6915af55bd0",
    "file_name": "a.mp4",
    "sha256": "7b6d..."
  },
  "random_seed": 18273641,
  "narration": {
    "enabled": true,
    "vision_model": "doubao-seed-2-1-turbo-260628",
    "tts_model": "seed-audio-1.0",
    "language": "zh-TW",
    "script_artifact_id": "..."
  },
  "effective_filters": {
    "brightness": 0.012,
    "contrast": 1.018,
    "saturation": 0.991,
    "noise_strength": 2,
    "border_mode": "blurred",
    "crop_ratio": 0.009,
    "mirrored": false,
    "speed": 1.006
  },
  "output": {
    "artifact_id": "525ed523-ebdc-4be3-a9a3-6292bf9566c1",
    "sha256": "c9d2...",
    "duration_seconds": 32.23
  },
  "software": {
    "narratoai_version": "0.8.4",
    "ffmpeg_version": "..."
  }
}
```

清单不得保存 API Key、Authorization 请求头、用户 Token 或未脱敏的供应商响应。

## 10. 错误码

| 错误码 | HTTP | 可重试 | 说明 |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 400/422 | 否 | 请求字段或组合无效 |
| `UPLOAD_TOO_LARGE` | 413 | 否 | 单文件超过上限 |
| `BATCH_TOO_LARGE` | 413 | 否 | 文件数或总时长超过上限 |
| `UNSUPPORTED_MEDIA` | 400 | 否 | 文件不是可解码的视频 |
| `UPLOAD_IN_USE` | 409 | 否 | 上传文件正被任务引用 |
| `INVALID_STATE_TRANSITION` | 409 | 否 | 当前任务状态不允许操作 |
| `CAPACITY_EXCEEDED` | 429 | 是 | 工作队列已满 |
| `VISION_NOT_CONFIGURED` | 503 | 否 | 未配置视觉模型 |
| `TTS_NOT_CONFIGURED` | 503 | 否 | 未配置 TTS |
| `UPSTREAM_RATE_LIMITED` | 502 | 是 | AI/TTS 上游限流 |
| `UPSTREAM_TIMEOUT` | 502 | 是 | AI/TTS 上游超时 |
| `UPSTREAM_BAD_RESPONSE` | 502 | 视情况 | 上游响应无法解析 |
| `FFPROBE_FAILED` | 400/500 | 视情况 | 输入探测或输出验收失败 |
| `FFMPEG_FAILED` | 500 | 视情况 | 媒体处理失败 |
| `INSUFFICIENT_STORAGE` | 503 | 是 | 可用磁盘空间不足 |
| `WORKER_INTERRUPTED` | 500 | 是 | 服务重启导致任务中断 |
| `ARTIFACT_NOT_FOUND` | 404 | 否 | 产物不存在或已过保留期 |

## 11. 前端推荐调用顺序

```text
GET  /capabilities
  ↓
POST /uploads/videos
  ↓ 获取 upload_ids
POST /batches
  ↓ 获取 batch_id
GET  /batches/{batch_id}/events  ← 实时展示
GET  /batches/{batch_id}         ← 轮询/断线校准
  ↓
GET  /artifacts/{artifact_id}/download
```

前端应以服务端返回的状态为准，不根据本地计时推算任务是否成功。SSE 断开不代表任务失败。

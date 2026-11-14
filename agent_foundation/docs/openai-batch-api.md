# OpenAI Batch API：异步批处理（Batch API）

- 原文：[Batch API](https://developers.openai.com/api/docs/guides/batch)
- 来源：OpenAI 官方 API 文档（镜像站 developers.openai.ac.cn 抓取，官方站对命令行抓取返回 Forbidden）
- 发布：官方文档页，随 OpenAI 平台持续更新
- 译文说明：原文为中文镜像，本篇为按本包语言规则的合规改写整理，术语保留英文原词；官方页每步附 JavaScript、Python、Go、Java、Ruby、curl、CLI 七种形态代码，本篇保留 Python 与 curl 两种，其余语言的等价调用不再展开。

## 概述

部分 OpenAI 平台场景需要同步请求，但很多情况下请求并不需要即时响应，或者速率限制阻止了大量查询快速执行。批处理任务通常在以下场景中有用：运行评估、对大型数据集进行分类、为内容库生成嵌入、为大型离线视频渲染任务排队。

Batch API 提供一组端点：把一批请求收集进单个文件，启动批处理任务执行它们，在执行期间查询批处理状态，完成后获取结果。与标准端点相比有三个优势：

1. 成本效益：与同步 API 相比 50% 的费用折扣。
2. 更高的速率限制：与同步 API 相比显著提高的上限，使用独立的资源池。
3. 快速完成：每个批处理在 24 小时内完成（通常更快）。

## 开始使用

### 1. 准备批处理文件

批处理从 `.jsonl` 文件开始，每行包含单个请求的详细信息。目前可用的端点有：

- `/v1/responses`（Responses API）
- `/v1/chat/completions`（Chat Completions API）
- `/v1/embeddings`（Embeddings API）
- `/v1/completions`（Completions API）
- `/v1/moderations`（审核）
- `/v1/images/generations` 与 `/v1/images/edits`（Images API）
- `/v1/videos`（视频生成）

每行 `body` 字段的参数与底层端点相同。每个请求必须包含唯一的 `custom_id`，用于任务完成后引用结果。每个输入文件只能包含对单个模型的请求。

两个请求的输入文件示例：

```text
{"custom_id": "request-1", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "gpt-3.5-turbo-0125", "messages": [{"role": "system", "content": "You are a helpful assistant."},{"role": "user", "content": "Hello world!"}],"max_tokens": 1000}}
{"custom_id": "request-2", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "gpt-3.5-turbo-0125", "messages": [{"role": "system", "content": "You are an unhelpful assistant."},{"role": "user", "content": "Hello world!"}],"max_tokens": 1000}}
```

视频生成的限制：Batch 目前仅支持 `POST /v1/videos`；视频请求必须用 JSON，不能用 multipart；提前上传资产并在请求正文传资产引用（图像引导生成用 `input_reference`，JSON 里作为带 `file_id` 或 `image_url` 的对象传递）；Batch 生成的视频在批处理完成后最多保存 24 小时供下载。

针对 `/v1/moderations` 时，每个请求体必须包含 `input` 字段。Batch 接受纯文本输入与内容数组（文本或图像，用 `omni-moderation-latest`）。处理器拒绝 `stream=true` 的请求，与同步审核端点一致。多模态审核请求建议优先用 `image_url` 引用远程资源，让 `.jsonl` 文件远低于 200 MB 上传上限。

### 2. 上传批处理输入文件

与微调 API 类似，先通过 Files API 上传输入文件，之后才能在创建批处理时引用它。

```python
from openai import OpenAI

client = OpenAI()

batch_input_file = client.files.create(
    file=open("batchinput.jsonl", "rb"), purpose="batch"
)

print(batch_input_file)
```

curl 形态：

```bash
curl https://api.openai.com/v1/files \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F purpose="batch" \
  -F file="@batchinput.jsonl"
```

### 3. 创建批处理

上传成功后，用文件 ID 创建批处理（示例假设为 `file-abc123`）。完成窗口目前只能设为 `24h`。可通过可选的 `metadata` 参数提供自定义元数据。

```python
batch = client.batches.create(
    input_file_id=batch_input_file.id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
    metadata={"description": "nightly eval job"},
)
print(batch)
```

curl 形态：

```bash
curl https://api.openai.com/v1/batches \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input_file_id": "file-abc123",
    "endpoint": "/v1/chat/completions",
    "completion_window": "24h"
  }'
```

请求返回包含批处理元数据的 Batch 对象：

```json
{
  "id": "batch_abc123",
  "object": "batch",
  "endpoint": "/v1/chat/completions",
  "errors": null,
  "input_file_id": "file-abc123",
  "completion_window": "24h",
  "status": "validating",
  "output_file_id": null,
  "error_file_id": null,
  "created_at": 1714508499,
  "expires_at": 1714536634,
  "request_counts": {"total": 0, "completed": 0, "failed": 0},
  "metadata": null
}
```

### 4. 检查批处理状态

随时用 `retrieve` 检查状态，返回 Batch 对象：

```python
batch = client.batches.retrieve(batch.id)
print(batch)
```

Batch 对象的运行状态共八种：

| 状态 | 描述 |
|---|---|
| `validating` | 批处理开始前正在验证输入文件 |
| `failed` | 输入文件未通过验证 |
| `in_progress` | 验证成功，批处理正在运行 |
| `finalizing` | 批处理已完成，结果正在准备中 |
| `completed` | 已完成，结果就绪 |
| `expired` | 无法在 24 小时窗口内完成 |
| `cancelling` | 正在被取消（最多需要 10 分钟） |
| `cancelled` | 已被取消 |

### 5. 获取结果

批处理完成后，用 Batch 对象的 `output_file_id` 通过 Files API 下载输出结果：

```python
file_response = client.files.content(output_file_id)
print(file_response.text)
```

curl 形态：

```bash
curl https://api.openai.com/v1/files/file-xyz123/content \
  -H "Authorization: Bearer $OPENAI_API_KEY" > batch_output.jsonl
```

输出 `.jsonl` 文件的每行响应对应输入文件中的一个成功请求。失败请求的错误信息写入错误文件，通过 `error_file_id` 获取。

`/v1/videos` 的完成结果包含已达终态（`completed`、`failed`、`expired`）的视频对象，可用返回的视频 ID 在批处理完成后下载最终资产。

输出文件的行顺序可能与输入文件不一致，不要依赖顺序处理结果，用每行的 `custom_id` 把输入请求映射到输出结果：

```text
{"id": "batch_req_123", "custom_id": "request-2", "response": {"status_code": 200, "request_id": "req_123", "body": {"id": "chatcmpl-123", "object": "chat.completion", "created": 1711652795, "model": "gpt-3.5-turbo-0125", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello."}, "logprobs": null, "finish_reason": "stop"}], "usage": {"prompt_tokens": 22, "completion_tokens": 2, "total_tokens": 24}, "system_fingerprint": "fp_123"}}, "error": null}
{"id": "batch_req_456", "custom_id": "request-1", "response": {"status_code": 200, "request_id": "req_789", "body": {"id": "chatcmpl-abc", "object": "chat.completion", "created": 1711652789, "model": "gpt-3.5-turbo-0125", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello! How can I assist you today?"}, "logprobs": null, "finish_reason": "stop"}], "usage": {"prompt_tokens": 20, "completion_tokens": 9, "total_tokens": 29}, "system_fingerprint": "fp_3ba"}}, "error": null}
```

输出文件在批处理完成 30 天后自动删除。

### 6. 取消批处理

可取消正在进行的批处理。状态先变为 `cancelling`，等进行中的请求完成（最多 10 分钟），之后变为 `cancelled`：

```python
client.batches.cancel(batch_id)
```

curl 形态：

```bash
curl https://api.openai.com/v1/batches/batch_abc123/cancel \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -X POST
```

### 7. 获取所有批处理列表

随时查看所有批处理任务。批处理数量多时用 `limit` 与 `after` 参数分页：

```python
client.batches.list(limit=10)
```

curl 形态：

```bash
curl https://api.openai.com/v1/batches?limit=10 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## 可用模型

Batch API 广泛适用于大多数模型，但并非全部。使用前查模型参考文档确认所用模型支持 Batch API。

## 速率限制

Batch API 的速率限制与各模型现有的速率限制分开，共三种：

1. 单次批处理限制：单个批处理最多 50,000 个请求，输入文件上限 200 MB。`/v1/embeddings` 批处理限整批所有请求合计最多 50,000 个嵌入输入。
2. 每模型排队提示词 token 数限制：每个模型有可排队进行批处理的最大提示词 token 数量，上限在平台设置页面查看。
3. 批处理创建速率限制：每小时最多创建 2,000 个批处理。要提交更多请求，增加每个批处理中的请求数量。

Batch API 目前没有输出 token 限制。速率限制使用全新的专属资源池，不消耗标准各模型速率限制的 token，等于变相扩大了可用的请求数量与 token 处理量。

## 批处理过期

未能及时完成的批处理最终变更为 `expired` 状态：未完成的请求被取消，已完成请求的响应仍可通过输出文件获取，费用只为已完成的请求结算。

已过期的请求写入错误文件，可用 `custom_id` 检索对应数据：

```text
{"id": "batch_req_123", "custom_id": "request-3", "response": null, "error": {"code": "batch_expired", "message": "This request could not be executed before the completion window expired."}}
{"id": "batch_req_123", "custom_id": "request-7", "response": null, "error": {"code": "batch_expired", "message": "This request could not be executed before the completion window expired."}}
```

> 包内互引：评估场景的批处理用法见 claude-develop-tests.md 与 openai-eval-best-practices.md；同一厂商异步降本的对照形态见 claude-message-threads.md（对话只发一次）与 ds-kv-cache.md（前缀缓存）。

# DeepSeek 上下文硬盘缓存与多轮对话（KV Cache & Multi-round Chat）

- 原文：[上下文硬盘缓存](https://api-docs.deepseek.com/zh-cn/guides/kv_cache)、[多轮对话](https://api-docs.deepseek.com/zh-cn/guides/multi_round_chat)
- 来源：DeepSeek 官方 API 文档
- 发布：官方文档页，随 DeepSeek 版本持续更新
- 译文说明：原文为中文，本篇为按本包语言规则的合规改写整理，术语保留英文原词；两页官方文档合为一篇。

DeepSeek API 的上下文硬盘缓存技术对所有用户默认开启，无需修改代码即可享用。

用户的每一个请求都会触发硬盘缓存的构建。若后续请求与之前的请求在前缀上存在重复，重复部分只需要从缓存中拉取，计入「缓存命中」。

## 缓存写入与命中规则

缓存命中的前提是相应前缀已被写入硬盘缓存。受 Sliding Window Attention 机制的影响，缓存前缀的存取与判别与之前有所不同。每条缓存前缀是一个独立的完整单元。后续请求只有在完整匹配缓存前缀单元时，才能命中缓存。

缓存前缀写入时机：

1. 请求结束位置写入：每次请求的用户输入结束位置与模型输出结束位置，会产生两个缓存前缀单元。后续请求若完整匹配它们，则可命中。
2. 公共前缀检测写入：当系统检测到多次请求之间存在公共前缀时，会将该公共前缀作为一个独立的缓存前缀单元写入。后续请求若完整复用该缓存前缀单元，则可命中。
3. 按固定 token 间隔写入：在长输入或长输出中，系统会以一定的 token 数量为间隔，截取缓存前缀单元，避免长前缀因迟迟未达到结束位置而完全无法被缓存。

举例 1：用户第一轮请求内容为 `A + B`，第二轮请求内容为 `A + B + C`，则第二轮请求能完整匹配 `A + B` 这个缓存前缀单元，可以命中 `A + B` 的缓存。详见下文例一。

举例 2：用户第一轮请求的内容为 `A + B`，第二轮请求的内容为 `A + C`，则第二轮请求无法命中缓存，因为 `A + C` 不能完整匹配第一轮的缓存前缀单元（`A + B`）。但此时系统会识别到两轮请求存在公共前缀 `A`，并将 `A` 作为缓存前缀单元写入。当第三轮请求 `A + D` 到来时，能完整匹配 `A` 这个缓存前缀单元，可以命中 `A` 的缓存。详见下文例二。

### 例一：多轮对话

第一次请求：

```text
messages: [
    {"role": "system", "content": "你是一位乐于助人的助手"},
    {"role": "user", "content": "中国的首都是哪里？"}
]
```

第二次请求：

```text
messages: [
    {"role": "system", "content": "你是一位乐于助人的助手"},
    {"role": "user", "content": "中国的首都是哪里？"},
    {"role": "assistant", "content": "中国的首都是北京。"},
    {"role": "user", "content": "美国的首都是哪里？"}
]
```

在上例中，第二次请求可以完整复用第一次请求的缓存前缀单元，这部分会计入缓存命中。

### 例二：长文本问答

第一次请求：

```text
messages: [
    {"role": "system", "content": "你是一位资深的财报分析师..."},
    {"role": "user", "content": "<财报内容>\n\n请总结一下这份财报的关键信息。"}
]
```

第二次请求：

```text
messages: [
    {"role": "system", "content": "你是一位资深的财报分析师..."},
    {"role": "user", "content": "<财报内容>\n\n请分析一下这份财报的盈利情况。"}
]
```

第三次请求：

```text
messages: [
    {"role": "system", "content": "你是一位资深的财报分析师..."},
    {"role": "user", "content": "<财报内容>\n\n请分析一下公司收入与支出占比。"}
]
```

在上例中，前两次请求不会命中缓存。前两次请求完成后，系统会识别出 `system` 消息加 `user` 消息中的财报内容为缓存前缀单元，并进行写入。在第三次请求中，由于完整匹配了前面写入的缓存前缀单元，则可命中缓存。

## 查看缓存命中情况

在 DeepSeek API 的返回中，`usage` 字段里有两个字段反映请求的缓存命中情况：

1. `prompt_cache_hit_tokens`：本次请求的输入中，缓存命中的 tokens 数。
2. `prompt_cache_miss_tokens`：本次请求的输入中，缓存未命中的 tokens 数。

## 硬盘缓存与输出随机性

硬盘缓存只匹配到用户输入的前缀部分，输出仍然是通过计算推理得到的，仍然受到 temperature 等参数的影响，从而引入随机性。其输出效果与不使用硬盘缓存相同。

## 其它说明

1. 缓存系统是「尽力而为」，不保证 100% 缓存命中。
2. 缓存构建耗时为秒级。缓存不再使用后会自动清空，时间一般为几个小时到几天。

## 多轮对话：无状态拼接是缓存的前提

DeepSeek `/chat/completions` API 是「无状态」API：服务端不记录用户请求的上下文，用户在每次请求时，需将之前所有对话历史拼接好后，传递给对话 API。这正是硬盘缓存能命中的前提——第二轮请求完整包含第一轮的输入与输出，前缀重复的部分才可能从缓存拉取。

Python 代码示例如下：

```python
from openai import OpenAI
client = OpenAI(api_key="<DeepSeek API Key>", base_url="https://api.deepseek.com")

# Round 1
messages = [{"role": "user", "content": "What's the highest mountain in the world?"}]
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
)

messages.append(response.choices[0].message)
print(f"Messages Round 1: {messages}")

# Round 2
messages.append({"role": "user", "content": "What is the second?"})
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
)

messages.append(response.choices[0].message)
print(f"Messages Round 2: {messages}")
```

第一轮请求时，传递给 API 的 `messages` 为：

```json
[
    {"role": "user", "content": "What's the highest mountain in the world?"}
]
```

第二轮请求时：先把第一轮中模型的输出添加到 `messages` 末尾，再把新的提问添加到 `messages` 末尾，最终传递给 API 的 `messages` 为：

```json
[
    {"role": "user", "content": "What's the highest mountain in the world?"},
    {"role": "assistant", "content": "The highest mountain in the world is Mount Everest."},
    {"role": "user", "content": "What is the second?"}
]
```

这个拼接纪律与本文第一节的多轮对话命中例子一一对应：`messages` 按时间顺序只增不改，每轮新增的内容在末尾追加，前缀保持完全一致，缓存前缀单元才能完整匹配。


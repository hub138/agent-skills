# DeepSeek JSON Output：严格 JSON 输出（JSON Output）

- 原文：[JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode)
- 来源：DeepSeek 官方 API 文档
- 发布：官方文档页，随 DeepSeek 版本持续更新
- 译文说明：原文为中文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。

在很多场景下，用户需要让模型严格按照 JSON 格式输出，实现输出的结构化，便于后续逻辑解析。DeepSeek 提供 JSON Output 功能，确保模型输出合法的 JSON 字符串。

## 注意事项

1. 设置 `response_format` 参数为 `{'type': 'json_object'}`。
2. 用户传入的 system 或 user prompt 中必须含有 `json` 字样，并给出希望模型输出的 JSON 格式样例，指导模型输出合法 JSON。
3. 合理设置 `max_tokens` 参数，防止 JSON 字符串被中途截断。
4. 使用 JSON Output 功能时，如果模型的输出无法被识别为 JSON，API 会把其中的非 JSON 内容替换为空格（U+0020），返回的 `content` 可能仅包含空格（看起来为空，此时 `finish_reason` 仍可能是 `stop`）。可以修改 prompt 缓解此类问题，并在代码中对空的 `content` 做兜底处理（例如重试请求）。

## 样例代码

使用 JSON Output 功能的完整 Python 代码：

```python
import json
from openai import OpenAI

client = OpenAI(
    api_key="<your api key>",
    base_url="https://api.deepseek.com",
)

system_prompt = """
The user will provide some exam text. Please parse the "question" and "answer" and output them in JSON format. 

EXAMPLE INPUT: 
Which is the highest mountain in the world? Mount Everest.

EXAMPLE JSON OUTPUT:
{
    "question": "Which is the highest mountain in the world?",
    "answer": "Mount Everest"
}
"""

user_prompt = "Which is the longest river in the world? The Nile River."

messages = [{"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}]

response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    response_format={
        'type': 'json_object',
    },
)

print(json.loads(response.choices[0].message.content))
```

模型输出：

```text
{
    "question": "Which is the longest river in the world?",
    "answer": "The Nile River"
}
```

> 包内互引：JSON Output 只是输出格式约束，与思考模式的开关无关，两参数可叠加使用，见 ds-thinking-mode.md；结构化输出的评估侧用法见 claude-develop-tests.md 的精确匹配评估示例。

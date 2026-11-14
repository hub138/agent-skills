# DeepSeek 思考模式：开关、强度与多轮拼接（Thinking Mode）

- 原文：https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
- 来源：DeepSeek（官方 API 文档）
- 发布：官方文档页，随 DeepSeek 版本持续更新
- 译文说明：全文翻译，术语保留英文原词，代码块与命令保持英文原文。

DeepSeek 模型支持思考模式：在输出最终回答之前，模型先输出一段思维链内容，以提升最终答案的准确性。

## 思考模式开关与思考强度控制

| 控制目标 | OpenAI 格式 | Anthropic 格式 | Responses API 格式 |
|---|---|---|---|
| 思考模式开关 | `{"thinking": {"type": "enabled/disabled"}}` | `{"reasoning": {"effort": "none/low/high/max"}}`（none 表示关闭思考模式） | `{"thinking": {"type": "enabled/disabled"}}` |
| 思考强度控制 | `{"reasoning_effort": "low/high/max"}` | `{"output_config": {"effort": "low/high/max"}}` | `{"reasoning_effort": "low/high/max"}` |

思考模式默认打开，且 effort 默认为 `high`。

用户设置的 effort 与模型推理 effort 的映射表如下：

| 请求传入 effort | 实际映射 effort |
|---|---|
| minimal | low |
| low | low |
| medium | high |
| high | high |
| xhigh | high |
| max | max |
| ultra | max |

```python
response = client.chat.completions.create(
    model="deepseek-flash",
    # ...
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
```

## 输入输出参数

思考模式不支持 `temperature`、`presence_penalty`、`frequency_penalty` 参数。为了兼容已有软件，设置这些参数不会报错，但也不会生效。

`top_p` 的行为因模型而异：

**`deepseek-flash`**：仅在思考模式下生效，有效取值范围为 `0.95`–`1.0`，低于 `0.95` 的取值会按 `0.95` 处理。在非思考模式下，该参数恒为 `1.0`，传入的值会被忽略。

**`该推理模型`**：思考模式下会忽略传入值（启用工具调用时固定为 `0.95`，否则为 `1.0`）；非思考模式下生效。即使提供了 `tools`，将 `tool_choice` 设为 `none` 也会关闭工具调用。

在思考模式下，思维链内容通过 `reasoning_content` 参数返回，与 `content` 同级。在后续轮次的请求中，`reasoning_content` 是否需要回传、是否会被拼接进上下文，取决于请求是否携带 `tools` 参数：

若请求**携带 `tools` 参数**：历史轮次的 `reasoning_content` 均应回传给 API，并会被拼接进上下文。详见[工具调用](https://api-docs.deepseek.com/zh-cn/guides/tool_calls)。

若请求**未携带 `tools` 参数**：`reasoning_content` 无需回传；即使传入 API，也会被忽略，不会拼接进上下文。详见[多轮对话拼接](#多轮对话拼接)。

## 多轮对话拼接

在每一轮对话过程中，模型会输出思维链内容（`reasoning_content`）和最终回答（`content`）。如果请求未携带 `tools` 参数，则在下一轮对话中，之前轮输出的思维链内容不会被拼接到上下文中。

### 样例代码

下面的代码以 Python 语言为例，展示了如何访问思维链和最终回答，以及如何在多轮对话中进行上下文拼接。

```python
from openai import OpenAI

client = OpenAI(api_key="<DeepSeek API Key>", base_url="https://api.deepseek.com")

# Turn 1
messages = [{"role": "user", "content": "9.11 and 9.8, which is greater?"}]
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
reasoning_content = response.choices[0].message.reasoning_content
content = response.choices[0].message.content

# Turn 2
# The reasoning_content will be ignored by the API
messages.append(response.choices[0].message)
messages.append({'role': 'user', 'content': "How many Rs are there in the word 'strawberry'?"})
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
# ...
```

流式版本同理，把 `chunk.choices[0].delta.reasoning_content` 累加得到思维链内容：

```python
from openai import OpenAI

client = OpenAI(api_key="<DeepSeek API Key>", base_url="https://api.deepseek.com")

# Turn 1
messages = [{"role": "user", "content": "9.11 and 9.8, which is greater?"}]
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    stream=True,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
reasoning_content = ""
content = ""
for chunk in response:
    if chunk.choices[0].delta.reasoning_content:
        reasoning_content += chunk.choices[0].delta.reasoning_content
    else:
        content += chunk.choices[0].delta.content

# Turn 2
# The reasoning_content will be ignored by the API
messages.append({"role": "assistant", "reasoning_content": reasoning_content, "content": content})
messages.append({'role': 'user', 'content': "How many Rs are there in the word 'strawberry'?"})
response = client.chat.completions.create(
    model="deepseek-flash",
    messages=messages,
    stream=True,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
# ...
```

## 工具调用

DeepSeek 模型的思考模式支持工具调用功能。模型在输出最终答案之前，可以进行多轮的思考与工具调用，以提升答案的质量。

请注意，携带了 `tools` 参数的请求，在后续所有请求中，必须完整回传 `reasoning_content` 给 API——即使该轮模型未实际进行工具调用。若你的代码中未正确回传 `reasoning_content`，API 会返回 400 报错。正确回传方法参考下面的样例代码。

### 样例代码

```python
import os
import json
from openai import OpenAI
from datetime import datetime

# The definition of the tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "Get the current date",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather of a location, the user should supply the location and date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city name"},
                    "date": {"type": "string", "description": "The date in format YYYY-mm-dd"},
                },
                "required": ["location", "date"],
            },
        },
    },
]

# The mocked version of the tool calls
def get_date_mock():
    return datetime.now().strftime("%Y-%m-%d")

def get_weather_mock(location, date):
    return "Cloudy 7~13°C"

TOOL_CALL_MAP = {
    "get_date": get_date_mock,
    "get_weather": get_weather_mock,
}

def run_turn(turn, messages):
    sub_turn = 1
    while True:
        response = client.chat.completions.create(
            model='deepseek-flash',
            messages=messages,
            tools=tools,
            reasoning_effort="high",
            extra_body={ "thinking": { "type": "enabled" } },
        )
        messages.append(response.choices[0].message)
        reasoning_content = response.choices[0].message.reasoning_content
        content = response.choices[0].message.content
        tool_calls = response.choices[0].message.tool_calls
        print(f"Turn {turn}.{sub_turn}\n{reasoning_content=}\n{content=}\n{tool_calls=}")
        # If there is no tool calls, then the model should get a final answer and we need to stop the loop
        if tool_calls is None:
            break
        for tool in tool_calls:
            tool_function = TOOL_CALL_MAP[tool.function.name]
            tool_result = tool_function(**json.loads(tool.function.arguments))
            print(f"tool result for {tool.function.name}: {tool_result}\n")
            messages.append({
                "role": "tool",
                "tool_call_id": tool.id,
                "content": tool_result,
            })
            sub_turn += 1
        print()

client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url=os.environ.get('DEEPSEEK_BASE_URL'),
)

# The user starts a question
turn = 1
messages = [{
    "role": "user",
    "content": "How's the weather in Hangzhou Tomorrow",
}]
run_turn(turn, messages)

# The user starts a new question
turn = 2
messages.append({
    "role": "user",
    "content": "How's the weather in Guangzhou Tomorrow",
})
run_turn(turn, messages)
```

`run_turn` 循环体演示了完整的执行流程：模型先输出思维链与工具调用请求，客户端执行工具后把结果以 `role: "tool"` 消息回传，直到某轮模型不再请求工具调用（`tool_calls is None`），该轮的 `content` 即最终回答。整个过程中每条 assistant 消息都通过 `messages.append(response.choices[0].message)` 回传，因此 `reasoning_content` 始终保留在消息里。

输出示例展示了 Turn 1.1 到 Turn 2.2 的完整交替：模型先推理「需要先取日期再查天气」，工具返回后继续推理并输出最终天气预报。且在 Turn 2 的请求中，仍然携带着 Turn 1 所产生的 `reasoning_content` 给 API。

对于需要把消息序列化存储的场景（例如自建消息存储），官方示例在 `messages.append(response.choices[0].message)` 与显式构造 `{"role": "assistant", "content": ..., "reasoning_content": ..., "tool_calls": ...}` 两种写法之间展示了等价性：只要 `reasoning_content` 与 `tool_calls` 字段保留在消息对象上，两种写法回传给 API 后行为一致。

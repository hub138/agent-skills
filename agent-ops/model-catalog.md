# 模型与调用频率总览（codebuddy + knot 双通道，2026-11-12 实测）

> **使用红线（用户 2026-11-12，严格）**：用量很大，**只允许 x0.00 和 ≤0.15 credits**。> 其余（含 0.19 的 `glm-5.3-flashx`、`minimax-m2.7-ioa`）**一律不用**；> 代码层用 `assert_cb_model_allowed()` 在发请求前拦掉，不依赖 429 自动回落（回落可能落到贵模型，更贵）。

> 来源：本机 codebuddy `/model` 列表，按 credits 倍率排序整理。credits 是**相对倍率**，不是绝对价格；x0.00 即不扣费。
> **口径只看这张表，不要用 `--help` 的列表判断免费与否**——help 会混列全部付费模型，也不标注倍率。
> 命名规则：`-ioa` 后缀是 **codebuddy CLI** 的 ID；**knot-cli 不能用带 `-ioa` 的名字**，要用不带后缀的（`free-model` / `small-model` / `glm-5.3` / `deepseek-v4-flash`）。

## 零、一屏看懂：哪些免费、怎么调、撞限流怎么办

| 通道 | 免费（x0.00 / 实测扣费 0） | 便宜档（≤0.15，可用不默认） | 默认 | 限流形态 | 429 恢复 |
|---|---|---|---|---|---|
| **codebuddy CLI** | `free-model`（主力）、`free-model-flash`、`small-model`、`echo`（特殊用途） | `gpt-6-luna` x0.07、`glm-5.3-flash-ioa` x0.08、`minimax-m3.1-flash` x0.08、`deepseek-v4.1-flash` x0.11 等 | `free-model` | 额度 429 **带「将在 <时刻> 重置」通知** | 整模型冷却到通知时刻、持久化，到期自动回归，其它模型继续 |
| **knot-cli** | `free-model`、`small-model`、`free-model-preview`；`glm-5.3`、`glm-5.3-flash`、`deepseek-v4-flash` 实测扣费也是 0 | 同上按平台口径 | `free-model` | 全局速率/并发限流，**没有恢复时间通知** | AIMD 降并发 + 指数静默 60/120/240/480s，连续 5 次成功才 +1 路 |

**免费 ≠ 无限**：knot 侧对「单个智能体 / 人+模型粒度 / 单模型」都有速率与天级上限，具体数字见 `knot-limits.md` 第一节（以官方说明为准）；codebuddy 侧按 credits 与额度通知走。两条通道的 429 恢复逻辑**不能混用**。

**调用频率与并发策略**（详见 `knot-limits.md` 第三、七节）：

- 每模型最多 **2 路**、多模型合计全局上限 **10**；是本项目内部量，不做全局配额推演（`MTR_KNOT_GLOBAL_MAX` 默认 0 关闭）。
- 默认只用 free-model（knot 侧 `free-model` / codebuddy 侧 `free-model`）；small-model 偏弱不进默认池，要用显式配 `MTR_KNOT_MODELS` / `<业务环境变量>` / `SUPERVISOR_MODEL`。
- 角色只有两个：干活 worker + 管理者（manager），都默认 free-model、都可配（见 `SKILL.md` 第一屏「模型安排」）。
- >0.15 credits 的模型禁用；分层清单与 ID 对应关系见下（第一~八节）。

## 一、免费（x0.00，不扣费）

| ID | 说明 |
|---|---|
| `free-model` | 混元旗舰，960K 输入；**codebuddy 侧最常用**，对应 knot 侧 `free-model` |
| `free-model-flash` | 混元旗舰的 flash 开发版，x0.00 |
| `small-model` | 混元上一代，编码/前端/办公；**注意它也免费**，不要因为它带 `-ioa` 就当成付费 |
| `echo` | Echo 专用 agent 工作流模型（特殊用途，一般不用于通用对话） |

> 用户口径「**codebuddy 只有 hy 免费**」与上表一致：除 `echo` 外，x0.00 的都是 hy 系列。**knot 侧本项目只用 `free-model` / `small-model`**（实测扣费 0）。

## 二、允许的便宜档（≤0.15；可用但不做默认）

| ID | credits | 特点 |
|---|---|---|
| `gpt-6-luna` | x0.07 | OpenAI 最轻量，高吞吐短任务 |
| `glm-5.3-flash-ioa` | x0.08 | Z.ai 原生多模态，**识图首选**，约 20s |
| `minimax-m3.1-flash` | x0.08 | 多模态，办公/agent/编码，推理速度快 |
| `deepseek-v4.1-flash` | x0.11 | DeepSeek 原生多模态，1M 上下文 |
| `mimo-v2.6-pro` | x0.13 | 小米，推理/研究类 |
| `gpt-5.6-luna` | x0.14 | 轻量快速 |

这一档是「**不免费但足够便宜**」的可用选项：需要多模态识图（hy 系列不行）或需要比 hy 更快的短任务时，优先用这一档，不要直接上 `claude-*` / `gpt-6-astra`。

## 三、禁用（>0.15，红线外）

| ID | credits |
|---|---|
| `glm-5.3-flashx` | x0.19 |
| `minimax-m2.7-ioa` | x0.19 |
| `minimax-m3-ioa` | x0.25 |
| `claude-haiku-5.5` | x0.33 |

## 四、禁用（0.5~0.8，红线外）

| ID | credits |
|---|---|
| `deepseek-v4-pro-ioa` | x0.51 |
| `glm-5.3-ioa` | x0.69 |
| `kimi-k2.8-preview` | x0.77 |
| `glm-5.2-ioa` | x0.79 |
| `glm-5.2-internal-ioa` | x0.79 |

## 五、禁用（0.9~1.7，红线外）

| ID | credits |
|---|---|
| `kimi-k3.1-pro` | x0.97 |
| `gemini-3.5-flash` | x0.99 |
| `gemini-3.1-pro` | x1.32 |
| `claude-sonnet-5` | x1.33 |
| `claude-sonnet-5-1m` | x1.33 |
| `claude-sonnet-5.5` | x1.33 |
| `gpt-6.1-sol` | x1.33 |
| `gpt-6-sol` | x1.33 |
| `gpt-5.6-terra` | x1.39 |
| `kimi-k3.1-pro-highspeed` | x1.56 |
| `kimi-k3-ioa` | x1.62 |

## 六、禁用（≥2.0，绝对不用）

| ID | credits |
|---|---|
| `claude-sonnet-4.6` | x2.00 |
| `claude-opus-5.5` | x2.17 |
| `claude-opus-5` | x3.33 |
| `claude-opus-4.8-1m` | x3.33 |
| `claude-opus-4.7-1m` | x3.33 |
| `claude-opus-4.6-1m` | x3.33 |
| `gpt-5.6-sol` | x3.47 |
| `gpt-6-astra` | x6.67 |

## 七、怎么选（按场景，不按「最强」）

> **本项目（业务项目）默认只用 `free-model`（small-model 偏弱、不默认），每模型最多 2 路、全局上限 10**，不做全局配额推演。下面这张表是给「需要便宜多模态/更快短任务」的其它场景用的。



| 场景 | 选 |
|---|---|
| 批量代码对比 / 判定 / 长跑队列 | **`free-model`（免费，每模型 2 路）**，本项目默认；small-model 偏弱不默认 |
| 需要识图 | `glm-5.3-flash-ioa`（x0.08，允许）；`glm-5.3-flashx` x0.19 **禁用** |
| 短任务高吞吐、想比 hy 快 | `gpt-6-luna`（x0.07）、`minimax-m3.1-flash`（x0.08） |
| 长上下文代码理解且愿付费 | `deepseek-v4.1-flash`（x0.11，1M）、`deepseek-v4-pro-ioa`（x0.51） |
| 复杂 agentic 编码 | **禁用**（`claude-sonnet-5.5` x1.33、`gpt-6.1-sol` x1.33 均超红线）；先用 `free-model` |
| **绝对禁用** | `claude-opus-*`（x2.17~3.33）、`gpt-6-astra`（x6.67）、`gpt-5.6-sol`（x3.47） |

## 八、与 knot 的对应关系

| knot-cli（不带 `-ioa`） | codebuddy CLI | 是否免费 |
|---|---|---|
| `free-model` | `free-model` | 都免费（各自通道） |
| `small-model` | `small-model` | 都免费 |
| `free-model-preview` | `free-model-preview` | 都免费 |
| `glm-5.3` | `glm-5.3-ioa` | knot 侧实测扣费 0；codebuddy 侧 x0.69 |
| `glm-5.3-flash` | `glm-5.3-flash-ioa` | knot 侧扣费 0；codebuddy 侧 x0.08 |
| `deepseek-v4-flash` | `deepseek-v4.1-flash` | knot 侧扣费 0；codebuddy 侧 x0.11 |

**关键区别**：knot 侧这些 ID 实测扣费 0（走公司免费额度），但受全局速率/并发限流、**没有恢复时间通知**；codebuddy 侧只有 hy 系列 x0.00，其它按 credits 计费，但**有明确的重置时间通知**、不受 knot 全局池影响。两条通道的限流处理不能混用，见 `knot-limits.md`。

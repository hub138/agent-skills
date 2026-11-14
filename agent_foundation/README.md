# agent_foundation · Agent 工程的地基

> 一本书、一套代码、一道红线。把「怎么把 agent 做得可靠」这件事，从零散经验沉淀成可查阅的知识、可复用的代码、可执行的门禁。

任何一个准备认真做 agent 的团队，都会在同一批问题上反复交学费：会话断了怎么续、输出变形怎么判、磁盘写满怎么防、并发撞限流怎么退、记忆怎么不丢原件、上线前怎么知道它真的行。`agent_foundation` 把这些问题一次讲清、一次做对。

## 四件东西

### 一、知识库 —— `docs/`

72 篇公开工程文档的结构化整理，按主题归位：

- **官方一手资料**：Anthropic（agent 设计、上下文工程、工具编写、技能、评测、沙箱、记忆工具）、OpenAI（Agents SDK、编排、评测最佳实践、批处理、限流）、Google（agent 质量、会话与记忆、工具与 MCP、原型到生产）、DeepSeek（工具调用、思考模式、KV cache、JSON 输出）。
- **工程模式**：长任务 harness、多智能体协调、harness 动态工作流、代理源码控制、HTML 制品、代码执行 MCP。
- **安全与评测**：trustworthy agents、agent 安全、沙箱化、评测设计、未知量处理。

不是链接合集——每篇提炼过结构、术语与可直接抄的结论。

### 二、工程指南 —— `GUIDE.md`

22 章，按 agent 的**一次完整生命周期**排列：跑起来 → 听懂输出 → 断线续跑 → 判断失败 → 管住资源 → 组织并发 → 对外通信 → 形成记忆 → 检索资料 → 设计工具 → 管好上下文 → 留下证据 → 干净收尾 → 放行发布 → 知道自己做得好不好。

三条使用路径：

- **按症状反查** → 第 19 章反模式表（「看到什么、改什么」）
- **按能力速查** → 第 18 章速查表
- **直接抄代码** → 第 21 章骨架，四种项目原型各给一条取用路线（批量跑任务 / 单会话长任务 / 多智能体验证 / 内部工具接入）

> 素材来源：五个真实 agent 工程在同一批问题上反复付出的代价。**每条机制背后至少有一次真实故障。**

总纲只有一句：**agent 的可靠性来自「假设一切会断」的设计立场。** 模型会超时、进程会卡住、磁盘会写满、消息会重复、输出会变形、人会在一半时改配置——下面每一章的机制，都是对其中一种「断」的正面回答。

### 三、原语库 —— `src/agent_foundation/`

37 个模块，**零运行时依赖，纯标准库**，每个可独立取用：

| 关注点 | 模块 |
|---|---|
| 会话与恢复 | `snapshot`、`recovery`、`cache_lease`、`cli_session`、`workspace_lifecycle` |
| 账本与幂等 | `idempotency`、`campaign`、`convoy`、`atomic_json` |
| 预算与护栏 | `budget`、`disk_budget`、`environment_guard`、`prefilter` |
| 风控与准入 | `risk_gate`、`admission`、`protocol`、`provider_failure` |
| 谱系与证据 | `lineage`、`genealogy`、`evidence`、`execution_receipt`、`transcript` |
| 记忆与经验 | `memory`、`file_memory`、`experience`、`iteration_loop`、`context` |
| 对外通信 | `webhook`、`notify_cadence`、`events`、`metrics` |
| 资源与并发 | `resource_pool`、`probe`、`advisory`、`artifacts`、`content` + `adapters/` |

```bash
cd agent_foundation
pip install -e .
python3 -m pytest tests/ -q
```

### 四、开源隐私闸门 —— `tests/test_privacy.py`

对包内**任何文件**零容忍内部路径、内网域名、内部模型代号和密钥——一条测试代替人的记性。

这道纪律本身就是从真实学费里抽象出的通用能力：任何准备开源自己 agent 基建的人，都会撞上同一批泄漏路径。`GUIDE.md` 第 22 章把它讲成一个可复用的发布前检查。

## 边界

- 这里是**通用原语与通用知识**，不绑定任何具体框架、模型供应商或云厂商。
- 每个模块都能单独取用；不需要为了用一个 `snapshot` 而接受整套架构。
- 只声明验证过的能力：模块有单测覆盖，指南里的每条结论都能追到一次真实故障或一份公开一手资料。

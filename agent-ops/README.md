# agent-ops — 一个智能体，管一支 AI 团队

> 你说一句目标，一群 CLI 子智能体去干活；一个 AI 管理者替你盯着、纠正、推进，
> 甚至在发现新方向时调整任务目标。断了自动续，卡了自动管，全程可追溯——你只在
> 真正需要拍板时出现。

## 这是什么

`agent-ops` 是一个跑在本机、面向命令行智能体（Claude Code / Codex / CodeBuddy 等）的
**多 agent 编排与运维系统**。它回答三个所有人都会撞上的问题：

1. **盯不过来**——3 个子任务还能守着看，10 个呢？→ 管理者（AI）替你看。
2. **断了就废**——长任务跑到一半进程死了/会话没了/上下文满了？→ 断点续跑 + 假死自愈。
3. **上下文爆炸**——读 3 个任务的日志 ≈ 撑爆一次窗口？→ 子任务把结论写进 5 个字段，
   主 agent 只读摘要，细节留在磁盘上随取随查。

它不是框架，不装服务，不用 Docker——**纯 Python 3.10+ 标准库 + 一份 SQLite 文件**，
拷进技能目录就能用。

## 能做什么（全部有实测数字）

| 能力 | 一句话 | 实测 |
|---|---|---|
| 任务队列 | 几十万任务 = 几十万行，不是几十万进程 | 10 万行插入 0.7s；取任务 **0.09ms** |
| 一句话派活 | `add --goal` / `plan --goal`，提示词模板自动渲染 | 一句话拆出 3 个带交付物的任务 |
| 管理者 | AI 读全部进度，纠正/推进/**微调目标**，决策全部留痕 | 真实识别"重复报错死循环"并给出换策略指令 |
| 断点续跑 | 进度落盘 + 压缩留痕，重试自动带"上次为什么失败" | 跑一半杀掉 → 新会话从断点继续 |
| 假死自愈 | 文件 900s 无增长 ≠ 立刻杀——标记后由管理者模型判断 | 误杀率 0（reasoning 阶段不误判） |
| 死士巡检 | 健康检查的健康检查：进程/数据库/日志/通知链路全客观事实 | 生产 cron 长期运行，误报实战修复 |
| 主动挂起 | `suspend` 腾出额度，`resume` 从断点回来，不耗重试次数 | 挂起期间不参与调度 |
| 限流自适应 | 区分两类 429，AIMD 降并发+指数静默，恢复后自动回升 | 假绿灯故障注入被拦截 |

架构与 [google/ax](https://github.com/google/ax)（Google 的 agent 编排运行时）同构：
状态进数据库、轮询调度、任务不可变、原文留盘——它是集群级，本 skill 是单人可维护的单机形态。

## 5 分钟上手

```bash
T=<本目录>/scripts/taskctl.py

# 1) 派活：一句话，不用写提示词
python3 $T plan --goal "审查这个代码库：构建、测试覆盖、安全" --repo /data/project

# 2) 无人值守：队列调度 + 管理者上线
python3 $T daemon --concurrency 2 --interval 30 &
python3 <本目录>/scripts/manager.py daemon --interval 300 &

# 3) 你只需要看这三个
python3 $T stats                 # 全部任务，每行一个
python3 $T brief <任务名>         # 结果摘要（5 个字段）
python3 $T history <任务名>       # 全史：做了什么、为什么、管理者怎么判断的
```

需要智能体 CLI（如 `codebuddy`，模型可配置）真正执行子任务；队列、监督、留痕本身零依赖。

### 你只给一个目标，就够了

`--goal` 后面跟**一句人话**即可，不需要写提示词、不需要懂任务类型、不需要列步骤：

```bash
python3 $T plan --goal "给这个服务补一组回归测试，覆盖超时和重试" --repo /data/project
python3 $T plan --goal "找出上周发版后偶发 502 的原因，给出可复现步骤" --repo /data/project
```

`plan` 会把这句话拆成若干带**交付物**的具体任务，渲染到 `templates/tasks/` 的模板里；
`manager.py` 会在读到进度后继续微调目标、纠正跑偏、把决策全部写进 `history`。

目标写得好不好，只影响一件事：**AI 能不能判断「什么叫做完」**。
所以写目标时带上你真正在意的那个结果（「有可复现步骤」「有前后对照」「有未覆盖项清单」），
比堆规则清单有用得多。实测：只发「13 条铁律」而不讲因果和完成判据的子任务，
会在只差一次文件拷贝的状态下空转 3 小时（见 `FIELD-NOTES.md` 第 31 条）。
模板里已经内置了「讲因果 / 完成判据 / 降级也是合格交付 / 别无限自检」的引导，
**人给目标、AI 拆任务、AI 自己判断收工**，这条链路是默认行为，不需要额外参数。

## 命令速查

| 命令 | 干什么 |
|---|---|
| `taskctl add --goal "..."` / `plan --goal "..."` | 派活（一句/自动拆解） |
| `taskctl list / stats / brief / history` | 看状态 / 结果摘要 / 任务全史 |
| `taskctl suspend / resume / retry / cancel <任务>` | 挂起 / 恢复 / 重试 / 取消 |
| `taskctl daemon / tick` | 无人值守调度（30s 一轮） |
| `agentctl dispatch / resume / send` | 交互式派发与续接单个 agent |
| `manager.py snapshot / once / daemon` | 管理者：只看快照 / 跑一轮 / 常驻 |
| `deadman.py --config <json>` | 死士巡检（异常才通知，正常只写日志） |
| `selfcheck.py` | 体检本 skill 全部能力是否在岗 |
| `doccheck.py` | 文档数字与代码事实对账（测试数 / 条数 / 文件数 / 命令引用） |

## 文档地图（按需深入）

| 文档 | 什么时候读 |
|---|---|
| `SKILL.md` | 给 AI 的完整操作手册（模型安排、CLI 用法、红线、排查口诀） |
| `orchestrator.md` | 编排细节：派发/看护模式、上下文预算、管理者与监督后端 |
| `memory.md` | 上下文工程与记忆：三层记忆、压缩与 rollover、管理者决策留痕 |
| `harness-lessons.md` | 设计对比：9 个开源 harness 横向研究，哪些抄了哪些没抄为什么 |
| `FIELD-NOTES.md` | 实战坑全量记录（每条：现象→根因→修法→验证），条数以 `doccheck.py` 对账为准，改代码前先查 |
| `tests/` | 回归测试，`python3 -m pytest tests/ -q` 一键验证（项数以 `doccheck.py` 对账为准） |

## 边界（诚实版）

**平台**：Linux 与 macOS 都支持，机器类型自动识别（`scripts/platform_util.py`）：
进程探测 Linux 读 `/proc`、macOS/其它用 `ps`；`codebuddy` / `knot-cli` 的二进制路径按
「环境变量 > 候选路径 > PATH」解析，不再写死 `/usr/local/bin`（macOS 实测真路径在
`/opt/homebrew/bin`）。Linux 容器未挂载 `/proc` 时退回 `os.kill`，不把活进程误判成死的；
其它平台探测能力不足时按「未知」保守处理。`pytest tests/ -q` 在 macOS 全量通过，
其中含 linux/macos/other 三分支、模型红线、文档事实自检的专项用例。

- 并发上限是**本项目内部量**（每模型 2 路、多模型全局 10），不做全局配额推算。
- 多机共享同一队列需要换 Postgres（存储层已隔离，SQLite 不适合多机写）。
- 管理者读的是 progress/result 快照，不是全量日志——子任务按模板写进度是刚需（模板已内置）。

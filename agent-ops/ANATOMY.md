# Skill 解剖（ANATOMY）

> **这份文件回答：这个 skill 由什么组成、数据怎么流、改一个文件会碰到谁。**
> 改代码前先在这里定位；流程与门禁看 `GOVERNANCE.md`；踩坑看 `FIELD-NOTES.md`。

---

## 1. 一句话架构

**入口是 `SKILL.md`，执行靠 `taskctl.py`/`agentctl.py`，监督靠 `manager.py` 与两个 `supervise_*` 后端，
客观巡检靠 `deadman.py`，数据落 SQLite + 任务目录，雷达作为独立子功能挂在 `radar/`。**

不装服务、不用 Docker、纯 Python 标准库 + SQLite。唯一的运行前提是机器上有可用的
agent CLI（`codebuddy` / `knot-cli`），且模型在 `scripts/model_policy.py` 的红线内。

---

## 2. 分层（依赖只能向下，不能向上）

| 层 | 文件/目录 | 职责 | 允许依赖 |
|---|---|---|---|
| L0 入口 | `SKILL.md`、`README.md` | 触发词、操作手册、能力承诺 | 只描述，不执行 |
| L1 编排 | `scripts/taskctl.py`、`scripts/agentctl.py` | 队列调度、交互式派发、租约、断点续跑 | L4 |
| L2 监督 | `scripts/manager.py`、`supervise_agents.py`、`supervise_jobs.py`、`supervisor.py`(shim) | 读快照、模型判下一步、执行 continue/nudge/restart/escalate/finish | L1、L4 |
| L3 巡检 | `scripts/deadman.py`、`scripts/selfcheck.py`、`scripts/doccheck.py` | 对健康检查做健康检查；能力在岗核对；文档对账 | L4 |
| L4 基础 | `scripts/model_policy.py`、`scripts/platform_util.py` | 模型红线、跨平台进程/二进制探测 | 无 |
| L5 数据 | `~/.codebuddy/watchdog/`（jobs/state/logs）、`taskctl` 的 SQLite、`radar/state/` | 任务、进度、决策、雷达台账 | 无 |
| L6 治理 | `GOVERNANCE.md`、`ANATOMY.md`、`CHANGELOG.md`、`FIELD-NOTES.md` | 怎么改、改哪里、为什么、踩过什么 | 无 |
| L7 雷达 | `radar/`、`scripts/radar_*.py` | 简报入账、仓库分析、借鉴落地、磁盘清理 | L4、L5、L6 |

---

## 3. 目录树与职责

```
agent-ops/
├── SKILL.md                  # 唯一操作手册（触发词 + 模型安排 + CLI 用法 + 红线）
├── README.md                 # 对外门面：定位、能力表、5 分钟上手、文档地图
├── GOVERNANCE.md             # 开发规范：权威源/分级/流程/门禁/留痕/红线
├── ANATOMY.md                # 本文件：结构、数据流、影响矩阵、外部引用
├── CHANGELOG.md              # 变更历史（每次提交一段，含门禁与回滚）
├── FIELD-NOTES.md            # 实战坑（现象→根因→修法→验证），只增不改
├── memory.md                 # 上下文工程与记忆：三层记忆、压缩、决策留痕
├── orchestrator.md           # 编排细节：派发/看护模式、上下文预算、公开版同步
├── model-catalog.md          # 模型 credits 分层（镜像 model_policy.py，非权威）
├── knot-limits.md            # knot 限流与 AIMD（内部数字不进公开版）
├── knot-concurrency-playbook.md
├── knot-official-limits.md
├── harness-lessons.md        # 9 个开源 harness 的设计对比（抄了/没抄/为什么）
├── dsh-lessons.md            # DeepSeek Harness 经验
├── ai-session-forensics.md   # 会话文件定位与排障
├── codebuddy-cli-notes.md    # codebuddy CLI 行为记录
├── watchdog.md               # 旧版 watchdog 说明（历史参考）
├── orchestrator/             # 编排相关补充材料（如有）
├── scripts/                  # 全部可执行入口，见下表
├── templates/
│   ├── jobs.example.json     # agentctl 长任务配置模板
│   ├── deadman.example.json  # 死士巡检配置模板
│   └── tasks/                # taskctl plan 的任务模板
│       ├── _done-contract.md # 完成判据（每个模板都引用）
│       ├── generic.md / fix-bug.md / research.md
│       ├── reproduce-bug.md / compare-commit.md
├── tests/                    # 回归测试，项数以 doccheck 为准
├── radar/                    # 技术雷达子功能（见第 8 节）
│   ├── README.md             # 使用手册（人 + AI）
│   ├── schema.sql            # 台账 schema
│   ├── prompts/              # 分析/落地提示词（给子 agent 的任务书）
│   ├── intake/               # 每期简报原文（进 git）
│   ├── analyses/             # 逐条深度分析（进 git）
│   ├── applied/              # 落地变更记录（进 git）
│   ├── LEDGER.md             # 台账渲染（进 git，自动生成）
│   └── state/                # sqlite + audit.jsonl + cache（gitignore）
└── scripts/desensitize.py    # 生成公开脱敏版（唯一发布通道）
```

### 脚本一览

| 脚本 | 职责 | 关键约束 |
|---|---|---|
| `taskctl.py` | SQLite 任务队列：add/plan/list/stats/brief/history/suspend/resume/daemon/tick | 租约 `lease_until` + `BEGIN IMMEDIATE` 原子抢占 |
| `agentctl.py` | 交互式派发单个 CLI agent：dispatch/resume/send/status/watch | 二进制走 `resolve_bin`，模型走 `model_policy` |
| `manager.py` | 管理者：读快照 → 模型决策 → 执行/写 guidance | 决策必须留痕；解析失败不动 |
| `supervise_agents.py` | 监督后端：agentctl 会话 | 与 supervisor 同构，共用快照协议 |
| `supervise_jobs.py` | 监督后端：脚本任务（jobs.json） | 同上 |
| `supervisor.py` | 兼容 shim，转发 manager | 不要在此加新逻辑 |
| `deadman.py` | 配置驱动的死士巡检（进程/端口/命令/日志） | 异常才通知，正常只写日志 |
| `selfcheck.py` | 能力是否真的在用 | 只读，不修改状态 |
| `doccheck.py` | 文档数字/导航/权威源对账 | 退出码 1 = 不一致 |
| `desensitize.py` | 生成公开版 | 跳过雷达 state/cache，替换内部词表 |
| `model_policy.py` | 模型红线唯一源 | 其它脚本不得再写一份 |
| `platform_util.py` | 跨平台探测 | 不得直接读 `/proc` |
| `radar_cli.py` | 雷达唯一入口 | 不调模型；确定性与判断分离 |
| `radar_store.py` | 雷达台账（解析/入账/渲染） | 只存路径与结论，不存长文 |
| `radar_workspace.py` | clone/清理 | 只删缓存根内、台账记录的路径 |

---

## 4. 四条运行时链路

**A. 无人值守队列（taskctl）**

```
plan/add --goal → tasks(queued) → daemon tick → 租约抢占 → CLI 子 agent
   → 子 agent 写 progress.md / result.json → tick 收尾 → task_events
   → manager 读快照 → continue/nudge/restart/escalate/finish → guidance.md
```

**B. 交互式长任务（agentctl）**

```
jobs.json → dispatch(会话 id) → 会话 jsonl 边跑边写 → watchdog.sh 每分钟唤醒
   → 看护进程判活（lease/pid/mtime）→ 掉线 resume → 仍不行交 manager
```

**C. 死士巡检（deadman）**

```
cron → deadman.py --config job.json → 逐项 probe（进程/端口/命令/日志/数据库）
   → 全过只写日志 → 异常推送（带判据，不带猜测）
```

**D. 技术雷达（radar）**

```
brief.md / 粘贴文本 → intake（解析入账 + 原文落盘）→ candidates(new)
   → next（原子领取）→ workspace（clone/刷新）→ AI 深读（代码/文章）
   → record（结论 + 报告路径 + 证据坐标）→ applied（改动 + 理由 + 门禁）
   → ledger（渲染 LEDGER.md）→ clean（TTL/容量清理缓存）
```

雷达与 A/B 的关系：雷达**不占用** taskctl 队列，也不调 `manager.py`。它可由人直接在会话里驱动，
也可由 cron 调 `radar_cli.py` 做确定性部分（intake/clean/ledger），判断部分交给一次显式的 AI 会话。

---

## 5. 数据与状态位置

| 数据 | 位置 | 是否进 git |
|---|---|---|
| taskctl 队列 | 默认 `~/.codebuddy/watchdog/state/tasks.db`（可配 `TASKCTL_DB`） | 否 |
| agentctl 配置/日志 | `~/.codebuddy/watchdog/`（`WATCHDOG_HOME` 可覆盖） | 否 |
| 任务进度/结果 | 每个任务工作目录的 `progress.md`、`result.json` | 视项目 |
| 雷达台账 | `radar/state/radar.db` | 否 |
| 雷达审计流 | `radar/state/audit.jsonl` | 否 |
| 雷达 clone 缓存 | `radar/state/cache/`（`RADAR_CACHE` 可覆盖） | 否 |
| 雷达简报原文 | `radar/intake/*.md` | 是 |
| 雷达分析/落地 | `radar/analyses/`、`radar/applied/` | 是 |
| 雷达台账渲染 | `radar/LEDGER.md` | 是（自动生成，勿手改） |

---

## 6. 变更影响矩阵

> 用法：在左列找到你要改的文件，右两列就是你必须同步和必须验证的东西。

| 你改这个 | 必须同步 | 必须验证 / 容易漏 |
|---|---|---|
| `SKILL.md` 触发词或 description | README 能力表；4 个安装副本；公开版 | 用真实问句触发一次；doccheck；frontmatter 仍是合法 YAML |
| `SKILL.md` 命令表 | 对应脚本的 `--help` 与 README 速查 | `doccheck`（会检查 README 引用的脚本是否存在） |
| `scripts/taskctl.py` 调度/租约 | `tests/test_taskctl.py`；SKILL.md 命令表；memory.md 状态机描述 | `pytest`；`taskctl stats`；两个 tick 并发抢占仍唯一 |
| `scripts/agentctl.py` | `tests/test_cli_smoke.py`；`tests/test_platform_util.py` | 真实 `dispatch --dry-run`；JSON 输出可解析 |
| `scripts/manager.py` | `tests/test_manager.py`；memory.md 第十节；SKILL.md 监督段 | 决策 JSON 解析失败时不误杀；guidance 注入下一轮 |
| `scripts/model_policy.py` | `model-catalog.md`；SKILL.md 模型安排；`tests/test_model_policy.py` | 新增模型必须实测可调通，不按 `--help` 列表 |
| `scripts/platform_util.py` | 所有调用点（agentctl/taskctl/manager/deadman） | `pytest tests/test_platform_util.py`；macOS 分支不读 /proc |
| `templates/tasks/*.md` | `doccheck` 要求 `_done-contract.md` 出现在 SKILL.md；`taskctl plan` 渲染 | 用 `plan --goal` 真实渲染一次，确认占位符全被替换 |
| `scripts/deadman.py` | `templates/deadman.example.json`；cron 配置 | `deadman.py --config <真实配置> --dry-run`（若有） |
| `scripts/doccheck.py` | 它自己检查的数字 | 故意写错一个数字，确认退出码 1 |
| `scripts/desensitize.py` | 公开版产物 | 产物中 grep 内部域名/路径/模型代号必须 0 命中；`radar/state` 未进入产物 |
| `radar/*` 新增文件 | `radar/README.md`；`.gitignore`；`desensitize.py` 的 KEEP_SUFFIX/PRIVATE_PREFIXES | `pytest tests/test_radar.py`；`radar_cli.py status --json` |
| `GOVERNANCE.md` / `ANATOMY.md` | 无需同步，但必须与代码事实一致 | 抽查 3 个路径/命令真实存在 |

---

## 7. 外部引用（改之前先查这里有没有人按名字调用）

**cron（机器人真实在跑）**：

```
*/5  * * * *  agentctl.py watch --quiet
*/30 * * * *  supervise_agents.py once
0    * * * *  supervise_jobs.py
0 */2 * * * * deadman.py --config <业务项目>/config/deadman.json
```

结论：`agentctl.py watch`、`supervise_agents.py once`、`supervise_jobs.py`、`deadman.py` 的
CLI 参数属于**外部契约**，改名/改参数必须保留旧写法或同步改 cron。

**安装副本（copy，不是 symlink）**：

- `~/.codebuddy/skills/agent-ops/`
- `~/.claude/skills/agent-ops/`
- `~/.codex/skills/agent-ops/`
- `~/.cursor/skills/agent-ops/`

源目录改动后，这四处**不会自动更新**。同步命令由安装脚本或手工 `rsync` 完成；
同步后至少验证 `SKILL.md` 与 `scripts/` 的 mtime 与源一致。

**公开脱敏版**：`scripts/desensitize.py` → `agent-skills/agent-ops/`，再推送到公开仓库。
公开版不包含：内部域名/路径、内部模型代号、具体限流数字、`desensitize.py` 自身、雷达运行时数据。

---

## 8. 雷达子功能（radar）

### 8.1 它解决什么

技术雷达每天产出简报，但「值得看/略过」是按大众后端工程师的画像判的。
一个**编排系统本身**关心的机制（租约、信封、验证新鲜度、节点编排、清理策略）经常被归入「略过」。
实测：2026-11-15 那期把 LoopForge、agent-runtime、SuperAgent、GCA 四条全判为略过，
而这四条恰好是 agent-ops 最该借鉴的。雷达子功能就是补这个缺口：
**不看别人的推荐位，按自己的问题清单逐条评估，并把评估结果变成可回滚的改动。**

### 8.2 数据流与产物

```
输入：简报 md（tech-radar 的 data/briefs/*.md，或人直接粘贴的文本）
  ↓ radar_cli.py intake
radar/intake/<日期>-<id>.md        原文，进 git
radar/state/radar.db               索引：briefs/candidates/analyses/changes/workspaces
  ↓ next → workspace → AI 深读
radar/analyses/<日期>/<slug>.md    每条：机制、证据、判定、成本、风险
radar/state/cache/<host>/<org>/<repo>   clone（gitignore，TTL 清理）
  ↓ record → applied
radar/applied/<日期>-<slug>.md     改了什么/为什么/没抄什么/门禁/回滚
radar/LEDGER.md                    台账渲染（自动生成）
```

### 8.3 判定口径

| 结论 | 含义 | 后续动作 |
|---|---|---|
| `adopt` | 机制可直接用，单机标准库环境成立 | 最小实现 + 测试 + 变更留痕 |
| `adapt` | 机制成立但要改形态（去掉框架/换成现有抽象） | 同上，且在报告里写清改了什么形态 |
| `skip` | 不适用/成本高于收益/与现有实现重复 | 必须在报告里写「为什么不做」，避免下次重复评估 |

判据顺序：**先问解决不解决本 skill 的真实问题，再问机制能否脱离原框架，最后才看实现难度。**
顺序反过来就会变成「为了借鉴而借鉴」。

### 8.4 磁盘边界

- clone 只在 `RADAR_CACHE`（默认 `radar/state/cache`）下，按 `host/org/repo` 分层。
- 单仓库默认上限 500MB；超限不删，标记 `over_limit`，由 `clean` 处理。
- `clean` 只删**台账里记录过且 resolve 后仍在缓存根内**的路径；缓存根外的目录一律跳过。
- 推荐每天/每周 `radar_cli.py clean --days 3 --max-mb 2000`，并在 `radar_cli.py status` 里看占用。

---

## 9. 新增一个子功能的标准动作

以雷达为例，加子功能必须同时完成：

1. 目录：`<name>/README.md`（权威说明）+ 数据/模板子目录；
2. 入口：`scripts/<name>_cli.py`，`--json` 输出，确定性操作不调模型；
3. 存储：需要查询才上 SQLite；正文一律 md 进 git；运行时数据进 `.gitignore`；
4. 测试：`tests/test_<name>.py`，覆盖解析/幂等/边界（至少 5 项）；
5. 文档：`README.md` 文档地图加一行、`SKILL.md` 加一节或指针、本文件加解剖、`GOVERNANCE` 无需改；
6. 脱敏：`desensitize.py` 的 `KEEP_SUFFIX`/`PRIVATE_PREFIXES` 检查一遍；
7. 台账：`CHANGELOG.md` 记一段，说明为什么加、怎么验证、怎么回滚。

---

## 10. 已知边界（不做的事）

- 不做多机共享队列（SQLite 单写；要共享换 Postgres，存储层已隔离）。
- 不做全局配额推算；并发上限是项目内部量。
- 不用 AI 判断进程是否卡死（mtime/租约是内核事实）；AI 只判断「下一步做什么」。
- 不把上游仓库当依赖引入；雷达只读，不执行其代码、不 vendor 其实现。
- 不追求「把所有借鉴都落地」；`skip` 也是一等结论，写清理由即可。

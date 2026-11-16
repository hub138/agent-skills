# 技术雷达（radar）— agent-ops 的借鉴子系统

> 一句话：**把「今天有什么值得抄」变成一条可追溯的流水线**——简报入账、仓库深读、
> 判定采纳/改造/不抄、落地成带测试的改动、清理磁盘、台账可查。

---

## 1. 为什么存在（不是拍脑袋加的）

2026-11-15 那期技术情报简报把四条判为「略过」：

- `Tencent/LoopForge`（自托管 Agent 交付工作流，四类节点 + 人工门禁）
- `openJiuwen-ai/agent-runtime`（process/docker/k8s 三种部署策略）
- `SuperAgent 实战`（GlobalContextPacket、SaResultEnvelope、单写者+租约）
- `GCA 多 Agent 协作`（单写者、Run ID / Build Digest / Verification Epoch）

判「略过」的理由是「偏编排流程，无性能数据」「新项目通稿」「无复核硬指标」——
**对一个后端读者成立，对 agent-ops 这个编排系统本身不成立。**
雷达的推荐位按大众画像筛，借鉴必须按自己的问题清单筛。这个子功能就是那道自己的筛子。

---

## 2. 三个入口

### 2.1 手上有一期简报（最常用）

```bash
cd <skill 根>

# 直接粘贴的文本
python3 scripts/radar_cli.py intake --file /tmp/brief.md --date 2026-11-16

# tech-radar 仓库里最新一期（需先 clone 到任意目录）
python3 scripts/radar_cli.py intake --from-dir ~/tech-radar --latest
```

`intake` 做三件确定性的事：解析条目、写台账、把原文落盘到 `radar/intake/`。
解析失败不会猜：用 `--dry-run` 看解析结果，或走 `--json-file` 让模型先抽条目。

### 2.2 已经入过账，继续做

```bash
python3 scripts/radar_cli.py status --json     # 还有几条待分析、缓存多大
python3 scripts/radar_cli.py next              # 原子领取下一条
python3 scripts/radar_cli.py workspace --candidate 3   # clone 仓库到缓存
```

### 2.3 直接问 AI（你平时的用法）

> 「看看这期技术雷达有什么可以借鉴的，深入分析，能落地的就落地。」

AI 会按 `prompts/session.md` 执行：先读治理文档 → 入账 → 逐条 triage →
深读（`prompts/analyze-repo.md` / `analyze-article.md`）→ 落地（`prompts/apply-borrowing.md`）
→ 清理 → 汇报。**判定和落地都留痕，不会只给一段读后感。**

---

## 3. 数据流

```
brief.md / 粘贴
   │ intake（解析 + 原文落盘 + 入账）
   ▼
radar/intake/<日期>-<id>.md          ← 原文（进 git）
radar/state/radar.db                 ← 索引（gitignore）
   │ next → workspace
   ▼
radar/state/cache/<host>/<org>/<repo> ← clone（gitignore，TTL 清理）
   │ AI 深读：机制 / 证据 / 适配性 / 成本 / 风险
   ▼
radar/analyses/<日期>/<slug>.md      ← 逐条分析（进 git）
   │ record（结论 + 证据坐标入账）
   ▼
radar/applied/<日期>-<slug>.md       ← 落地记录：改了什么/为什么/没抄什么/门禁/回滚
   │ applied（改动入账）
   ▼
radar/LEDGER.md                      ← 台账渲染（自动生成，进 git）
```

---

## 4. 判定口径

### 4.1 先分诊（必要步骤，不是可选）

每期先跑 `triage`，按确定性规则给三档路由：

| 路由 | 判据（脚本） | 产出 |
|---|---|---|
| `deep` | 机制词加权 ≥5，或仓库 +2 后达标 | clone / 读全文，完整报告 |
| `brief` | 3–4 分 | 5–10 行摘要，不 clone |
| `skip` | <3 分，或噪声词压过机制词 | 一句理由，不写报告 |

规则可解释（`triage_reason` 列出命中的机制词与噪声词），因此判错时可以复核并修正规则。
深读后推翻 `skip` 会在台账留下 `triage_override` 事件。

### 4.2 再判定

| 结论 | 什么时候给 | 必须写清 |
|---|---|---|
| `adopt` | 机制直接成立，单机 Python 标准库环境可跑 | 最小实现 + 验证方式 |
| `adapt` | 机制成立但形态要改（去框架、接现有抽象） | 改了什么形态、为什么原形态不行 |
| `skip` | 不适用 / 与现有实现重复 / 成本高于收益 | **为什么不做**（防止下次重复评估） |

判定顺序固定：**真实问题 → 机制可移植性 → 实现成本**。反过来就会「为了借鉴而借鉴」。

三条硬规矩：

1. `skip` 也要落报告，不许只在对话里说一句「这个没啥用」。
2. 文章类来源最多给 `adapt`，除非文章给了可复核的代码/数据；纯观点不给 `adopt`。
3. 落地改动必须过 `GOVERNANCE.md` 第 4 节门禁，且写回滚方式。

---

## 5. 报告模板

### 5.1 分析报告 `radar/analyses/<日期>/<slug>.md`

```markdown
# <条目标题>

- 来源：<简报日期> #<seq> / <URL>
- 类型：repo | article
- 相关性：<1-5>（相对 agent-ops）
- 结论：adopt | adapt | skip

## 1. 它解决的真实问题
（对准 agent-ops 的哪个具体缺口；对不上就直接写 skip）

## 2. 机制拆解
| 机制 | 怎么实现 | 证据 |
|---|---|---|
| ... | ... | `path:line` / URL#小节 |

## 3. 与现有实现的对照
（agent-ops 现在怎么做；是重复、缺失还是更弱）

## 4. 可移植性
（依赖了什么：Docker/K8s/外部服务/特定语言运行时；去掉后还剩什么）

## 5. 最小切片
（≤200 行能验证什么；不做什么）

## 6. 判定与理由
（为什么 adopt/adapt/skip；成本、风险、维护负担）

## 7. 若落地：验证方案
（测试点、门禁、回滚）
```

### 5.2 落地记录 `radar/applied/<日期>-<slug>.md`

```markdown
# <条目标题> → 落地记录

- 分析报告：`radar/analyses/...`
- 改动文件：`...`
- 提交：`<sha>`（或「未提交」及原因）

## 改了什么
（行为层面的变化，不是文件清单）

## 为什么这样改
（机制映射：上游的 A 对应本地的 B；为什么不直接照搬）

## 没抄什么
（明确列出放弃的部分与原因——和抄了什么同等重要）

## 门禁
（pytest / doccheck / agentctl status / pyflakes 的真实输出摘要）

## 回滚
（git revert <sha>；涉及数据的话写清如何恢复）
```

---

## 6. 磁盘管理

clone 缓存默认在 `radar/state/cache/`（可用 `RADAR_CACHE` 覆盖）。

```bash
python3 scripts/radar_cli.py status            # 看占用（MB）与最近事件
python3 scripts/radar_cli.py clean --days 3    # 3 天未用的工作区
python3 scripts/radar_cli.py clean --max-mb 2000  # 总容量上限，超出按最旧删
python3 scripts/radar_cli.py clean --dry-run   # 只报告不删
```

安全边界：

- 只删**台账记录过**且 resolve 后仍在缓存根内的路径；缓存根外一律跳过。
- 不跟随符号链接删除；只 `shutil.rmtree` 目录。
- 单仓库默认 500MB 上限，超限标记但不静默删除。
- `radar/intake|analyses|applied|LEDGER.md` 永不参与清理。

---

## 7. 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `RADAR_HOME` | `<skill>/radar/state` | 数据库、审计流、缓存的根 |
| `RADAR_DB` | `$RADAR_HOME/radar.db` | 台账数据库 |
| `RADAR_CACHE` | `$RADAR_HOME/cache` | clone 工作区 |

简报来源不做自动抓取：`intake --from-dir` 指向已 clone 的雷达仓库，
或 `--file` 指向手工保存的简报。这样雷达只依赖文件，不依赖某个内网服务是否在线。

---

## 8. 命令速查

| 命令 | 作用 |
|---|---|
| `radar_cli.py intake --file/-from-dir/--json-file` | 收一期简报 |
| `radar_cli.py triage [--force]` | 确定性分诊：deep / brief / skip |
| `radar_cli.py list [--status new] [--brief 日期] [--route deep]` | 看候选与结论 |
| `radar_cli.py next [--force]` | 原子领取一条待分析（默认跳过 skip） |
| `radar_cli.py workspace --candidate N` | clone/刷新上游仓库 |
| `radar_cli.py record --candidate N --report ... --verdict ...` | 登记分析结论 |
| `radar_cli.py applied --candidate N --files ... --summary ...` | 登记落地变更 |
| `radar_cli.py ledger` | 重新渲染 `radar/LEDGER.md` |
| `radar_cli.py status [--json]` | 汇总 + 磁盘 + 最近事件 |
| `radar_cli.py clean [--days N] [--max-mb N] [--dry-run]` | 清理工作区 |

所有查询命令支持 `--json`，便于子 agent 读取。

---

## 9. 与治理层的关系

- 新增/修改雷达代码：按 `GOVERNANCE.md` 分级，至少 P1；测试在 `tests/test_radar.py`。
- 雷达产生的代码改动：等同普通改动，必须过同一条门禁，不许「因为是借鉴所以放宽」。
- `radar/LEDGER.md` 是渲染产物，手改会在下次 `ledger` 时被覆盖。
- 公开脱敏版不包含 `radar/state`、`radar/intake` 与 clone 缓存（见 `desensitize.py`）。

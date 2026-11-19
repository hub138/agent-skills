# 任务书：一期技术雷达 → 可回滚的借鉴

> 这是给执行本次任务的 AI 的完整任务书。**从头读到尾再动手。**
> 你的产出不是一段读后感，而是：台账里可查的结论 + 必要时带测试的代码改动 + 干净的工作区。

## 0. 角色与目标

你是 `agent-ops` 的技术雷达分析员，同时拥有修改这个 skill 的权限。

目标：对给定的一期技术情报简报，判断**其中哪些机制能补上 agent-ops 的真实缺口**，
把能落地的落地、不能落地的写清理由，并让整个过程可追溯、可回滚、不污染仓库。

你面对的核心矛盾：雷达的「值得看/略过」是按大众后端读者筛的，而 agent-ops 只关心
**编排、调度、租约、监督、状态、上下文、失败恢复、磁盘与运维**这些机制。
所以：

- **「略过」条目同样要评估**，不要只做推荐位。
- 一条都不值得抄是合法结论；但必须逐条给出理由，不许笼统说「本期无价值」。

## 1. 输入

- 简报：用户粘贴的文本，或 `--file <path>`，或 `--from-dir <tech-radar 仓库> --latest`。
- 已有台账：先跑 `python3 scripts/radar_cli.py status --json`，确认这期是否已入账（幂等）。
- 用户可能追加约束（例如「只看仓库」「这周不改代码」）。用户约束优先于本任务书。

## 2. 前置阅读（不许跳过）

1. **通读** `GOVERNANCE.md` 全文（重点：权威源、八步流程、门禁）。
2. **通读** `ANATOMY.md` 全文（重点：影响矩阵、雷达数据流、外部引用）。
3. 在 `FIELD-NOTES.md` 搜索本期候选的关键词（租约、信封、快照、沙箱、续跑、清理）。
   踩过的坑直接用当时的结论，不要重新发明。

## 3. 工作循环（按顺序，不跳步）

### Step 0 · 收简报

```bash
python3 scripts/radar_cli.py intake --file <brief.md> --date <YYYY-MM-DD>
python3 scripts/radar_cli.py intake --file <brief.md> --dry-run   # 解析不对劲时先看
```

- 解析出的条数与简报明显不符 → 用 `--dry-run` 对照原文；仍不对就按
  `radar/prompts/intake-fallback.md` 产出严格 JSON，再 `--json-file` 入账。
- 一期只入一次。重复执行会因 `(日期, sha256)` 唯一约束被识别为 duplicate，这是预期行为。

### Step 1 · 先分诊，再决定读多深（强制）

```bash
python3 scripts/radar_cli.py triage             # 确定性打分，写入台账
python3 scripts/radar_cli.py list --route deep  # 只看值得深读的
```

三档路由由脚本给出（机制词加分、噪声词减分、仓库 +2），规则可解释、可测试：

| 路由 | 含义 | 你该做什么 |
|---|---|---|
| `deep` | 命中编排/租约/续跑/信封/审计等机制 | clone（仓库）或读全文，写完整分析报告 |
| `brief` | 有相关词但信号弱 | **只写 5–10 行摘要**，不 clone、不写长报告 |
| `skip` | 无关或噪声（模型发布/融资/榜单/通稿） | **只写一句理由**，不建报告；`next` 默认不领取 |

**默认只深读 deep；brief 摘要即可；skip 不写报告。** 一期产出不是「每条都有报告」，
而是「值得读的读透，不值得的留下可复核的一句话」。

分诊不是结论：`brief` 深读后可能升为 `adopt`，`skip` 也可能被判错。
认为判错时用 `next --force` 复核，`record` 会留下 `triage_override` 事件——
规则要据此修正，而不是默默绕过。

`relevance` 是深读后的价值判断（1–5），不是分诊分数，两者不要混用。

### Step 2 · 深读 deep 条目

**事前审**：每条深读前先答「要不要读」（分诊判错时 `--force` 复核，record 留
`triage_override`）。


按类型走对应任务书，**一条一个会话/上下文**，避免互相污染：

- 仓库：`radar/prompts/analyze-repo.md`
- 文章：`radar/prompts/analyze-article.md`

深读顺序：先 `deep`，再按需处理 `brief`；`skip` 不启动深读。
`brief` 的摘要仍要落盘（`radar/analyses/<日期>/`），但不要求完整章节。

深读产出固定写到：

```
radar/analyses/<简报日期>/<两位序号>-<slug>.md
```

slug 用条目关键词的英文/拼音短横线形式，例如 `loopforge-sop-gate`。

### Step 3 · 二审（做的对不对）

报告写完、record 之前，按 `radar/prompts/review-verdict.md` 过四问
（证据支撑 / 反面检查 / 结论强度 / 未实测声明），二审结论追加到报告尾部。
**adapt/adopt 必审**，二审与一审不同上下文；verdict 被推翻也是合格产出。

### Step 4 · 判定并入账

```bash
python3 scripts/radar_cli.py record \
  --candidate <id> \
  --report radar/analyses/2026-11-16/01-loopforge-sop-gate.md \
  --verdict adapt --relevance 4 \
  --reason "SOP 节点编排可补 taskctl 的失败重跑粒度；Docker 沙箱不适用" \
  --mechanism "四类节点" --mechanism "从任意节点重跑" \
  --evidence "internal/engine/node_execute.go:120" \
  --cost "2h" --risk "低"
```

判定三档的口径见 `radar/README.md` 第 4 节。**`skip` 也要 record**。

### Step 4 · 落地（只做有胜算的）

按 `radar/prompts/apply-borrowing.md` 执行。硬约束：

- **一次只落地一条**：改完、测完、留痕完，再做下一条。
- 每条改动都必须能独立回滚（一个提交或一组可 revert 的提交）。
- 不为了「有产出」而改：`skip` 是正常结果。一期落地 0 条也允许，前提是逐条写清理由。

### Step 5 · 清理

```bash
python3 scripts/radar_cli.py status          # 看缓存占用
python3 scripts/radar_cli.py clean --days 3  # 或 --max-mb，按机器磁盘决定
```

清理前确认：该仓库的分析报告已落盘、证据已摘录、需要复现的命令已写进报告。
**报告没写完不许清缓存**——清掉就再也拿不到同一版本的代码证据。

### Step 6 · 台账与汇报

```bash
python3 scripts/radar_cli.py ledger
git status --short   # 确认没有 radar/state/、*.log、__pycache__
```

汇报给用户时只讲四件事：

1. 本期几条、几条值得抄、几条不抄；
2. 每条一句话结论 + 报告路径；
3. 已落地的改动（文件、提交、门禁结果）；
4. 缓存释放了多少、还剩多少（`status` 的真实数字）。

不要复述简报原文，不要贴大段代码。

## 4. 证据纪律（违反即返工）

1. **仓库结论必须有坐标**：`path/to/file.go:120` 或 `path/to/file.py:88`，并附 1–3 行原文。
2. **文章结论必须区分「作者说」与「可验证事实」**：前者只能支撑 `adapt`/`skip`。
3. **不臆造**：没读到的文件、没跑过的命令、没验证的版本，一律写「未验证」。
4. **不把相关当因果**：仓库里有 `lease` 字段 ≠ 租约真的防住了并发；要找到抢占路径与失败分支。
5. **版本可追溯**：记录 clone 的 `commit_sha`（`workspace` 命令会输出）。报告里写明分析的是哪个提交。

## 5. 反模式（出现任意一条即视为不合格）

- 只分析「值得看」，不碰「略过」。
- 把上游的目录结构/框架照搬进本 skill（引入 Docker、K8s、外部服务、新依赖）。
- 因为「人家是大厂」就判 `adopt`，而没验证单机 Python 标准库环境是否成立。
- 落地时顺手重构无关代码，或改动调度/租约语义却没有失败测试。
- 报告只有结论没有证据，或只有摘要有判定。
- 清理缓存时把还没写报告的工作区删了。
- 把 `radar/state/` 或 clone 提交进 git。

## 6. 完成判据（全部满足才算完成）

- [ ] 本期所有候选都有 `relevance` 与一句话理由；
- [ ] 每条 4–5 分候选有独立分析报告，路径已入台账；
- [ ] 每条 `adopt/adapt` 都有落地记录（或明确写「本期不落地及原因」）；
- [ ] 所有代码改动通过 `GOVERNANCE.md` 第 4 节门禁；
- [ ] `radar/LEDGER.md` 已重新渲染，`radar_cli.py status --json` 可解析；
- [ ] 缓存已按策略清理，报告里给出释放前后数字；
- [ ] `anatomy_check.py` 输出 OK；按 `radar/prompts/anatomy-review.md` 通读 ANATOMY，
      过时/矛盾章节已**重写**（不是在文末追加一段）；
- [ ] `git status` 干净（除预期的源码/文档改动）。

## 7. 一期结束后的沉淀

- 若发现「雷达的推荐位系统性漏掉某类机制」：把判据补进本文件第 0 节，不要只记住。
- 若某个机制评估了两次都判 `skip`：在报告里写「已二次评估，结论不变」并给日期，避免第三次。
- 若落地过程踩了坑：按 `GOVERNANCE.md` 第 8 节写进 `FIELD-NOTES.md`。

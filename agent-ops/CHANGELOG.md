# CHANGELOG

> 每次提交一段，倒序。格式见 `GOVERNANCE.md` 5.1：
> 改了什么 / 为什么 / 门禁 / 回滚。不写「优化了一下」。

## 2026-11-18 · 任务组：子 agent 互相感知与通讯（group）

### 新增
- `scripts/task_group.py`：三通道——感知(`groups/<gid>/peers.md`)、
  通讯(`taskctl send` → 对方 `inbox.md`)、留痕(`events.jsonl`，schema 对齐
  foundation.events.Event)；消息幂等（同 from+内容 sha 已发过则拒绝，--force 才重发）。
- `taskctl`：`tasks.group_id` 列（只加列迁移）；`add --group`；`plan` 同次拆解
  自动同组；`send` / `group <gid>` 两个子命令；`ensure_task_dir` 注入 peers 投影
  与收件箱新消息（偏移量防重放，消费后不重复注入）；`event` hook 在状态变化时
  刷新 peers；manager 快照带 group（组内互等超时由管理者模型判断，不写死脚本逻辑）。
- `tests/test_group.py`：6 项（成员登记/幂等/消费增量/状态投影/prompt 注入/全景）。

### 用法（双 AI 协作，明日场景）
`taskctl plan --goal "rzz 改进：AI-1 实现+验证，AI-2 调研"`（同组并行）→
AI-1 每轮 `send --to research "case X 失败，需查 XX 方向"` → research 下一轮
prompt 带消息与 peers → 调研笔记落盘 `groups/<gid>/` → 汇合由 manager 判断。

### 端到端冒烟（真实 CLI）
双任务同组 → send×2 → inbox 2 行 → 偏移量消费后 pending 清空 → 组事件 4 条
→ peers 投影含成员 status/idle/outdir。

### 门禁
pytest 96 passed；doccheck OK；anatomy_check OK；agentctl status/json OK；
pyflakes `undefined name '` = 0。

## 2026-11-18 · agent_foundation 通用件桥接（只读库）

### 新增
- `scripts/foundation_bridge.py`：定位 agent_foundation（env > 内部布局 > 公开布局）；
  缺库返回 None，调用方手写回退——安装副本/别的机器不受影响。
- `scripts/prompt_transport.py`：argv 上限 ≈128KB 截断（审查项目 232 条里 2 条 knot 实测坑）。
- `scripts/provider_events.py`：失败分类（foundation provider_failure + agent 假绿灯形态）
  + 落盘冷却（限流自报重置时刻按时刻冷却）。
- `scripts/evidence_gate.py`：result evidence 坐标/引文校验（宽松口径只记警告）。
- `tests/test_foundation.py`：15 项。

### 接入
- `manager`：监督调用前查冷却；prompt cap；解析走 protocol 三级（只采 EMBEDDED——
  STREAM 级第一行可能是 CLI 内部事件），缺库回退手写正则。
- `supervise_agents` / `supervise_jobs`：假绿灯/429 手写检测统一到 provider_events；冷却 + cap。
- `agentctl`：registry 读写改 AtomicJsonStore（损坏不静默归零——foundation 生产事故教训）。
- `taskctl`：build_cmd/plan prompt cap；收尾 evidence_gate 校验记 evidence_warning。
- `SKILL.md` 增补「通用件桥接表」；`ANATOMY` 脚本表登记 4 个新模块。

### 不迁移（理由在 SKILL.md 桥接表）
`recovery.py` / `iteration_loop.py`（taskctl 语义已覆盖，避免双轨）；
`resource_pool.py`（并发 = 进程池 + 模型红线发前拒绝，未实测不接）。

### 门禁
- agent_foundation：全量基线 7 个收集错误（__init__.py 与测试脱节，只读不修）；
  涉及模块测试文件（safety_modules/runtime_infra/agent_foundation/privacy/adapters/webhook）57 项全绿。
- agent-ops：pytest 90 passed / doccheck OK / anatomy OK / agentctl json OK / pyflakes 0。

## 2026-11-16 · 独立审查：证伪「无效优化 / 重复建设」

### 审查方式
独立只读审查（54 次工具调用）+ 真实负向测试 + 真实简报数据对照。下面每条都有证据，
不是「测试都过了所以没问题」。

### 确认为真问题并修复
- `intake --slot` 没传给入库函数；`--latest` 是空 `pass` 分支 → 重写 `cmd_intake`：
  `--from-dir` 默认收全部简报、同日多期自动分批，`--latest` 才只收最新。
- 真实简报的 `## 略过` 段完全没解析（11-15 那期 12 条只进 2 条）→ 新增解析，
  实测回到 12 条；略过条目按理由复核，明显噪声仍跳过。
- `clean --days + --max-mb` 组合被容量短路吞掉 TTL 清理 → `ttl_count` 区分，测试钉住。
- `claim` 事件没有 actor、`triage_override` 单独提交 → 事件记 actor/主机，
  override 与分析同事务，新增 `events --kind` 作为消费入口。
- `triage --force` 会覆盖已分析条目路由 → 只重打 `new/screened`。
- 契约自动附加不在末尾、用关键词判重 → `render_prompt(extra=)` 保证契约在最后，
  用契约正文片段判重。
- 治理文档把门禁写成 4/5/6 条互相打架、写死测试数、公开版有悬空引用 →
  统一到 `GOVERNANCE` 第 4 节六条；数字改为「以 doccheck 为准」；
  `SKILL.md` 导航表登记全部新模块并纳入 `doccheck` 检查；
  `desensitize.py` 改掉公开版对 `radar/intake` 的悬空引用。

### 证明不是重复
- **triage 与上游预筛判据不同**：上游 `rank.py`/「略过」按大众读者信息量，
  本 skill 按编排机制词。实测 11-15 真实简报 12 条 → `1 deep / 5 brief / 6 skip`：
  上游判略过的 LoopForge / agent-runtime / SuperAgent 全部进入复核，
  而推荐位里的「训推一致性」被判 `skip`。
- 两份 SQLite 数据不同（任务队列 vs 雷达台账）；三个检查器职责不同
  （文档数字 / 文档结构 / 运行时在岗）。
- `templates/tasks/*.md` 没有与契约重复的条款；`render_prompt` 追加确实让 worker
  多拿到整份契约（约 5KB）。

### 负向验证（可证伪）
- 新建未登记脚本 `scripts/_ghost_probe.py` → `doccheck` 退出 1，报「未出现在 ANATOMY」；
- 删除 ANATOMY 第 10 节 → `anatomy_check` 退出 1；恢复后两者 OK；
- 真实 CLI 走 `--slot` → DB 里 slot 不再是空串（此前测试绕过 CLI 掩盖了这个问题）。

### 门禁
pytest 75 passed；doccheck OK；anatomy_check OK；agentctl status/json OK；pyflakes 0。

## 2026-11-16 · 雷达分诊：先筛后读（必要功能）

- 新增 `triage` 子命令与 `triage_score/route/reason/at` 四列（只加列迁移）。
- 规则：机制词加权 + 仓库 +2 − 噪声词；≥5 `deep` / 3–4 `brief` / <3 `skip`。
- `next` 默认跳过 `skip`；`workspace` 拒绝 clone `skip`（需 `--force`）。
- `record` 遇到 `skip` 却被判 `adopt/adapt` 时写 `triage_override` 事件，便于回头修规则。
- 提示词改为「默认只深读 deep；skip 不写报告」，补 3 项测试（规则/拦截/旧库迁移）。
- 实测 11-16 两期 8 条：7 条 deep、1 条 brief（原生沙箱，证据不足），无机制条目被误杀。

## 2026-11-16 · 文档自维护：ANATOMY 结构对账 + 全文审阅

### 新增
- `scripts/anatomy_check.py`：路径存在性、脚本/模板/提示词覆盖、影响矩阵、门禁完整性；
  退出码 1 = 需要修订。已并入 `doccheck.py`，同时保留独立入口拿结构清单。
- `radar/prompts/anatomy-review.md`：逐节提取「声称」→ 五类判定（成立/过时/不完整/矛盾/多余）
  → 六维必查 → 重写章节；明确禁止文末追加更新日志。
- `tests/test_anatomy.py`：6 项，验证对账器能拦住缺章节、幽灵路径、未覆盖脚本、
  门禁未接、缺任务书。

### 重写（按审阅结论，不是追加）
- 目录树：删除不存在的 `orchestrator/`；列出全部雷达提示词；修正 `_done-contract.md` 的生效方式。
- 脚本表：补 `anatomy_check.py`；`radar_store` 补事务与 claim 事件；`radar_cli` 补同日多期。
- 雷达数据流：补 slot、claim、事务边界。
- 影响矩阵：补 `radar_store.py`/`radar_cli.py`；契约行改为「render_prompt 自动附加」。
- 外部引用：给出 rsync 同步命令并改用 md5 校验；区分部署前缀与 CLI 契约。
- 判定口径：补「第二轮深读可修正第一轮结论」。
- 扩展清单与边界：补对账/审阅两步；明确 ANATOMY 不自动生成。

### 门禁
pytest 全绿（项数以 doccheck 为准）
pyflakes `undefined name '` = 0。

### 回滚
`git revert <本次提交>`。删掉 anatomy_check 调用即可回到「只靠自觉」的状态（不建议）。

## 2026-11-16 · 雷达子功能 + 治理层 + 两处借鉴落地

### 新增：技术雷达（radar）

- `radar/schema.sql`：briefs / candidates / analyses / changes / workspaces / events 六张表；
  `briefs.slot` 支持同一天多期（实测 11:00 与 15:00 内容不同）。
- `scripts/radar_store.py`：两种简报格式解析、幂等入账、原子领取、台账渲染；
  状态/记录/审计**同事务提交**（见下方借鉴）。
- `scripts/radar_workspace.py`：只接受 http(s)/git@ 仓库 URL；clone 到独立缓存；
  删除前校验路径仍在缓存根内且是台账记录过的路径。
- `scripts/radar_cli.py`：`intake/list/next/workspace/record/applied/ledger/status/clean`；
  确定性操作不调模型；`--json` 挂在子命令上。
- `radar/README.md` + `radar/prompts/{session,analyze-repo,analyze-article,apply-borrowing,intake-fallback}.md`：
  一期任务书与四种专项任务书，含证据纪律、反模式、完成判据。
- `tests/test_radar.py`：11 项，覆盖两种格式、同日多期、幂等、原子领取、
  审计失败回滚、清理越界拒绝。

**为什么**：雷达的「值得看/略过」按大众后端读者筛。2026-11-15 那期把
LoopForge / agent-runtime / SuperAgent / GCA 四条全判「略过」，而这四条恰好是
编排系统最该借鉴的。雷达子功能用本 skill 自己的问题清单重新评估，并把结论变成
可回滚的改动。

### 新增：治理层

- `GOVERNANCE.md`：单一权威源、变更分级（P0–P3）、八步流程、四条门禁、
  留痕格式（CHANGELOG / 分析 / 落地 / FIELD-NOTES）、八条红线。
- `ANATOMY.md`：分层、目录职责、四条运行时链路、数据位置、变更影响矩阵、
  外部引用（cron 命令与安装副本）、雷达解剖、扩展清单、边界。

**为什么**：改之前要能查到「改哪里、下游是谁、要跑什么」；改完要能回答
「改了什么、为什么、怎么回滚」。

### 借鉴落地（2 条，其余 6 条结论见 `radar/LEDGER.md`）

1. **续跑文章 → 任务契约**：`templates/tasks/_done-contract.md` 增加
   「断点快照四问」（哪版目标/已完成/下一步/未知副作用）与「副作用前落盘」；
   `taskctl.render_prompt()` 改为**真正附加**契约（此前文档声称自动附加、代码没做），
   并用测试钉住「四问必须出现在提示词里」。
2. **openclaw-enterprise → 雷达台账**：`radar_store.tx()` 把候选状态、分析/变更记录、
   审计事件放进同一事务；DB 审计写不进去就整体回滚；`audit.jsonl` 是提交后的镜像。

### 补充：第二轮深读（同日）

- 重新 clone 三个仓库并做代码级深读：LoopForge 的节点类型/验证门禁/工作区检查点；
  openclaw 的 claim+audit 同语句/终态 evidence CTE/恢复分类；agent-runtime 的
  Deployer ABC/`running_not_ready`/双队列。
- **结论修正**：SuperAgent 由 `skip` 改为 `adapt`。第一轮只确认「有信封」，
  漏了失败分类（TIMEOUT/UNDELIVERABLE/WAITING_HUMAN）与错误三元组
  （userCause/userAction/system）；`taskctl.validate_result` 目前只有 done/blocked/failed。
- **新增落地**：`take_next` 领取时同事务写 `claim` 事件
  （对应 openclaw `postgres-work-queue.ts:62`）。
- 8 份分析报告均追加「第二轮深读补充」，并标注未覆盖范围。
- 门禁：pytest 全绿（项数以 doccheck 为准）

### 修复：既有缺陷

- `scripts/supervise_agents.py`：`idle` 在 `_session_stats()` 之前被引用，
  正常退出且空闲 >300s 的分支会抛 `NameError` 并中断整轮监督。把 `_session_stats`
  调用前移；该问题由 pyflakes 门禁发现。

### 门禁

```
pytest tests/ -q                全绿（项数以 doccheck 为准）
doccheck.py                     OK 文档数字与代码事实一致
agentctl.py status              打印任务表
agentctl.py status --json       JSON 可解析
pyflakes | grep "undefined name '"   0
```

### 回滚

- 整批：`git revert <本次提交>`
- 仅借鉴 1：`git checkout HEAD~1 -- templates/tasks/_done-contract.md`
- 仅借鉴 2：`git revert <本次提交>` 或还原 `scripts/radar_store.py` 的 `tx()` 调用
- 雷达数据在 `radar/state/`（gitignore），回滚代码不影响已落盘的报告

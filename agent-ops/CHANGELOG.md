# CHANGELOG

> 每次提交一段，倒序。格式见 `GOVERNANCE.md` 5.1：
> 改了什么 / 为什么 / 门禁 / 回滚。不写「优化了一下」。

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
pytest 64 passed；doccheck OK（含 anatomy_check）；agentctl status/json OK；
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
   审计事件放进同一事务；审计写不进去就整体回滚。

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
- 门禁：pytest 58 passed；doccheck OK；pyflakes `undefined name '` = 0。

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

# CHANGELOG

> 每次提交一段，倒序。格式见 `GOVERNANCE.md` 5.1：
> 改了什么 / 为什么 / 门禁 / 回滚。不写「优化了一下」。

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

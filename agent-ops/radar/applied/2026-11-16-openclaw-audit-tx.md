# OpenClaw → 雷达台账「变更 + 状态 + 审计」同事务

- 分析报告：`radar/analyses/2026-11-16/08-openclaw-control-plane.md`
- 改动文件：`scripts/radar_store.py`、`tests/test_radar.py`
- 提交：`a7e9c50`

## 改了什么

- 新增 `radar_store.tx(conn)`：显式 `BEGIN IMMEDIATE`，异常整体回滚。
- 拆出 `_event_row()`（只写事件行，不提交）与 `_audit_file()`（提交成功后追加
  `audit.jsonl`，best effort）。
- 以下写入全部改为单事务：
  - `ingest_brief`：简报 + 候选 + intake 事件；
  - `take_next`：读取 + 标记 screened；
  - `set_status`：状态更新；
  - `record_analysis`：分析记录 + 候选状态 + analysis 事件；
  - `record_change`：变更记录 + 候选状态 + applied 事件；
  - `record_workspace`、`mark_cleaned`：工作区登记/清理标记 + 事件。
- 新增测试 `test_record_analysis_rolls_back_with_audit`：让 `_event_row` 抛错，
  断言分析记录与候选状态一起回滚，且没有留下 analysis 事件。

## 为什么这样改

OpenClaw 的 `docs/design.md:125` 写的是
「Resource mutations, queued work, and audit records commit together」，
并且审阅里明确「授权或审计失败会阻止变更」（`:203-204`）。

修改前 `record_analysis` 是三次独立提交（analysis → candidate → event）：
进程在第二步崩溃，就会留下「分析报告已入账、候选仍是 new」的台账；
在第三步崩溃则「状态改了、审计没有」。这两种状态都会让「可追溯」失效——
不是日志缺失，而是台账与事实不一致。

对雷达来说，审计不是附属日志，而是结论的一部分。所以按 OpenClaw 的口径把三者
放进同一事务；`audit.jsonl` 的文件追加放在提交之后，避免文件写失败把数据库事务拖挂。

## 没抄什么

- **多租户 / IAM / Driver 体系**：单机单人不需要。
- **不可变 Agent revision 表**：`events` 已经是只追加历史，再造一层 revision 是重复。
- **独立 audit 包**：本 skill 的审计由 `_event_row` + `_audit_file` 承担，
  规模不需要分包。

## 门禁

```
pytest tests/ -q                58 passed（雷达 12 项，含事务回滚）
doccheck.py                     OK
radar_cli.py status --json      JSON 可解析
pyflakes | grep "undefined name '"   0
```

## 回滚

```bash
git revert a7e9c50
```

回滚后台账恢复为多次提交，已有数据不受影响（schema 未变）。

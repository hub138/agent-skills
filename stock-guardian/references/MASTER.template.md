# MASTER.md — 单一当前事实源（模板）

> 用法：`node scripts/state-core.js init --sg-home <数据目录>` 会按本模板创建 `<数据目录>/MASTER.md`；
> 也可复制本文件手动创建。任何 AI 可读写，但**写必须通过 state-core.js 原子命令**（并发安全、强制版本号）；
> 直接手改后必须运行 `node scripts/state-core.js validate` 确认合法。
> 铁律：unknown 合法；AI 建议永远不等于成交；成交只认用户实报。

标记之间为机器真相（`jsonl` 区块内每行一条合法 JSON 记录），标记之外可写人类说明。
历史叙事、过期口径**不得**留在标记之内；标记内的每一条记录都必须是"现在进行时"的当前事实。

<!-- SG:STATE:BEGIN -->
```jsonl
{"type":"META","schema_version":1,"revision":0,"updated_at":"unknown","last_writer":"unknown"}
{"type":"ACCOUNT","cash":{"amount":null,"status":"unknown"},"total_assets":null,"data_status":"unknown"}
```
<!-- SG:STATE:END -->

## 记录类型

| type | 唯一键 | 关键字段 |
|---|---|---|
| META | 唯一 | schema_version / revision / updated_at / last_writer（由命令自动维护） |
| ACCOUNT | 唯一 | cash.amount / cash.status / total_assets / data_status |
| POSITION | code | quantity / sellable / cost / source / known_at |
| EXECUTION | id | code / side(BUY\|SELL) / qty / price(null=unknown) / cash_change / known_at / source / historical |
| CANDIDATE | code | entry_plans[]（同代码多条计划合并存放） |
| DECISION | id | action / quantity / price_range / max_loss / invalidation / expires_at / evidence_level |
| STRATEGY | id | 策略注册信息 |
| OPEN_QUESTION | id | text / evidence / status（未决问题，闭环后记录 resolved_at） |

`status` 取值：`confirmed`（用户实报/券商导入）｜`estimated`（机器或推算，禁止当确认用）｜`unknown`。
`source` 取值：`user_report`｜`broker_import`｜`machine_estimate`｜`ai_estimate`。

## 命令速查

```
init --sg-home PATH
validate | show
set-account      --cash N --cash-status S [--total-assets N|unknown] --data-status S --expect-revision R
set-position     CODE QTY SELLABLE COST|unknown SOURCE KNOWN_AT --expect-revision R
record-execution --id ID --code CODE --side BUY|SELL --qty N --price N|unknown --known-at TS [--historical] --expect-revision R
settle-t1        --code CODE [--qty N] --expect-revision R
add-question     --text TEXT [--evidence E] --expect-revision R
upsert-candidate --json FILE --expect-revision R
set-decision     --json FILE --expect-revision R
set-strategy     --json FILE --expect-revision R
import-pool      --source POOL.md --expect-revision R
render-views     （生成 views/ 只读视图：portfolio.current / pool.current / watch.current）
```

所有写命令必须带 `--expect-revision R`（CAS：版本不符即拒绝，防并发覆盖）；成功一次 revision+1。
`record-execution` 只认实报事实：SELL 不得超过 sellable，BUY 当日不增加 sellable（T+1），价格 unknown 时现金降级 estimated；
`--historical` 用于补录已发生的动作（只登记事实，不改持仓与现金现值）。

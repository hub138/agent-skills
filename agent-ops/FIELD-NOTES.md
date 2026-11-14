# 实战补丁记录（2026-11-13 通宵任务）

> 本文件只记**用本 skill 真实跑任务时踩到的坑与已落地的修法**，不是设计文档。
> 每条都附现象、根因、改了什么、怎么验证。新增前先看有没有同类。

---

## 1. supervisor.py 不认识 agentctl 任务（已补后端）

**现象**：用 `agentctl dispatch` 派了 3 个 agent，`supervisor.py snapshot` 输出「(没有 running 任务)」。

**根因**：`supervisor.build_snapshot()` 只查 `taskctl` 的 sqlite `tasks WHERE status='running'`，
返回的 `rows` 是 `sqlite3.Row`，后续 `apply_action` 依赖这些字段。agentctl 的任务只存在于
`~/.codebuddy/agentctl/<name>/` 目录 + 会话 jsonl 里，**没有数据库**，两套模型不通用。

**改法**：新增 `scripts/supervise_agents.py`（agentctl 后端），**复用** supervisor 的
`PROMPT` / `ask_model()` / `SUPERVISOR_MODEL`，**只换**快照来源与动作执行：
- 快照来自 `agentctl.load_registry()['tasks']` + `agentctl.session_file(task)`；
- 动作：`continue` 不动 / `nudge` 写 `guidance.md` / `restart` 仅对已死进程 `resume` /
  `escalate` 写 `escalate.md` / `finish` 写 `finished.md`。

**验证**：`supervise_agents.py snapshot` 能列出 3 个任务且事件数各不相同（38/82/55，此前自己按
前缀 glob 全部指到最新那个 jsonl，四个任务都显示 118）；`once --force` 让监督模型对三个
「刚启动、无 progress.md」的任务都判 `continue`（理由：早期无进度文件属正常），**没有误杀**。

**教训**：不要自己 `glob('*.jsonl')` 猜会话，一定走 `agentctl.session_file()`——registry 里有
准确 `session_id`。

---

## 2. cron 里的 python3 不是你以为的那个（3.6 vs 3.12）

**现象**：`agentctl watch` 挂 cron 后日志全是
`SyntaxError: future feature annotations is not defined`。

**根因**：交互 shell 的 `python3` 是 `/root/.pyenv/shims/python3`（3.12.0），
cron 的干净 PATH 解析到 `/usr/bin/python3`（**3.6.8**），
而 `agentctl.py` 首行有 `from __future__ import annotations`（3.7+）。

**改法**：crontab 里写**绝对路径**：
```
*/5 * * * * cd <skill 安装目录>/agent-ops && \
  CODEBUDDY_CLI_BIN=/usr/local/bin/codebuddy \
  /root/.pyenv/versions/3.12.0/bin/python3 scripts/agentctl.py watch --quiet >> /tmp/agentctl_watch.log 2>&1
```

**验证**：手动 `timeout 60 <abs python3> scripts/agentctl.py watch --quiet` → `rc=0`。

**教训**：cron 与交互 shell 的 `python3` 可能差三个大版本。凡挂 cron 的脚本，
命令里一律写绝对路径，别依赖 PATH。同类问题在 `codebuddy` 二进制上也存在（见 codebuddy-cli-notes.md）。

---

## 3. 会话 jsonl 的结构是 `function_call`，不是 `tool_use`

**现象**：自己写解析器统计「模型干了什么」，结果工具调用数恒为 0。

**根因**：codebuddy 会话 jsonl 的行结构是：
```json
{"type":"function_call","name":"Bash","arguments":"{\"command\":\"...\"}"}
{"type":"function_call_result","name":"Glob","status":"completed","output":{"type":"text","text":"..."}}
{"type":"message","role":"assistant","content":[{"type":"output_text","text":"..."}]}
```
不是 Anthropic 的 `message.content[].type == "tool_use"`。而且 `arguments` 是 **JSON 字符串**，
不是 dict，要二次 `json.loads`。

**改法**：解析时按 `type` 分支：`function_call` 取 `name` + 解析 `arguments`，
`function_call_result` 取 `output.text`，`message` 取 `content[].text`。

---

## 4. `--resume <非UUID会话ID>` 静默返回 rc=0 且零输出

**现象**：`agentctl resume rootcause` 输出「已续接」，但进程没起来、状态仍 `queued`；
手动 `codebuddy -p ... --resume rootcause-1794506006 -- "..."` 得到 **rc=0、stdout 为空**。

**根因**：`--resume`（等价 `-r`）在会话 ID 不是 UUID、或会话状态不可续时，
不报错、不输出，直接返回 0。这是「假绿灯」的变体——
`returncode == 0` 且 `stdout` 为空，任何只看 rc 的封装都会判成功。

**改法（临时）**：对幂等任务（已入表的不重跑）改用 `dispatch` 新建会话，
在 prompt 里写「先读 progress.md 恢复，从第一个未完成项继续」，比 resume 可靠。

**改法（应做，未做）**：`agentctl resume` 应在拉起后等 3 秒检查
`pid` 是否存活 **且** 会话 jsonl 是否新增事件，两者都不满足就降级 `dispatch` 新建，
而不是打印「已续接」就返回。

**教训**：续接类调用必须验「有输出 + 有新事件」，不能只看 rc。

---

## 5. 外部 `pkill -f <脚本名>` 会连带杀掉 agent 的子进程

**现象**：3 个 agent 在 01:59 同时停止，`run.log` **完全空**（连错误都没有），
会话最后一条是 `function_call_result`（工具调用中途断）。

**根因**：agent 执行时会 `Bash` 调各种脚本，子进程 cmdline 里带脚本名。
我在清理 `deep_reach.py` / `deep_all.sh` 时用 `pkill -f deep_reach.py`，
把 agent 派生的同名子进程一起杀了；agent 主进程随后也被连带。

**改法**：清理一律**按 PID 精确杀**，先 `ps -eo pid,ppid,cmd` 认父链；
只在确认 cwd 或 ppid 链属于本项目时才 kill。

**建议（未做）**：`agentctl dispatch` 应在任务目录落一份 `pids.txt`
（bash wrapper + node 主进程 + 已知子进程），清理时按文件杀，不靠模式匹配。

**教训**：`run.log` 为空**不等于**没跑过——可能是被 SIGKILL 没来得及 flush。
判断依据看会话 jsonl 的事件数，那是边跑边写的。

---

## 6. `progress.md` 只写进提示词不够，要机械检查

**现象**：三个任务的 prompt 都明确要求「每完成一步追加 progress.md」，
实际跑了几十个事件后 `progress.md` 仍然不存在。

**根因**：模型在「先探查、还没动手」阶段会认为「没什么可写的」，
纯靠提示词约束不住。

**改法**：`supervise_agents.py` 的快照里把 `progress_lines=0` 标成
「**缺失：上下文压缩后无法恢复，必须要求它先落盘**」，由监督模型在合适时机 nudge。
同时 `should_ask()` 里加了一条：`missing_progress and events > 20` 也触发监督
（不必等 30 分钟定时）。

**验证**：`once --force` 时监督模型看到 6 事件、0 进度，正确判 `continue`
（早期正常）；事件数涨到 20 以上会转为触发。

---

## 7. 任务 prompt 里的数字要先跟库核对

**现象**：`reach_refine` 任务写「对 23 条可达已建立条目」，agent 实际查到
`deep_reach` 已建立 29 条、`judge_condition` 只有 12 条，主动提出口径不一致。

**根因**：我在写 prompt 时用的是几分钟前的快照数字，期间 `deep_all.sh` 还在跑。

**改法**：prompt 里的数量一律写成「以库为准，当前约 N 条，先用 SQL 确认再动手」，
不写死具体条数。

**教训**：这是**好现象**——agent 质疑输入前提是期望行为，不该被当成跑偏。
主 agent 写 prompt 时要预留这种校验，而不是要求它盲从数字。

---

## 落地清单

| 文件 | 改了什么 |
|---|---|
| `scripts/supervise_agents.py` | **新增**：agentctl 后端的模型监督器 |
| `FIELD-NOTES.md` | 本文件 |
| 无 | 其余 6 条是操作纪律，已写入本文档，代码未改的已在「应做/建议」标注 |

---

## 8. agentctl 长任务「静默死亡」的完整链条（最重要的一条）

**现象**：`dispatch` 派出的 agent 跑 2-10 分钟后消失。
`agentctl status` 显示 `queued`，`run.log` 只有 `===== start =====`，`exit` 文件为空，
会话 jsonl 末尾停在 `function_call_result`（没有最终文本）。

**排查过程与已排除项**：
- ❌ 不是 OOM：`dmesg` 全天仅 1 次 OOM，且时间对不上。
- ❌ 不是进程组连带：`spawn()` 已有 `start_new_session=True`。
- ❌ 不是 agentctl 主动 kill：代码里没有 kill 逻辑。
- ❌ 不是假绿灯：派探针任务后 `run.log` 正常输出「收到」，`exit=signal-or-exit:0`。

**真相（三条叠加）**：
1. **单次 `-p` 调用有 `--max-turns` 上限**。长任务（如「审判 807 条」）跑到上限就正常退出，
   模型没产出最终文本 → `run.log` 里只有 start 行、`exit=0`，看起来像「什么都没干」。
2. **`watch` 用 `--resume` 续接，但会话 ID 不是 UUID 时静默返回 rc=0 零输出**（见第 4 条），
   于是「续接成功」是假的，状态停在 `queued`。
3. 三者叠加形成看起来像「卡住」的死循环。

**正确用法（本 skill 的 `watchdog.md` 早就写了，但很容易忽略）**：
- 长任务**不能**指望一次 `-p` 跑完。用 watchdog 的 `prompts` 数组 + `prompt_mode: cycle`
  拆成多步；每步只跑一批、把进度写 `progress.md`，下一轮读进度继续。
- 或者：**需要跑几百条批量的，用脚本 + cron，不要用 agent**。
  agent 适合「需要判断和改代码」的活；纯遍历批量用脚本更快更稳、不占模型额度。
- 幂等设计是前提：已处理的不重跑（本项目用 `judge_done` / `s3_outcome` 表），
  这样即使每轮只跑 20 条被中断，下一轮也能接上。

**已落地的小改进**：`spawn()` 的 bash wrapper 加 `trap 'echo "signal-or-exit:$rc" > exit' EXIT`，
下次异常退出时 `exit` 文件里能看到是信号还是正常退出码——
此前 `exit` 恒为空，只能靠猜。

**教训**：`run.log` 为空 + `exit` 为空 + 状态 `queued`，这组三特征是
「轮次耗尽 + resume 静默失败」，不是「进程被杀」。先看会话事件数是否停在某个整数附近。

---

## 9. `launch_task` 复用旧 session_id 造成「续接死锁」（已加秒退自愈）

**现象**：三个任务卡 `queued` 13 分钟，`agentctl resume` 每次都打印「已续接」，
但 `session_id` 和 `pid` 完全没变、进程也没起。

**根因**：
- `cmd_resume` 只 `enqueue(reg,"launch",...)` 然后**立即**打印「已续接」，不验证；
- `launch_task` 新建时**复用 task 里旧的 `session_id`**，而磁盘上已有同名会话文件，
  codebuddy 会直接退出（rc=0、`run.log` 无内容）；
- effect 因此被判成功并从队列移除，`watch` 下一轮再 enqueue、再秒退 —— 死锁。

**已改**：`launch_task` spawn 后等 3 秒探活，不活就换 `session_id` 为 `<name>-<ts>`
重试一次；仍不活则 `status=queued` 并返回 False，交回 effect 退避重试
（3 次后转 `awaiting-person`，不再无限循环）。

**仍未改（建议）**：`cmd_resume` 的「已续接」应在探活通过后才打印。
现在的输出会在失败时也报成功，是同一类「假绿灯」。

---

## 10. 长批量任务不该用 agent（用脚本 + cron）

**实测**：`p1_trialr2` 跑了 74 个会话事件、`rootcauser2` 48 个，**产出为零**——
全部在「读文件、核对数据、还原上下文」，没有一行代码或一条结论落盘。

**对比**：把同一件事写成 `trial_pipeline.py`（由 `p0_full_trial.py` 参数化 level）
+ cron 每 5 分钟跑 30 条，**单批就产出 26 条结论**，幂等、可中断、不占对话额度。

**判据**：
- 需要「读代码、做判断、改文件」→ 用 agent
- 只是「遍历 N 条、每条跑固定流程」→ 用脚本 + cron
- 前者受 `--max-turns` 和上下文限制，后者没有上限

**副产品**：`S1_FAILED`（限流）不该落表，否则会出现「写表失败 → 下轮重跑 → 再失败」的
重复烧调用。改成 S1 失败只在日志记录、下轮自然重试。

---

## 11. 监督器要排除「已完成/探针」任务，否则反复空触发

**现象**：cron 跑 `supervise_agents once` 输出
`[supervise_agents] 监督者无有效输出` + `触发判断: ask=True (probe 超过 600s 无新事件)`。

**根因**：`collect()` 只跳过 `finished.md` 存在或 `awaiting-person` 的任务；
一行式探针任务（`probe`/`demo*`）没有产出契约、也没有 `finished.md`，
被当成「活跃但卡住」，每轮都触发监督，而模型对一个已完成的探针给不出动作 → 输出 null。

**已改**：
- 名字以 `probe`/`demo` 开头的跳过；
- `exit` 含 `signal-or-exit:0` 且会话超过 300 秒无新事件 → 视为完成，不再告警。

**验证**：三个卡死的任务转 `awaiting-person` 后，快照为空、不再调模型（正确行为：
没有活跃任务就不该烧调用）。

**教训**：监督器的价值取决于「被监督对象是否真的在跑」。当所有活都交给脚本 + cron 后，
agent 监督器的正确输出就是「无可监督任务」——不要为了让它有输出而硬塞任务进去。

---

## 12. 长批量脚本的三个必备防护（都踩过）

把 P1 807 条审判从 agent 改成脚本 + cron 后，连续踩了三个坑：

1. **`S1_FAILED` 不能落表**：限流失败的记录一旦落表，下轮 `NOT IN` 会跳过它，
   永远不会重试；而如果写表失败又会重复烧调用。
   正确做法：S1 失败**在写表之前 `continue`**，只在日志记录，下轮自然重试。
2. **cron 批次要 `flock -n` 防重叠**：每 5 分钟一批、每批 30 条，单批可能跑超 5 分钟，
   重叠会抢同一个免费模型池，限流率升到 80%。
   **注意别写成 `[ -f lock ] && exit 0`** —— `flock` 会长期保留锁文件，这行会让任务永远不跑。
3. **`reason` 不能只写机械占位**：`'关系均成立'` 看不出判据，人工复核时等于没有信息。
   要落 `缺陷短语 + 观测类型 + 跨层(platform×runtime) + 反证`，
   判无的落命中的关系与理由。实测改后 reason 从 8 个字变成可读的判据。

---

## 13. 记忆：事实自动生成 + 判断人工维护，两者必须分开

**现象**：项目的「进度记录」是 `AI_NIGHT_PROGRESS.md`，**547KB 的追加日志**，
头部还停在 1 天半前。新会话要知道「现在什么状态」得读几百 KB，而且读到的是过期信息；
用户连问五次「skill 的记忆有没有用起来」，说明这个问题从外面看是明显的。

**根因**：把「事实」（进度数字、谁在跑、硬约束）和「判断」（待办、已知问题、决策原因）
混在同一个手写文件里。手写的事实必然过期；自动生成的判断必然空洞。

**改法**（本 skill `memory.md` 没覆盖的一层：**主 agent 的现状入口**）：
- `gen_state.py` 每 30 分钟**自动生成** `STATE.md`，内容全部来自
  `oss.sqlite` + `crontab -l` + `/proc`：一句话现状、在跑什么、关键进度、硬约束、文件索引。
- `NOTES.md` **人工维护**判断类内容（待办 / 已知问题 / 关键决策原因），脚本原样 append 进 STATE.md。
- `STATE.md` 顶部写明「自动生成，勿手改」，手改会在下次刷新时丢。
- 接手顺序：`STATE.md`（30 秒看清现状）→ `NOTES.md`（有什么坑）→ 按需 grep 547KB 详录。

**验证**：生成后立刻发现两个我此前不知道的本项目 cron（`diff251-serve.sh` 每 2 分钟、
`keepalive.sh` 每 5 分钟）——这种「你不知道它在跑」正是手写文档必然漏掉的。

**副产品**：STATE.md 让 P0 结论分布第一次可见——`S3_INFO_GAP 193 / 237`，
即 P0 里绝大多数确实设计不出用户端到端复现。这个数字此前只存在于我的口头汇报里。

**可复用的原则**：
- 事实由脚本从**一手数据源**（库、crontab、/proc）生成，不要人写、不要从日志里摘。
- 判断由人写，脚本不许编。
- 两者物理分开，用固定文件名（`STATE.md` / `NOTES.md`），并在入口写清「谁覆盖谁」。
- 每 30 分钟刷新，且**挂在已有的巡检循环里**，不新增进程。

---

## 14. 多个循环写同一个 sqlite：落表失败静默丢数据，表现为「同一 sha 被审多次」

**现象**：日志里 `39d1d09684`、`3a27669063` 等 sha 各出现两次，但 `p1_trial` 表里只有 64 行
（三批共 90 条判定，只落了 64 条）。`pending()` 返回的 744 条**没有重复**。

**根因**：
```python
for _ in range(6):
    try:
        c.execute('INSERT OR REPLACE ...'); c.commit(); break
    except sqlite3.OperationalError:
        time.sleep(1.2)
# 6 次都失败 → 什么都不做，直接下一条
```
6 次重试全失败后**静默跳过**，这条判定丢了；`NOT IN (SELECT sha FROM 表)` 下轮又选中它，
于是「审了、没落、再审」，白烧模型调用。触发条件是并发写：`p0_trial_loop`（fetch_body +
p0_full_trial + deep_reach + s3_backfill）与 `p1_trial_loop` 同时写一个 `oss.sqlite`。

**已改**：
- 落表失败不再静默：打印 + `stat['WRITE_FAILED']` 计数，能立刻看出并发冲突。
- 停掉已空转的 `p0_trial_loop`（P0 审判 237/237 已完成，它只剩 s3_backfill 在降级），
  减少并发写源。停后单批 8 条全部落表、`WRITE_FAILED=0`。

**顺带清理**：发现两个 `find / -maxdepth 6/8` 全盘搜索进程仍在跑（某个已死 agent 的残留），
严重拖 IO。清理一律按 PID，不用 `pkill -f`（会连带杀掉正在跑的 agent，见第 5 条）。

**可复用原则**：
- 写库重试必须有「最终失败」分支，不能只 `sleep` 后继续。
- 同一时刻只让**一个**循环写主库；其余改成只读或干脆停掉。
- sqlite WAL + `busy_timeout` 只能缓解，不能消除多进程写冲突。

---

## 15. 环节的「产出」必须成为下游的「输入条件」，否则白算

**现象**：`deep_reach` 已判定 32 条「可达已建立」（含完整 file:line 链路、用户入口、
使用性质、置信度），但 `judge_condition` 里只有 6 条有复现输入——**26 条链路白算了**。

**根因**：下游 `s3_backfill` 的取数条件是
`verdict IN ('CANDIDATE','NEEDS_E2E_TRIAL')`。
但一条条目可能**先**被判 `S3_INFO_GAP`（那时还没做深度分析），**后来**才被判
「可达已建立」——它的 verdict 不会自己变回来，于是永远不在待办队列里。

**已改**：新增 `reach_refine.py`，取数条件改成按 `deep_reach.reachability LIKE '已建立%'`
`AND sha NOT IN (SELECT sha FROM judge_condition)`，与 verdict 解耦。

**关键设计差异**：
- `s3_backfill` 是「让模型设计路径」；
- `reach_refine` 是「把已验证链路**转写**成结构化字段」——链路作为事实喂进去，
  明确禁止模型另编路径。所以能直接标 `reachability=已建立`、允许 A/B 级。

**效果**：条件从 13 条 → **45 条**；可达已建立的 34 条 **100% 覆盖**（缺口 0）。
实跑 3 条全部一次通过（`P1/C/E4`、`P1/B/E2`、`P1/B/E3`）。

**可复用原则**：
- 多阶段流程里，每个阶段的「产出表」都要检查**有没有下游在消费**。
  只写不读的阶段等于没做（本项目浪费了 26 条已验证链路）。
- 一旦上游已经产出「已验证事实」，下游应做**转写**而不是**重新推理**——
  前者稳定且可标高等级，后者会重新引入不确定性。
- 幂等键要选「产物」而不是「中间状态」：这里用 `sha NOT IN judge_condition`
  （产物是否存在），不用 `verdict`（会被别的阶段改）。

---

## 16. 「未复现」不等于「误报」——一律当失败处理会误杀真机必须的条目

**现象**：29 条真机未复现，直觉是「全部该在派单前拦住」。
逐条审计（`rootcause_audit.py`，模型读实测过程摘要 + 归因）后结果完全不同：

| 判定 | 条数 | 含义 |
|---|---|---|
| 该拦-构建前提不满足 | 17 | build 事实不满足，派单前可静态判定 |
| 该拦-量级不可达 | 5 | 触发量级超真机可接受窗口 |
| **不该拦-真机必须** | **5** | 需真机实测入口行为才能判定，拦了就是误杀 |
| **不该拦-检验标准有误** | **1** | signal 写错维度，不是缺陷不存在 |
| **不该拦-意外发现** | **1** | 跑出了别的可测量缺陷，是收益不是损失 |

**如果把 7 条「不该拦」当误报处理掉，等于把「真机必须验证的」和「意外收获的」一起扔掉。**

**典型误判风险**（审计原文）：
> 6/6 次文件名为空、实验组 0/3、对照组 0/3 均无预填，需真机实测入口行为才能判定预填是否发生

这条从任何静态信息都推不出来，只能真机跑。

**检验标准问题也查出来了 1 条**（比「该拦」更有价值）：
> signal 应为内存安全检测构建（如 ASan）下的释放后使用告警/错误事件，
> 而非零售构建的崩溃次数、Windows 应用错误事件或退出码

即：UAF 类缺陷在零售构建上本来就不会崩，用「崩溃次数」当 signal 必然测不出来——
这是**判定标准本身错了**，不是缺陷不存在。

**可复用原则**：
- 失败的归因必须**分类到「可机械化拦」和「只能真机」两个桶**，不能笼统算误报率。
- 审计「未复现」时优先找**检验标准错误**（signal 维度不对），这类问题的修复收益
  远大于多加一条过滤规则。
- 审计输出的规则要写成**关系型描述**（「构建版本 ≥ 修复版本 → 前提不成立」），
  不写具体 commit 名，否则换上游即失效（第 8 条同类教训）。
- 用脚本 + 模型逐条审计（29 条 × 1 次调用），不要用 agent 跑——见第 10 条。

---

## 17. 监督器对「cron 脚本任务」完全盲区（已补第三个后端）

**现象**：项目里真正在跑的是四个 cron 脚本（P1 审判、补端到端输入、深度分析、巡检），
但 `supervisor.py` 只认 taskctl 的 sqlite、`supervise_agents.py` 只认 agentctl 的 agent 目录。
两边都返回「没有任务」——**脚本任务出问题时没有任何监控**。

**脚本任务的失败形态和 agent 不同**：
- 不是「进程死了」（cron 每次都是新进程，死了就是没跑）
- 而是「进程活着但产出为零」「连续几批全是限流失败」「成功数卡住不涨」
- 这些只能靠**读日志 + 库指标**判断

**已改**：`scripts/supervise_jobs.py`，配置驱动（`jobs.yaml` 或内置默认）：
```yaml
p1_trial:
  log: p1_trial.log
  grep: "^\\[p1_trial\\]"
  db: "SELECT count(*) FROM p1_trial"
  expect: P1 审判逐批产出结论
```
快照 = 日志末尾 N 行 + 产出计数 + 进程存活；模型判断 `ok/warn/alert/done`，
异常写 `ALERTS.md`，退出码 1 便于 cron 联动。

**验证**：快照能读到真实产出（`p1_trial` 145 条、最近 5 批的 `S1_FAILED` 波动 4→11→4→0→1），
模型能据此判断限流是否恶化。

**副产物（重要）**：`codebuddy -p` 单次调用**光启动就要 58 秒**（只回答两个字也 58s）。
所以监督类调用超时要给到 600-900 秒，不能按「模型推理耗时」估。
这也意味着**监督不宜高频**——每小时一次比每 10 分钟一次合理。

---

## 18. 监督器自身的四个坑（写对才有效，写错全是噪音）

给脚本任务做监督（`supervise_jobs.py`）时连踩四个，每个都会让监督**看起来在跑但结论无效**：

**① 用 codebuddy 做监督太慢 → 改用 knot**
`codebuddy -p` 光启动就 **58 秒**（只回答两个字也 58s），多实例并发直接卡死（>5 分钟无输出）。
`knot-cli` 同样一句话 **8 秒**。差 7 倍且 knot 免费。
→ 监督类调用一律走 knot，超时给 180s 足够。

**② PROMPT 漏了 `{snapshot}` 占位符 → 模型凭空编造**
快照根本没插进去，模型照着自己想象编了 5 个不存在的任务
（`daily-report-cron`、`webhook-retry-cron`…），还一本正经给出 warn/alert 判断。
→ 加启动自检：`if '{snapshot}' not in PROMPT: raise SystemExit(...)`。

**③ 没声明「信息已全给」→ 模型跑去查文件**
knot 输出「我需要先找到这些 cron 脚本的状态快照」「让我搜索包含 task_name 的文件」，
然后被截断，一行 JSON 都没有。
→ prompt 开头必须写「快照已包含全部信息，不要发起任何工具调用、不要查找文件，直接输出 JSON」。

**④ JSON 提取用非贪婪正则 → 被 reason 里的方括号截断**
`re.findall(r'\[.*?\]', out)` 遇到 `"reason":"日志末尾为[76/76]"` 就提前收尾，
JSON 不完整解析失败；贪婪版又会吞掉后面内容。
→ 必须**括号配对扫描**（数 depth），并跳过 `[任务规划中]` 这类中文标签。

**验证（最终跑通）**：
```
ok    p1_trial       末尾6批均有新判定行，产出计数184
warn  reach_refine   末尾两条同为fcaf525050重复记录，先S3_REJECT后OK
done  deep_all       日志已到[76/76]，76条全部处理完
```

**监督立刻抓到真问题**：`fcaf525050` 第一次 `S3_REJECT` 后没留任何记录，
被 pending 无限重试，第二次又通过了。**纯脚本看不出「同一 sha 先 reject 后 ok」这种逻辑矛盾，
只有模型读日志才能发现**——这就是「模型监督」相对「脚本判活」的价值。

---

## 19. 自动生成的现状入口能主动暴露「硬约束违反」，比人肉巡检可靠

**现象**：`STATE.md` 自动生成后第一眼就看到 `条件缺可达依据：❌ 6`。

查出来是 6 条历史脏数据：`reachability` 为空，却标了 `A/E1`、`B/E2`——
**没做深度可达分析，却声称「用户真实操作全链路」**。这是最危险的一类虚高，
因为派单时会按「用户会碰到」去跑。

**根因**：
- 校验函数 `check_e2e_consistency` **本来就有** `缺 reachability` 这条（第 337 行），
  三条写入路径（`s3_backfill` ×2、`reach_refine`、`judge_pipeline`）也都调了它；
- 这 6 条是**校验加上之前**写进去的历史数据，一直没人发现。

**处理**：没有 deep_reach 依据的降为 `C/E4` + `reachability='未核实：未做深度可达分析'`；
有依据的用依据回填。处理后硬约束全部归零。

**关键教训**：
- 硬约束不能只在「写入时」校验，还要在「现状快照里持续暴露」。
  写入校验只能拦住新增，拦不住历史脏数据。
- 自动生成的 `STATE.md` 在这里起了实际作用——**协议化的现状输出比人肉巡检可靠**，
  因为人不会每次都去数「有没有 reachability 为空的记录」。
- 校验新增一条规则后，要**回查历史数据**（`WHERE 新规则会拦的条件`），
  否则规则只对新数据生效。

**可复用做法**：在 `gen_state.py` 这类「现状生成器」里放一组**硬约束断言**，
每次生成都算一遍并显式标 ✅/❌。违反时不需要人记得去查，看文件就知道。

---

## 20. 告警必须出现在「接手的第一个视线」里，否则监督闭环是断的

**现象**：`supervise_jobs.py` 正常写 `ALERTS.md`，但 `grep -c ALERTS STATE.md` = **0**。
接手的人按约定只读 `STATE.md`，**永远看不到告警**——监督器等于白跑。

**根因**：监督器、告警文件、现状入口是三个独立产物，没有连成一条链。
写了告警没人读，和没写告警是同一件事。

**已改**（`gen_state.py` 增加 `alert_summary()`）：
- 读 `ALERTS.md`，把 `## 标题` 提成摘要；
- **放在 `STATE.md` 最顶部**，在「一句话现状」之前——
  接手的第一个问题应该是「有没有东西坏了」，不是「进度多少」；
- 超过 48 小时的告警不再顶在上面（避免旧告警永远挂着、变成噪音）；
- 结尾提示「处理后清空该文件或改名 `ALERTS.resolved.md`」。

**验证**：修前 `STATE.md` 顶部是进度；修后第一屏是
`## ⚠️ 有 1 个未处理告警（0.1小时前）— reach_refine — warn`。

**可复用原则**：
- **告警的终点必须是「接手者一定会读的那个文件」**，不是单独一个 alerts 文件。
- 告警要有**时效**（超过 N 小时降级为历史），否则会变成永久噪音，人就开始无视它。
- 监控链路要能一句话说完：**监督器 → ALERTS → STATE 顶部 → 人**。
  中间任何一环断开，前面的工作都不产生价值。

---

## 21. 「有没有用起来」要能一次算出来，不靠回忆

**背景**：用户连续问「这个 skill 有没有正确用起来」，我每次都靠回忆逐条说，
既慢又容易漏（说出来的是「我以为在用」，不是「实际在用」）。

**做法**：`scripts/selfcheck.py`，一次算完 8 个能力的状态：
- **在用**：有 cron/进程/数据，且在产出
- **闲置**：有能力但当前项目没有适用场景（**合理，不是缺陷**）
- **部分**：有用但缺一环（如 STATE.md 有、progress.md 无）
- **不该用**：存在但场景不匹配（如用 agent 跑长批量）

**判定方式全部是客观证据**，不看文档：
| 能力 | 判据 |
|---|---|
| agentctl | `registry.json` 里有 task 且进程存活（跨平台 `platform_util.pid_exists`） |
| supervisor | crontab 是否含 `supervisor.py` / 是否有 taskctl 库 |
| supervise_agents / supervise_jobs | crontab + 日志大小 |
| watchdog | `jobs.json` 里 `enabled` 数量 + cron |
| taskctl | 是否找到 taskctl 库文件 |
| 三层记忆 | `STATE.md` 刷新时间 + `NOTES.md` + `progress.md` 个数 |
| 脚本+cron 批量 | 项目里 `*_loop.sh` 有几个挂进了 crontab |

**实测输出**（2026-11-13 03:50）：
```
agentctl 多 agent 派发      ⏸闲置  7 个任务记录，全部已退出
supervisor（taskctl 后端）  ⏸闲置  未用 taskctl 队列
supervise_agents（agent）   ✅在用  已挂 cron 且有输出
supervise_jobs（脚本）      ✅在用  已挂 cron
watchdog + jobs.json       ⏸闲置  所有 watcher 已停用（用户主动停）
taskctl 队列               ⏸闲置  批量改用脚本+cron
三层记忆                    ✅在用  STATE 2分钟前刷新；NOTES 有；progress 0 个
脚本 + cron 批量作业         ✅在用  2 个循环已挂 cron
汇总: 闲置 4 / 在用 4
```

**可复用原则**：
- 「我们用没用 X」必须由**客观信号**判定（cron 表、进程表、文件 mtime、库行数），
  不能靠文档描述或记忆。
- **「闲置」不该被当成失败**。没场景就不用是对的；要区分「闲置（合理）」
  和「本该在用却闲置（遗漏）」。
- 自检脚本要**主动指出可疑组合**（本次它报出「agentctl 无活跃任务但仍挂着
  supervise_agents cron，每小时空跑一次」）——这种组合人不一定想得到。

---

## 22. 任务「完成」被监督器误判成「卡住」（两个原因叠加）

**现象**：早上 `ALERTS.md` 报两个告警，实际两个任务都**正常跑完了**：
- `p1_trial — alert`：「日志末尾连续 6 行均为 `[p1_trial] {}`，产出 810 卡住不涨」
- `deep_all — warn`：「日志停在 `[76/76]`，无更新迹象」

**两个原因**：
1. **脚本侧**：`pending` 为空时仍打印 `{'stat': ...}` → 实际打的是 `{}`。
   任务收尾后 cron 每 5 分钟空跑一次，日志末尾堆满 `{}`，看起来像「反复输出空结果=卡死」。
   → 改为明确输出 `已全部审完 810/810，本轮无待处理`。
2. **监督侧**：只看「日志末尾有没有新判定行」，**没有比对总数**。
   已完成的任务天然不再产生新行，必然被判停滞。
   → 配置加 `total` SQL，快照里直接标 `产出 810 / 总数 810 ← **已完成**`，
   并在 PROMPT 里写明「已完成的任务日志末尾可能是历史空行，不要因此判 alert」。

**修后验证**：
```
3 个任务，异常 0 个
done  p1_trial      产出 810/810 已达总数，末尾 6 条 {} 为空跑历史行
done  reach_refine  产出 58/37 已超总数，末尾多为 OK
ok    deep_all      产出 249/250，日志推进到 [76/76] 且有新判定行
```

**可复用原则**：
- **「完成」和「卡住」在日志层面长得一样**（都不再产生新行）。
  必须有一个独立的「应完成量」来区分，不能只看变化趋势。
- 任务收尾后 cron 会继续空跑，**空跑的输出必须有明确语义**（「无待处理」），
  不能输出空对象——那和「跑了但没产出」无法区分。
- 监督规则要针对「已完成」写显式例外，否则最正常的终态会被报成最严重的异常。

## 23. 企微 markdown 单条 4096 字节：长清单必须拆条 + 机械校验（2026-11-13）

**现象**：修复堆积提醒 392 条待合入只发前 5 条 +「还有 387 个」——用户明确说「截断太多，其实能发很多」。

**根因与改法**：企微 markdown 单条正文有 4096 字节上限，之前把它当「只能发短通知」的理由做了截断。正确做法：
1. 超限时**按优先级分组拆成多条**，每条开头标 `(1/4) P0 部分`，而不是省略内容；
2. 拆完**机械校验**：每条 ≤4096 字节、各条清单行数合计 = 总数——写个 10 行校验脚本跑一遍，
   比人眼可靠（本次实测 4 条 4015/4029/4009/2625 字节、行数合计 392）；
3. 发送前 dry-run 全量打印 + 只发 1 条真实测试，避免把几百条轰进群里。

**教训**：「平台有单条上限」的正确应对是**拆条**，不是**替用户决定少看内容**。


---

## 23. 搜索范围自我限制会造成「假性未定位」——根因是工具边界，不是源码没有

**现象**：真机已复现的 8 条结论里，6 条报「未定位」（WB 侧无调用点），报告出现不专业表述。
用户要求要么定位、要么确认不是问题后删除，不留含糊表述。

**根因（查实）**：
- WB 是 monorepo，`packages/workbuddy-server`（服务端包）源码就在仓库里；
- 但 `wb_source.grep` 硬编码只搜 `apps/workbuddy-desktop/src`，
  `deep_reach` / `source_locate` 的 SYSTEM prompt 也写「只搜 apps/workbuddy-desktop/src」；
- SSE 客户端、tar 解压、MCP 传输的调用点全在 `packages/` 里 → 搜不到 → 被判「WB 无此调用」。
  **这不是「源码里没有」，是「工具看不见」**。

**修复（三层）**：
1. `wb_source.grep` 加 `area` 参数：`'app'`（默认，兼容旧调用）/ `'repo'`（整个 monorepo）。
   注意 `run()` 会先 `cd e['root']`，所以 repo 模式的 target 用相对路径 `.`，
   不要用绝对路径（之前在这里踩过一次 None）。
2. `deep_reach` / `source_locate` 的 `do_tool` 改走 `area='repo'`，
   SYSTEM prompt 同步改写（「搜索整个 monorepo；调用点在 packages 里照常给
   file:line 并注明是服务端包，不算未建立/未定位」）。
3. 把「定位」设为**必须完成的环节**：真机已复现的条目不允许以「未定位」收尾，
   定位不到就扩大范围重跑，直到给出链路或给出「调用点在哪个包」的明确结论。

**重跑结果**：8/8 全部定位。其中 3 条调用点在 `packages/` 服务端包
（MCP SSE 传输 `agent-cli/src/node/mcp/mcp-transport-manager.ts:80`、
专家包解压 `workbuddy-server/src/expert/runtime/`、
专家包安装 `workbuddy-app/.../workbuddy-agent-adapter-next.ts:29346 installExpertFromUrl`），
5 条在 `apps/` 桌面端（自研更新链路、CLI sidecar、会话切换 IPC
`browser-native-host.ts:111`、代理注入、随包资产同步）。

**衍生事实**：WB 的暴露面不只桌面端——服务端包 `packages/workbuddy-server`、
`packages/agent-cli`、`packages/workbuddy-app` 也在调用内核能力。这影响后续扫描的范围口径。

**可复用原则**：
- 「工具搜不到」≠「代码不存在」。判定「WB 无此调用」之前，必须确认**搜索范围覆盖全部源码**。
- 给 agent 的工具边界（能搜哪里）必须写进 prompt，并且边界要**先验证**再固化
  ——本例的边界是拍脑袋写的，从来没验证过 packages 里有没有东西。
- 出现一类含糊表述（未定位/未判定/未核实）时，用含糊词全库扫描，
  通常能暴露整条流程的系统性缺口，而不是零星笔误。

---

## 24. 「--all 全量」与「只跑疑似」的语义要分清——我自己刚犯

**现象**：要给 P1 的 327 条疑似风险（NEEDS_E2E_TRIAL 304 + CANDIDATE 23）补深度分析，
启动时误用了 `--all`，它取的是**全部 807 条 P1 审判条目**——其中 391 条 NO_PHENOMENON、
85 条 NOT_CONSTRUCTIBLE 早已判「不是风险」，给它们跑深度分析是纯浪费（且把预计时间
从 4 小时拉到 10 小时）。

**根因**：`--all` 的语义是「覆盖全部审判条目（连判无的也补）」，设计初衷是补 S3_INFO_GAP
那类「生成输入失败但没判过可达性」的；而「疑似风险」应该用**非 --all 模式**
（where 过滤 verdict IN (CANDIDATE, NEEDS_E2E_TRIAL)）。两个语义都合理，但不能混用。

**已改**：停掉 --all，改用非 --all 模式（待分析 322 条）；
deep_reach 加 `--level`/`DEEP_LEVEL` 支持 P0/P1（此前只写死 p0_trial）。

**可复用原则**：
- 「全量补洞」和「跑疑似队列」是两种模式，参数要分开；启动前先看
  `待分析 N 条` 的 N 是否符合预期（324 vs 807，一眼就能发现不对）。
- 判「不是风险」的条目不需要再分析——它们已经是结论了。
  分析资源永远只花在「未定性」的条目上。

---

## 25. mcporter 双配置文件：`config add` 写 A、运行时读 B——headers 补错文件等于没配

**现象**：iwiki MCP 注册后一直 `auth required`，转 OAuth 又因远程 CLI 无浏览器卡死。
用户坚持「token 就是 km 那个，之前一直能用」。

**排查**：
- curl 带 km 的 PAT 直测 iwiki 端点 → **tools/list 成功**，token 完全有效；
- mcporter 调用却 401 → 转 OAuth → 超时。
- 对比两份配置才发现：`mcporter-internal config add iwiki ...` 把条目写进了
  **`<skill 安装目录>/config/mcporter.json`**（工作目录相关），
  而运行时读的是 **`/root/.mcporter/mcporter.json`**；
  我第一次只往 `~/.mcporter/` 加了 Bearer headers，实际读取的那份（skills/config/）没有 → 401。
  两份都补上 headers 后立即成功。

**教训**：
- mcporter 存在**双配置文件**：`config add` 的写入路径受 cwd 影响，与运行时读取路径可以不同。
- 排障顺序必须是：**curl 直测端点确认 token 有效性 → 再查客户端配置**。
  我反过来了（先信 mcporter 的 auth required 去搞 OAuth），浪费了一轮。
- `auth required` 在这个客户端里有两种含义：①真的没凭据；②**headers 没被读到**。
  遇到先 grep 配置文件而不是发起 OAuth。
- 大 body（整篇报告）不要走 mcporter 的函数调用语法——bash 层转义必坏（实测回显不执行）；
  用 urllib 直连 JSON-RPC，`json.dumps` 转义才可靠。

**已落地**：`sync_iwiki.py`（urllib 直连 saveDocument + getDocument 回读验证），
cron 每 30 分钟把 `reports/WB-上游开源扫描报告.md` 同步到 内部文档 docid=4059137877。

---

## 26. 批量脚本必须加单实例锁，否则「cron 兜底 + 手动启动」会重复分析同一批

**现象**：`deep_perf` 持续 `database is locked`，重跑反复崩。查 `ps` 发现
**4 个 `deep_reach.py --level P1` 同时跑**（已跑 49 分钟 / 3h47m / 2h49m / 1h49m）。

**根因**：
1. cron 的每小时兜底会启动新实例，**不检查是否已有实例在跑**；
2. 手动启动也不检查；3. 无单实例锁 → N 个进程拿同一批 pending，重复分析、抢写库。

**修法（三层）**：
- `deep_reach.py` 入口加 `fcntl.flock(LOCK_EX|LOCK_NB)`，锁文件按 level 区分
  （`.deep_reach_P1.lock`），拿不到锁直接 `sys.exit(0)`；
- bash 循环脚本（`perf_rerun.sh`/`catchup_judge.sh`）用 `exec 9>lock; flock -n 9`；
- 判「重复分析」的方法：`ps -eo pid,etime,cmd | grep <脚本名>` 看**同脚本是否有多个 PID**，
  而不是只看「有没有在跑」。

**顺带修的两个库问题**（同一根因的后果）：
- 共享 sqlite 连接在多写者下会持续 `locked`（即便 `busy_timeout=90s`）→ 落库改**独立短连接**；
- `INSERT ... VALUES(?,?,...)` 按位置写在加列后必错位（本项目已第三次）→ 一律显式列名。

**可复用原则**：
- 任何「cron 会反复拉起」的批量脚本，第一件事是加单实例锁；
- 出现 `database is locked` 先查**同脚本并发实例数**，再查锁参数；
- 「有没有在跑」不等于「跑得对不对」——要查是否**重复**在跑。

---

## 27. 能用 AI 判的，不要写成死规则——规则是兜底，AI 才是主力

**现象**：判断「上游缺陷在 WB 基线里存不存在」时，我先写了 `premise_check.py`：
用正则从 release notes 抓版本号 + 比大小，判 not_affected / needs_verify。
结果 10 条候选全判 `not_affected`——**因为我把「修复回移到 40」当成了「40 引入」**，
实际回移列表只证明「缺陷存在于那些版本」，反推「基线没有」会**漏报**。

用户纠正：**「AI 是很强的，流程要加强的是 AI。」**

**为什么规则不可靠（本例）**：
- 版本号是死的，缺陷语义是活的。同一句话「Also in 40, 41」，
  在「缺陷从 40 才有」和「缺陷从 30 就有但只回移到 40」两种情形下含义完全不同，
  正则分不出来，读得懂上下文的人/AI 分得出来。
- 更关键的是**功能层判断**：「大量 app-region 元素导致无响应」这条，
  版本号只能告诉你修复在 43.7.0；但真正该问的是「37.10.3 的 Electron 有没有 app-region 机制」。
  这个判断要读上游 API 文档/功能引入历史，是语义推理，不是版本比较。

**改法（三层，重点是第二层）**：
1. **机械层**（兜底，只挡铁证）：`root_cause_model.json` 加 R7「引入版本晚于基线」，
   仅当原文明确写 `introduced in X` 且 X > 基线时才拦截；
2. **AI 层（主力）**：S2 提示词明确要求 AI 综合判断三件事——
   ① 原文引入版本；② **缺陷描述的功能/对象/API 在基线里是否存在**（比版本号准）；
   ③ 回移列表只作辅助不可反推。结论必须三选一并写依据；
3. **审查层**：reviewer 审产出的前提判断是否站得住（已接）。

**可复用原则**：
- **规则负责「不可能对」的硬拦截，AI 负责「需要理解」的判断。**
  把语义判断写成正则，等于把复杂情况压成一个字节，必然错。
- 判断标准写进**提示词**，让 AI 每次自己跑一遍；脚本只保留「铁证拦截」。
- 写规则前先问：这条规则遇到反例会怎样？如果反例会**漏报**（比误报严重），
  就不该做成硬规则，只该做成「提示 + 交 AI 判」。
- 用户反复强调的这条，值得当成硬约束：**流程改进优先改提示词和审查，其次才加脚本规则。**

---

## 28. 统计口径选错，会把结论低估一个数量级——按「状态字段」统计会漏掉后补结论的条目

**现象**：报告第二章写「P0 终态真问题 8 条」，实际深度分析确认 **25 个独立缺陷**（36 条命中、去重后 25 个）。
差了一个数量级，而每一层数字都「看起来对」。

**根因**：统计 SQL 用 `verdict IN ('CANDIDATE','NEEDS_E2E_TRIAL')` 筛「进入深度分析的条目」。
但深度分析是**后补**的：一批条目在深度分析里被判「可达已建立」，而它们的 `verdict`
仍停在早期的 `S3_INFO_GAP`（信息不足）——被过滤条件排除，于是 33 条已建立全部漏统计。

**为什么难发现**：报告里每个数字都能自洽（8 = 4 深度 + 1 真机 + …），
只有把「verdict 分布」和「deep_reach 可达数」两张表交叉比对才会暴露。

**修法（顺序不能反）**：
1. **先回填状态**：按深度结论更新 verdict（`已建立 +32`、`已剔除 +163`），让状态字段反映最新结论；
2. **再改统计口径**：从「按 verdict 分类」改为「按是否有深度结论分类」
   （疑似 = `REACH_ESTABLISHED` ∪ `CANDIDATE` ∪ `NEEDS_E2E_TRIAL`，可达 = 其中 deep_reach 已建立）；
3. **去重要单独做**：同一缺陷有多个 backport 版本（如 permission UAF 4 个、PowerMonitor 5 个），
   按标题归一化（去 PR 号、版本号、`[CP-xxx]` 前缀）后统计「独立缺陷数」，否则数字虚高。

**可复用原则**：
- **状态字段只反映它被写入那一刻的结论**。后补的分析结论必须回填状态，否则所有基于状态的统计都会失真。
- 报告里的关键数字，至少用**两条独立路径**算一遍（这里是 verdict 分布 vs deep_reach 可达数），
  对不上就查口径，不要挑一个用。
- 统计「缺陷数」和「条目数」是两回事：先按标题去重，再给数。否则一个缺陷的 5 个 backport 会被算成 5 个。

---

## 29. 「可达」之后还有一道关：派单判据必须按缺陷类型分档

**现象**：16 个逻辑/校验类 P0 缺陷（关闭子窗口崩溃、深链引号、TLS hostname、IPC 校验、
iframe 沙箱…）在库里躺了一整天没派出去。它们的 `commit_verdict` 是 P0、
`deep_reach` 是「已建立」——每一道关都过了，只卡在最后一步。

**根因**：派单时我问的是「能不能构造出『释放与使用重叠』的窗口」——
这是 **UAF 专属判据**。逻辑/校验类缺陷没有"释放窗口"这个概念，
被同一个标准判成「不可构造」，于是全部没派。

**推论**：判据必须按类型分档：
| 类型 | 判据 |
|---|---|
| UAF / 竞态 | 能否构造「释放与使用重叠」窗口（日常构建难命中，需 ASan/PageHeap） |
| 逻辑 / 校验 | 日常操作能否走到那段代码 + 结果是否可观测（**不需要内存窗口**） |
| 崩溃 | 操作路径是否可复现 + 崩溃率 |
| 功能/行为偏差 | 「正确行为 vs 实际行为」能否对照 |
| 性能/内存 | 变量能否到量级 + 超阈值 + 是否回落 |

**第二层修正**：UAF 也不能一律归「需专用构建」。PowerMonitor（合盖唤醒）、
zoom_controller（菜单缩放）、drag-drop（拖文件出窗）、lazy style（浏览器标签）、
MediaFoundation（播视频）—— 触发动作本身就是日常操作，用户正常使用就在反复制造那个时序，
普通构建多试几十次也有机会命中。**判「需专用构建」之前先看触发动作是不是日常操作。**

**第三层**：`INFO_GAP`（信息不足）必须与「无」分开统计。实测 1298 条判「无」的理由
是「未找到/信息不足」——那是「没查清」，不是「不是问题」。混在一起会让
「判无 6606 条」看起来像扎实结论，实际含 1298 条未验证。

**可复用原则**：
- 每一道关的判据，都要问「这个判据是不是只适用于某一类缺陷」；是的话就得分档。
- 「不可构造」这种结论，必须写明**依据的是哪类判据**，否则无法复核。
- 统计口径里，`信息不足` / `无法判定` 必须是独立状态，不能并入「不是问题」。

---

## 30. 「一次性改到位」= 先写审计工具，再动手改；不是逐处打补丁

**背景**：同一个 bug 形态在本项目犯了 5 次——「ALTER 加列排最后 + INSERT 按位置写」，
每次都是加列后才暴露，而且错位后数据静默写进错误字段，不报错。
第 5 次时用户要求「一次性改到位，不要重复或者遗留，哪怕一行行看清楚」。

**正确做法（先工具后改）**：
1. 写静态审计脚本 `audit_schema.py`：正则抓出所有 `INSERT INTO x VALUES(?,...)`，
   比对占位符数 vs `PRAGMA table_info` 的实际列数；
2. 一次性拿到**全部**错位清单（实测 95 处按位置写，其中 3 处真错位）；
3. 只改这 3 处，其余不动。

**为什么不能「一行行人工看」**：95 处 × 每处 1 分钟 = 1.5 小时，还会漏；
工具 3 秒全查完，且可反复跑。

**同类问题的统一处理**：
| 问题 | 一次性方案 |
|---|---|
| 10 个 enqueue 脚本各自实现，只有 2 个接评审 | 写 `enqueue_guard.py`，在各脚本的 post/req 入口统一插入 guard（不改调用点） |
| 脚本还会继续增加 | 写 `enqueue.py` 统一入口，老脚本全部标 DEPRECATED |
| 守卫只拦以后、队列里已有不合格任务 | 写 `recheck_queue.py` 复审在队任务，按 `physical_ready=0` 硬依据撤回 |
| 模型输出自相矛盾（正文说「未建立」布尔填 1） | 落库时加自洽校验，正文含否定词就强制清零 |

**关键认知**：
- 「改到位」的前提是**能枚举全部实例**。枚举不出来就会漏，漏了就等于没改。
- 枚举靠工具，不靠人眼。写完工具再改，改完再跑一次工具确认零残留。
- 一次性改完的判据：**同一个审计脚本再跑一次，输出「全部一致」**。

**顺带处理「遗留」的三个位置**：
- 数据库：重复主键 0 / 长度异常 0 / 空 result 0 / unknown 残留清空；
- 报告：正文无重复段落（只有表格分隔线重复，属正常）／顶部摘要与各章数字 5 项全部对得上库；
- 提示词：本质原则只注入 1 次（不重复），物理条件在原则与 S3 各 1 次（不同作用，保留）。

---

## 31. 规则清单让子 agent 空转 3 小时；输入提示词先讲因果（2026-11-15）

**现象**：派 5 路出题任务，提示词是「13 条铁律」规则清单。其中 `fix4-ag5` 跑了 3 小时、
600+ 事件、状态一直 working。看会话尾部才发现它其实早做完了：
四档里等价改写 3/4，唯一挂项是「忘了把 ROOTCAUSE.md 拷进测试目录」，
它自己都写了 `I forgot to copy ROOTCAUSE.md`，却继续在
「Let me do one last check」「最后核对一下」之间循环。

**根因**：提示词只给条款，没给「为什么」和「什么叫做完」。
模型不知道哪条已满足、更不知道可以收工；门禁能拦错，拦不住绕圈。
用户点醒：「AI 都和你一样，你能懂得他们都能懂」——讲清因果它自己会推导。

**修法（以 md 引导为主；工具能力上游已备齐）**：
- `templates/tasks/_done-contract.md`：四段（真实事故的因果 / 四条完成判据 /
  归档降级是合格交付 / 时间纪律），含「重复核对不产生新信息」「补一次文件搬运即可，不要再开一轮探索」。
- 上游本就有 `taskctl plan --goal`（一句话拆任务）、`manager.py` 的 goal refinement 与
  `guidance.md` 注入、`supervise_agents.py` 的 nudge。**真正缺的不是插嘴能力，是输入 md 没告诉
  AI「为什么」和「什么叫做完」**。所以本次主场是模板与 README，不重复造 CLI 轮子。

**验证**：对 4 个 queued 任务直接 `send`、对 1 个 working 任务先按 PID TERM 再 `send`，
5 路事件数全部增长（565/622/701/647/493），PROGRESS 里出现审判器与收工字样；
不是假绿灯（`send` 返回 0 也可能只是入队）。
5 道重做题最终单题审判 5/5 FAIL 0。

**顺带修的预存 bug（平台适配第二轮）**：
- `deadman.py::process_alive` 直接 `os.listdir("/proc")`，macOS 上抛 FileNotFoundError；
- 4 个脚本写死 `CB_BIN=/usr/local/bin/codebuddy`，而 macOS 真路径在
  `~/.nvm/.../bin` 或 `/opt/homebrew/bin`，**派单会打到不存在的二进制**；
- 统一到 `platform_util.resolve_bin`（环境变量 > 候选路径 > PATH）与
  `pid_exists` / `process_alive` / `os_kind`，并补 `tests/test_platform_util.py`
  （11 项，覆盖 linux/macos/other 与「Linux 但 /proc 未挂载」）。
- 全量 `pytest tests/ -q` → **28 passed**。

**教训**：机器类型自适应不能只改「报错那一行」。要枚举同形态的全部实例
（6 处 `/proc` + 6 处 BIN 常量），一次收敛到统一模块，再用跨分支单测证明
三种平台都走对；只在本机手测通过，等于只证明了 macOS 这一条分支。

**教训**：判断任务是否正常，不能只看「事件在涨 / 进程活着」；
要看最近 N 条事件有没有产生**新的落盘文件或新的数字**。这条已写进
`orchestrator.md` 三·十二作为监督侧后续增强方向。

## 32. 「成熟」的判据：枚举同形态实例 → 单一权威源 → 跨分支单测 → 文档对账（2026-11-15）

用户要求「其他类似的，都成熟一点」。按第 30 条「一次性改到位」的方法扫全仓，
发现三类半吊子，处理方式一致：

| 半吊子 | 现象 | 收敛 |
|---|---|---|
| 模型红线 | `agentctl.py` 与 `taskctl.py` 各写一份逐字相同的 `ALLOWED_MODELS`，零单测，改一处忘另一处就漂移 | `scripts/model_policy.py` 唯一权威源（CB/KNOT 两套清单 + `assert_model`），两脚本引用；`tests/test_model_policy.py` 8 项含「派单入口真的会拒绝贵档」 |
| 判活 | `agentctl.alive()` 与 `platform_util.pid_exists()` 语义重复 | `alive()` 变薄封装，10 处调用点不动 |
| 文档数字 | README 写「28 项回归测试」实际 36；SKILL.md 写「14 个有效文件」实际 20+ | 新增 `scripts/doccheck.py`：跑 pytest collect 对账测试数、FIELD-NOTES 最大编号、命令速查引用的脚本是否存在、导航表是否漏新模块、是否又出现第二份白名单 |

**过程中被自己的门禁连抓三次**（这正是它该做的）：
加 `doccheck.py` → 脚本数 11→12；加 `test_doccheck.py` → 测试数 36→40；
README 故意改错数字 → 立刻报「写 99 项，实际 36 项」。
**结论：文档里任何写死的计数都会过时**，最终改成动态表述
（「项数以 doccheck.py 对账为准」），门禁反过来检查「有没有又写死数字」和「导航表漏没漏模块」。

**没做的**：`_tail` 在 4 个脚本里两份近似实现（宽度 160/200 不同），
收敛收益小、改动面大，判定为过度重构，保留现状并写明理由。
**成熟 ≠ 把所有相似代码都抽成模块**，判据是「会不会漂移、会不会误判、有没有单测证明」。

**验证**：`pytest tests/ -q` 40/40；`doccheck.py` OK；`selfcheck.py` 8 项正常。

## 33. `--help` 冒烟是假绿灯：贪婪正则吞掉 8 个函数，提交出去才发现（2026-11-15）

**现象**：为收敛模型白名单，用正则替换 `agentctl.py::alive` 时写成
`re.search(r'def alive...[\s\S]*?\n    return False\n')`，贪婪匹配一直吃到后面，
连带删除 `read_int` / `session_file` / `session_events` / `tail_session` / `dur` /
`now_iso` / `build_cmd` / `spawn` / `launch_task` 共 8~9 个顶层函数。
当时验证做了 `--help` 冒烟（6 个入口全 OK）+ `pytest 40/40` + `doccheck OK`，
**全部通过**，但 `agentctl status` 直接 `NameError: read_int`、派单会打不到任何进程。
更糟的是这个坏版本被 commit + push 了（`b56bae6`），下一轮要用 `status` 才发现。

**根因**：
1. `--help` 由 argparse 在 `main()` 早期返回，**根本不执行业务分支**；
2. 现有 pytest 全测的是库函数，没有一条真的 spawn 一个 CLI 子命令去看它能否跑完；
3. 大范围 `re.sub` 替换函数体时，没有前后对比「顶层函数集合是否守恒」。

**修法（三层，全部落地）**：
- 从损坏前最后一个完整提交 `d71a318` 整体恢复 `agentctl.py`，只做三处**精确**替换
  （加 import / 白名单常量换成引用 / alive 换成薄封装），不再用宽正则改函数体；
- `tests/test_cli_smoke.py` 6 项：真的执行 `agentctl status`（含 `--json` 解析）、
  `taskctl stats/list`、`selfcheck`、`doccheck`，断言输出里没有
  `Traceback/NameError/AttributeError`；再加一条静态兜底，核对 11 个核心函数名都在；
- 静态函数集合守恒检查：改完 `def` 层面必须与改动前一致（`test_agentctl_has_all_core_functions`）。

**验证**：恢复后 `status` rc=0 且打印 5 路任务表；`pytest 46/46`；`doccheck OK`。

**教训（写进 skill 用法）**：
「冒烟」必须是**业务子命令真跑一遍**，不是 `--help`；
提交前若动过 AST/函数体，要对比顶层符号集合；
`pytest` 全绿不等于 CLI 可用——测试覆盖的是被 import 的函数，不是入口。

## 34. 能力坏了 ≠ 任务失败：审计"谁来感知感知者"

**现象**（2026-11-15）：TDSQL 静态扫描判定链路实际死了 **62 小时**（最后一次判定 11-12 17:44），
但死士巡检每 2 小时都判"全部正常"。

**根因链**：
1. grpcio 被降到 1.62.2，而生成的 `repomind_pb2_grpc.py` 要求 >=1.74 → 客户端初始化直接抛 RuntimeError；
2. 每次判定都异常 → 全部走 transient 重试 → 无判定入库；
3. 死士只看「进程活 / 日志新鲜 / 可判定队列数」——队列恰好空（所有条目无 diff），
   于是"没活干"掩盖了"干不了活"。

**修法**：
- `pip install "grpcio>=1.74"` 恢复能力（升级后真实调用返回正常）；
- 死士新增两类检查：`tcp_probe`（依赖服务端口可达）+ `cmd_probe`（能力初始化命令 RC=0），
  把"能不能干活"作为独立维度探测，与"有没有在干活"分开；
- 项目侧另加「告警链路」检查（近 24h must 告警是否发送失败）。

**原则**：监控分三层——① 进程/心跳（活着吗）② 产出/队列（在干活吗）
③ **能力探活（干得了活吗）**。前两层全绿而第三层坏，是静默事故的标准形态。
凡是"依赖外部服务/客户端库/凭证"的链路，都必须有第三层。

**同批完成的通知补全**（用户要求"所有感知/异常都要有通知"）：
统一告警层 `tools/alert.py`（key 去重 + alerts.jsonl 全留痕 + 真实发送判定），
接线：两个 runner 取队列失败/崩溃/case 超时/环境损坏、编译 8 个返回点、
cron preflight/daily 失败、merge_tracker 崩溃、QTA 换包失败、DB 重连耗尽、SSH 建连失败、
selfheal push 失败/前置检查失败、死士自身崩溃。
同批修复底层假成功：`notify.Send` 无返回值 + 上层无条件打印"sent successfully"
→ 按 HTTP 状态码返回 bool，`send_notification_to_user_group` 返回 (成功数, 总数)。

# codebuddy CLI 本机可用性与假绿灯排查手册

> 实测环境：本机 `<host>`，2026-11-11/12。适用场景：调用 `codebuddy -p` 没返回内容、只看到一行 plugin 提示、或程序把错误串当成 AI 结论写进了数据库。
> 结论先给：**本机 codebuddy 登录正常、不用额外 token。生产批量的长 prompt 继续用 `/usr/local/bin/codebuddy`（2.132.0）**——同一时刻实测它能 139.5s 返回有效判定，2.182.0 在 150s 内未返回。两个版本短任务都正常；两者都是 `#!/usr/bin/env node` 的 JS 脚本，`env -i` 干净环境都会报 `node: No such file or directory`，cron 能跑是因为 PATH 里配了 node。两个二进制都不要删，2.182.0 那个路径正被 IDE 和其它进程使用。

## 一、先分清两个二进制

```
which -a codebuddy
# /root/.nvm/versions/node/v22.23.2/bin/codebuddy   -> 2.182.0（PATH 第一优先）
# /usr/local/bin/codebuddy                          -> 2.132.0
```

| 路径 | 版本 | 实测 `free-model` |
|---|---|---|
| PATH 默认 `codebuddy` | 2.182.0 | 连续 3 次返回 `{"type":"error","error":"Plugin runtime refresh settled wait exceeded 5000ms"}`，RC=0、stderr 空。错误码 `PLUGIN_REFRESH_SETTLED_TIMEOUT`，是 5 秒插件刷新等待超时，**不是二进制损坏、不是没登录** |
| `/usr/local/bin/codebuddy` | 2.132.0 | 正常返回 `收到` |

补充事实：

- `~/.codebuddy/.env` 里有 `CODEBUDDY_API_KEY`、`CODEBUDDY_OWN_TOKEN`、`CODEBUDDY_PARTNER_TOKEN`，本地已登录；`set -a; source ~/.codebuddy/.env; set +a` 之后 2.182.0 仍然报同一条 plugin 错误，所以**不是凭据问题、不是没登录**。
- 2.182.0 在 `-p`、`--output-format text`、`--output-format stream-json`、带/不带 `--model`、带/不带 `--tools ''` 下都一样报那条 error JSON。
- 稳定做法：脚本用环境变量 `CODEBUDDY_CLI_BIN` 选择 `/usr/local/bin/codebuddy`。**这是「选另一个已安装的二进制」，不是删除或替换 PATH 上那个。**

## 一·五、版本怎么选（2026-11-12 实测，别再照抄旧结论）

| 事实 | 实测 |
|---|---|
| 两个二进制的真身 | 都是 symlink → `@tencent-ai/codebuddy-code/bin/codebuddy`，首行 `#!/usr/bin/env node`，**都依赖 PATH 里的 node** |
| `env -i PATH=/usr/bin:/bin` | 两个都报 `env: 'node': No such file or directory` |
| 2.182.0 短任务 | RC=0、stdout=`收到`(7B)、stderr 空，**不再复现** `Plugin runtime refresh settled wait exceeded 5000ms` |
| 2.182.0 7KB 长 prompt | 120s 未返回（同一时刻 2.132.0 也在 100s 超时，属通道慢，不能单独归罪于版本） |
| 2.132.0 生产表现 | 批量判定单条 35~65s、失败率接近 0（已跑数千条） |
| 2.182.0 独有能力 | `--resume-create-missing`：`--resume` 时会话不存在则用同 id 新建空会话，而不是失败 |

**判断**：长短任务分开看，按场景选。

- **长 prompt 批量判定**（本项目静态扫描那种 7KB 输入）：用 2.132.0。实测同一时刻 2.132.0 139.5s 返回有效判定，2.182.0 150s 未返回。
- **短任务 / 需要 `--resume-create-missing`**：用 2.182.0。短任务实测 RC=0、输出「收到」、stderr 空；`--resume-create-missing` 是它独有（会话不存在时用同 id 新建空会话）。
- 不想依赖该参数时，等价做法是「先 `--resume`，秒退且日志含 `No conversation` 时改用 `--session-id` 新建」——`agentctl` 已内置。
- 切换只改一个环境变量：`CODEBUDDY_CLI_BIN=<对应路径>`；注意 cron 的 `PATH` 必须含 node。

## 二、最危险的坑：RC=0 的 error JSON 被当成成功

2.182.0 的表现是 **进程退出码 0、stdout 只有一行 error JSON**。任何只看 `returncode == 0` 或「输出非空」的封装都会判成 200 成功，然后把

```json
{"type":"error","error":"Plugin runtime refresh settled wait exceeded 5000ms"}
```

当作 AI 结论交给下游解析、写库。本项目 `业务项目` 里 `community_commits.tdsql_need_merge` 曾经出现的 JSON 残片脏值就是这么来的。

判定必须加内容检查（Python 同步封装末尾示例）：

```python
result = asyncio.run(execute_codebuddy_cli_async(...))
try:
    content, code, attempt, model_used, stats = result
    compact = str(content).replace(" ", "").replace("\n", "")
    if '"type":"error"' in compact:
        logger.error("CodeBuddy CLI 返回 error JSON，判为失败（不再假绿灯）: %s", str(content)[:160])
        return content, 500, attempt, model_used, stats
except (ValueError, TypeError):
    pass
return result
```

单测方式（不必真的触发故障）：

```python
from unittest.mock import patch
import <业务模块> as m
err = '{"type":"error","error":"Plugin runtime refresh settled wait exceeded 5000ms"}'
with patch.object(m, "execute_codebuddy_cli_async", return_value=(err, 200, 1, "free-model", {})):
    assert m.execute_codebuddy_cli("x", model="free-model")[1] == 500
```

## 三、可直接复用的调用形态

```bash
# 1) 最简：一次性问答（后台跑要 setsid + </dev/null，否则可能 TTY stopped）
setsid codebuddy -y -p '1+1=?' < /dev/null &> /tmp/cb.out &

# 2) 稳定版：指定旧二进制 + text 输出 + 免费模型
/usr/local/bin/codebuddy -p --output-format text --model free-model "只回答两个字：收到"

# 3) 项目里的 RepoMind 形态（带 MCP、流式、跳权限）
codebuddy --model free-model \
  --mcp-config ~/.codebuddy/mcp.json \
  --dangerously-skip-permissions \
  --output-format stream-json \
  -p "<prompt>"
```

第 3 种的工程细节（`repomind/codebuddy_cli.py` 内已实现）：

- prompt 超过约 500 字符时，用临时文件 + Node.js wrapper（`spawn` + `child.stdout.pipe(fileStream)`）传参，避免 ARG_MAX 和 64KB 管道截断；stdout 直接落文件，靠心跳监控增长。
- 环境变量 `MCP_TIMEOUT=1800000`（30 分钟），因为 RepoMind 初始化慢。
- 命令要 `start_new_session=True`、`stdin=DEVNULL`。
- 大 prompt 场景不要加 `--tools ''`：禁全部工具后，模型若被要求查文件会卡在「我要 grep」然后截断。确实要禁工具时，在 prompt 里写明「相关文件已全部给出，用文本推演验证语义，不要发起工具调用」。

一行自检（判断当前 PATH 下的 codebuddy 是否会给有效回答）：

```bash
out=$(timeout 60 codebuddy -p --output-format text --model free-model "只回答两个字：收到" 2>&1); \
  case "$out" in *'"type":"error"'*|*"Plugin runtime refresh"*) echo "BAD: $out";; *) echo "OK: $out";; esac
```

## 四、模型命名：codebuddy 与 knot 不能混用

| 通道 | 免费模型 ID |
|---|---|
| codebuddy CLI | `free-model`、`small-model`、`free-model-preview` |
| knot-cli | `free-model`（= codebuddy 的 `free-model`）、`free-model-preview`、`small-model` |

- knot 侧喂 `free-model` 会直接报 `不支持该模型: free-model,请检查模型是否全小写或存在`。
- codebuddy 的 `--model` 帮助里那些 `*-ioa`、`claude-*`、`gpt-*` 不是免费通道，不要拿来做并发。
- 代码里做一层别名映射最省心：`{"free-model": "free-model"}`，调用方写哪个都不会炸。

## 五、排查顺序（照这个走，不要一眼判成「没登录」）

1. `which -a codebuddy` + 各自 `--version`，确认是不是踩了 2.182.0。
2. 用 `/usr/local/bin/codebuddy` 跑一次最简问答，能返回内容就说明登录/凭据没问题。
3. 把 stdout/stderr 分开看：error JSON 可能出现在 stdout，而 stderr 是空的，RC 还是 0。
4. 检查调用方是否只看退出码；有则加 `"type":"error"` 检测。
5. 检查是否用了 `--tools ''`、`--agents` 单独传、`--system-prompt`（应用 `--system-prompt-file`）等参数坑。
6. 大 prompt 走 wrapper + 文件输出，别用管道直接接。

## 六、相关代码位置（业务项目，供排障时定位）

- `<业务模块路径>`：`execute_codebuddy_cli` / `execute_codebuddy_cli_async`、`_find_codebuddy_executable`、`FREE_MODELS`、`MODEL_FALLBACK_ORDER`。
- `<业务模块路径>`：knot-cli 通道、`free-model → free-model` 别名、单次超时与回落链上限。
- `<业务模块路径>`：`MTR_SKIP_REPOMIND` 开关、`_normalize_need_merge` 中英文判定归一化。

## 七、能不能删 PATH 上那个 2.182.0

**不能删。** 2026-11-12 复核时它还被这些活跃进程使用：

```
node /root/.nvm/versions/node/v22.23.2/bin/codebuddy -y                       # 交互会话，20+ 分钟
node /root/.nvm/versions/node/v22.23.2/bin/codebuddy -p --output-format stream-json --model free-model --max-turns 56 ...   # 其它用户任务，硬编码该绝对路径
```

- 该路径是软链，指向 nvm 的 `@tencent-ai/codebuddy-code` 包；删了会同时打断 IDE 交互会话和别的用户的任务。
- PATH 里 `/root/.nvm/versions/node/v22.23.2/bin` 被多个任务的 env 硬编码，删文件不会清掉引用。
- 报错只是初始化阶段的 5 秒等待超时，交互模式（`-y`）和别的进程仍在用；属于可重试/可回退的问题，不是废弃文件。
- 真要验证影响，最多把软链临时改名（可回滚），不要 `rm`。

## 八、根因：PATH 优先级决定二进制版本（对照 upstream_fix/cli.py）

参考 `upstream-fix-iteration/upstream_fix/cli.py`：它在 cron 里跑，`shutil.which("codebuddy")` 解析到 **`/usr/local/bin/codebuddy` 2.132.0**，所以一直正常。本 IDE 会话的 PATH 前几段是 codebuddy-server shim / remote-cli / … / `/root/.nvm/versions/node/v22.23.2/bin`，`codebuddy` 解析到 **2.182.0**。

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root sh -c 'which -a codebuddy; codebuddy --version'
# /usr/local/bin/codebuddy
# 2.132.0
```

2.182.0 的 `dist-server/codebuddy.js` 里有 `PluginRefreshSettledTimeoutError`（`PLUGIN_REFRESH_SETTLED_TIMEOUT`，默认 5000ms）；本机该刷新 settle 不了，于是 `-p` 直接返回 error JSON。2.132.0 没有这段逻辑。

**逐项排除（全都实测过，均仍报同一错误）**：

| 假设 | 实测 | 结论 |
|---|---|---|
| 没登录 / 缺 token | `~/.codebuddy/.env` 有 `CODEBUDDY_API_KEY` 等；`source` 后仍失败 | 排除 |
| 调用参数写错 | 按 cli.py 原样 `codebuddy -p <prompt> --output-format text --model free-model --tools default -y` | 排除 |
| IDE 注入的会话变量 | `upstream_fix.command.child_process_env()` 剥离后、`env -i` 最小环境下都失败 | 排除 |
| MCP / 用户设置加载 | `--strict-mcp-config --mcp-config '{"mcpServers":{}}' --setting-sources '' --settings '{}'` | 排除 |
| 二进制损坏 | 交互模式 `-y` 有活跃进程在跑；换 2.132.0 立即正常 | 排除 |

所以是 **版本 + PATH 优先级**，不是调用姿势。`child_process_env()` / `scrub_poisoned_env()` 解决的是**另一类**故障：从 IDE 会话继承的 `SERVER__PORT`、`CODEBUDDY_SESSION_ID`、`CLAUDE_*`、`TST_HACK_*`、`BASH_ENV`、`BASH_FUNC_*` 等把模型回调指向已失效的 IDE hook，表现为「进程活着但零输出卡死」。两者不要混为一谈；从 IDE 会话起长任务时，两件事都要做。

可复用的固定写法（别让 PATH 决定版本）：

```python
import os, shutil, subprocess
bin_path = os.environ.get("CODEBUDDY_CLI_BIN") or "/usr/local/bin/codebuddy"
print(subprocess.run([bin_path, "--version"], capture_output=True, text=True).stdout.strip())
# 起子进程时同时用 child_process_env() 剥掉 IDE 会话变量
```

诊断一行版：`shutil.which("codebuddy")` + `codebuddy --version`，先把解析到的绝对路径打印出来再判断，不要只看「报错内容」就猜登录/版本。

## 九、把 codebuddy 当作主批量通道（2026-11-12 实测）

**两种 429 不是一回事，别混为一谈**：

| 通道 | 429 内容 | 性质 | 正确应对 |
|---|---|---|---|
| knot-cli | `{"code":429,"msg":"too many requests"}` | 十几个项目共用的**全局并发池**，随在途数变化 | 按模型分桶、每模型 `Semaphore(2)`、降并发；重试无用 |
| codebuddy CLI | `429 您的使用量已超出频率限制，将在 YYYY-MM-DD HH:MM:SS UTC+8 重置，您也可以切换其他模型继续使用` | **单个模型/账号额度**，到点自动恢复，与并发数无关 | 该模型冷却到重置时刻，其余模型继续跑；到期自动重新纳入 |

codebuddy 的 `small-model` / `free-model-preview` / `free-model` 是**独立通道**，不走 knot 全局凭证池。2026-11-12 实测：十几个项目把 knot 池占到 8~16 路时，静态扫描走 knot 有 **63% 调用撞满 180s 超时**（372 次调用只成功 136 次）；同一批 prompt 改走 codebuddy 后单条 35~65s、失败率接近 0，判定吞吐从 5~7 条/小时提到 31 条/小时。

接入实现（`业务项目`）：

- `llm/LLMClient.py`：`<业务环境变量>=codebuddy` 分流到 `_call_codebuddy()`；`/usr/local/bin/codebuddy -p --output-format text --permission-mode bypassPermissions --tools '' --model <id> <prompt>`。每模型 `Semaphore(2)`，`small-model` 90s / `free-model-preview` 150s 按模型分别超时。
- `cb_available_models()` + `<项目私有状态文件>`：命中额度 429 时解析「将在 … 重置」把该模型冷却到那一刻，**持久化到文件**（runner 重启不丢），到期自动回归。候选池 `small-model,free-model-preview,free-model`，额度恢复后从 4 路自动变 6 路，无需人工改配置。
- `static_scan_runner.py`：每轮取可用模型算 workers（每模型 2 路），`ThreadPoolExecutor` 并发跑对比，**结果仍在主线程串行写库**，避免 state/DB 互相覆盖。

接入时踩到并修掉的 5 个坑：

1. **双模块路径**：`scan.py` 用 `from src.<业务模块> import ...`，runner 用 `<业务模块>`，是**两份模块实例**，`threading.local()` 不共享，线程里设的模型全部落到默认值。改成 `call_llm(..., model_override=...)` 显式传参。
2. **禁工具却没在 prompt 里禁止**：`--tools ''` 之后模型仍会输出 `<tool_call>Bash>` 想去 grep，并在那里截断，判定行根本没产生。prompt 必须写明「相关代码已全部给出，不要调用任何工具/搜索文件系统」；同时在封装里检测 `<tool_call` 判失败，避免半截输出写脏值。
3. **简写判定**：codebuddy 常写 `Need to merge: Yes.`，原正则只认 `need to merge this change`。解析正则要加 `(?: this change)?`，并配合枚举白名单归一化 `Yes/No/Not Applicable`。
4. **按模型速度差异**：同长度 7KB prompt 下 `small-model` 48~51s、`free-model-preview` 偶发 >90s，统一超时会误杀慢模型。
5. **重启遗留孤儿**：`kill -9 runner` 会留下 `ppid=1` 的 `codebuddy -p` 和 `chat-watchdog`，继续占额度/并发。启动清理要按 `ppid=1` + 本项目命令特征精确清，不要 `pkill -f`。

一句话结论：**批量判定优先走 codebuddy（独立额度、每模型 2 并发），把 knot 全局池留给别人的长任务**；两种限流分别按「降并发」和「整模型冷却」处理。

## 十、免费口径常见误解（2026-11-12）

**问：codebuddy 免费，是不是可以无限并发？**
不是。免费指**不扣费**（本机实测 hy 系列 `--spending-limit 0` 不拒绝），但账号有**额度限流**：429 文案明确写「您的使用量已超出频率限制，将在 <时刻> UTC+8 重置，您也可以切换其他模型继续使用」。这是按模型/账号的额度，到点自动恢复，与并发数无关；撞了以后应整模型冷却到通知时刻，其余 hy 模型继续跑。knot 的 429 则是另一套（全局并发/速率，无恢复时间通知）。

**问：既然免费，为什么本项目默认串行？**
并发口径见 SKILL 第十节：**每模型最多 2 路、全局上限 10**（旧版「本项目总量 2」是语义误读）。免费不等于无限，有账号额度限流；AIMD 从 2 起步探测，撞 429 自动降并发 + 指数静默。串行时记得按批次轮转 hy 模型，别把单模型额度用尽。

## 十一、串行时暴露的两个确定性失败坑（2026-11-12）

改用 1 路串行后，队列里 6 条连续 `transient`、零写库，查出来**不是限流也不是额度**：

1. **DB 内容含 NUL 字节**（`Bug#37142400` 的 `main_diff`）：把 `\x00` 塞进 `subprocess.Popen` 的 argv，直接抛 `ValueError: embedded null byte`，日志只有一行看不出是哪条。修法：源头 `mysql_diff_content / tdsql_content / commit_msg` 都 `.replace("\x00","")`，并在 `_call_codebuddy` 里再兜底清洗一次 `prompt`。
2. **`main_diff` 为空**：`compare_commit_with_tdsql` 返回 `{'success':False,'reason':'no_mysql_diff'}`。旧代码把所有 `success=False` 一律当 `transient` 重排，但数据缺失是**确定性失败**，重排一万次也不会有 diff，会永久占着队列。修法：`scan_one` 按 `reason` 区分，`no_mysql_diff / no_main_path / no_tdsql_file` 归 `invalid`（有限重试 2 次后隔离），429/超时/AI 异常才归 `transient`。

排查口诀：**串行下连续 transient 且零成功调用，先看日志里有没有 `无法获取 MySQL diff`、`embedded null byte` 这类确定性原因，别急着归因到限流**。另外串行时务必按批次轮转模型（`start_model = batch_no % len(models)`），否则 1 路永远只用列表里的第一个 hy 模型，把它账号额度用尽、其余两个闲置。

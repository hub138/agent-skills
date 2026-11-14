# watchdog：长任务断了自动接上（完整手册）

> 原 `watchdog（旧版）` skill 已并入本 skill（）。脚本、模板、配置格式、排查方法全部保留；新任务也可以直接用 `scripts/agentctl.py`（见 `orchestrator.md`）。
> 数据目录 `~/.codebuddy/watchdog/` 是**私人数据**（含真实路径与任务内容），不要读给别人，也不要建议公开。

## 一、原理

```
crontab 每分钟叫醒一次
  → 看门狗检查每个任务：进程还在吗？
     在   → 什么都不做
     不在 → 带上原会话 ID 重新拉起，发该发的那条指令
```

判断「活不活」有两条：进程没了，或进程还在但日志很久没动（假死，默认关闭）。
拉起有冷却和次数上限，防止一出错就整夜狂拉烧额度。

**核心原则：检查不花钱，拉起才花钱。** 检查可以密（1 分钟一次），拉起必须有冷却和上限。

## 二、什么任务值得上这套

三个都满足才继续，否则直接说用不上：

1. 要跑多久？几分钟的不用上；**几十分钟以上**才值得。
2. 会不会因网络抖动/进程退出而中断？不会中断的用不上。
3. 任务有没有**可写的进度文件**？这是关键——没有就先设计一个，再做续接。

## 三、快速开始

### 1. 起会话，固定 session id

```bash
cd <项目目录> && codebuddy -p --port 0 --session-id <英文任务名> "任务描述"
```

`--port 0` **必须加**：codebuddy 每次启动会起本地 HTTP 服务，端口记在 `~/.codebuddy/web-ui-port.json` 复用，常被已常驻实例占着，不加就报 `EADDRINUSE` 起不来。

`--session-id` 支持字母/数字/下划线/连字符/冒号，必须以字母或数字开头；不指定才由系统生成 UUID。两种都能用于 `--resume`。

### 2. 生成配置

```bash
bash <skill 安装目录>/agent-ops/scripts/install.sh    # 建数据目录并放模板
```

然后直接帮用户写 `~/.codebuddy/watchdog/jobs.json`。必填：`session_id`、`prompts`、`workdir`，其余用默认。

### 3. 装 cron 并验证

```bash
bash <skill 安装目录>/agent-ops/scripts/watchdog.sh install-cron   # 装/更新 crontab
bash <skill 安装目录>/agent-ops/scripts/watchdog.sh status         # 应能看到任务
```

`status` 看不到任务 = 配置没生效，回去检查 `session_id` 和 `enabled`。

## 四、jobs.json 全字段

一个 watcher 就是一个后台任务，`watchers` 是数组，可配多个。

| 字段 | 默认 | 说明 |
|---|---|---|
| `session_id` | 必填 | 要续接的会话 ID（自定义名或 UUID） |
| `prompts` | 空 | 该会话要执行的多条指令，见第五节 |
| `workdir` | `~` | 在哪个目录跑，决定加载哪个项目的配置 |
| `model` | `$WORKER_MODEL` | 模型 ID；默认取 `WORKER_MODEL`，按通道与任务挑；每模型 1~2 路、多模型设全局上限，**只用白名单内不超预算的模型** |
| `extra_args` | `["-y"]` | **无人值守必须保留 `-y`**，否则权限弹窗卡死 |
| `sandbox` | `true` | 拉起时带 `CODEBUDDY_IS_SANDBOX=1`，放宽权限防弹窗 |
| `check_interval_minutes` | 5 | 多久检查一次；挂掉后平均 2.5 分钟被发现 |
| `stale_minutes` | 0 | 日志多久没动判假死。**默认关闭**：`-p` 输出要等进程结束才刷，开了必误杀 |
| `restart_cooldown_seconds` | 60 | 两次拉起最小间隔，挡「一拉起就秒退」风暴 |
| `max_restarts` | 20 | 连续失败重启上限，0 不限 |
| `done_file` | 空 | 完成标记，留空用 `state/<任务名>.DONE` |
| `prompt_mode` | step | `step` / `cycle` / `first` |
| `enabled` | true | 设 false 临时停用，不用删配置 |

带 `_说明` 后缀的是注释字段，可删。改完立即生效，不用重启。

顶层还有 `cron_interval_minutes`（crontab 多久叫醒一次，默认 1）和 `defaults`（各任务的默认值）。

## 五、prompts：一个会话多条指令

| `prompt_mode` | 行为 | 适合 |
|---|---|---|
| `step` | 按顺序走，上一条**正常退出**才进下一条，走完自动收工 | 分阶段任务 |
| `cycle` | 每次拉起轮换下一条，走完回第一条，靠完成标记收工 | 周期性指令 |
| `first` | 永远只用第一条 | 长时间单任务（推荐） |

占位符：`{DONE_FILE}`、`{STEP}`、`{NAME}`、`{WORKDIR}`。
指令很长时写成 md 文件，用 `"file": "prompts/xxx.md"` 引用，比塞 JSON 好维护。

不配 `prompts` 时用内置指令：读进度 → 判断当前步骤 → 从第一个未完成继续 → 每步写回进度 → 完成后创建标记并停手。

## 六、提示词模板（决定续接质量）

**最重要的一条：必须要求 Agent 把进度写回文件。**

原因：会话上下文撑满会压缩，压缩后早年细节会模糊；只有落盘进度不会丢，resume 全靠它。

```markdown
你是任务「{NAME}」，工作目录 {WORKDIR}。

1. 先读 `{WORKDIR}/progress.md`，判断上次做到哪一步，从第一个未完成项继续
2. 每完成一步，**立刻**把结论追加进 progress.md（必须写，不能只在回复里说）
3. 判断标准：什么算合格、什么要排除、边界怎么判
4. 产出规范：写到哪个文件、什么格式
5. 收工条件：全部完成就创建 {DONE_FILE} 并停手

禁止：修改 {WORKDIR} 之外的文件；调用超过 预算阈值 的模型。
```

## 七、时间参数怎么定

- `cron_interval_minutes` 设 1 完全没问题，脚本开销可忽略
- `check_interval_minutes` 默认 5；想更快发现挂掉就填 1
- 真正要节流的是拉起：`restart_cooldown_seconds` + `max_restarts`

## 八、沙箱

`sandbox: true` 时拉起命令带 `CODEBUDDY_IS_SANDBOX=1`，沙箱内放行权限——无人值守没人能点确认，不开会被权限弹窗永久卡住。
代价是放宽了操作限制，**只对信任的任务开启**；不确定的设 `false`。

## 九、目录结构

skill 目录（可公开）：

```
scripts/watchdog.sh        主脚本（多任务检查 + resume 拉起）
scripts/parse-jobs.mjs     把 jobs.json 翻译成 bash 好读的形态
scripts/install.sh         初始化数据目录
scripts/selfcheck.sh       自检
templates/                 jobs.example.json、example.md
```

数据目录 `~/.codebuddy/watchdog/`（**私有**）：

```
jobs.json    你的任务配置
prompts/     你的提示词
state/       pid、退出码、当前第几条、完成标记
logs/        watchdog.log（拉起记录）、<任务>.run.log（Agent 输出）
```

## 十、命令

```bash
bash <skill 安装目录>/agent-ops/scripts/watchdog.sh status          # 看每个任务状态
bash <skill 安装目录>/agent-ops/scripts/watchdog.sh <任务名>         # 只检查某一个
bash <skill 安装目录>/agent-ops/scripts/watchdog.sh install-cron    # 装或更新 crontab
tail -f ~/.codebuddy/watchdog/logs/<任务>.run.log    # 跟 Agent 输出
tail -20 ~/.codebuddy/watchdog/logs/watchdog.log     # 拉起记录（排查最有用）
touch ~/.codebuddy/watchdog/state/<任务>.DONE        # 手动收工
```

## 十一、排查

| 现象 | 先看 | 处理 |
|---|---|---|
| 状态「已停」但没拉起 | `max_restarts` 是否达上限、是否在冷却期 | 调大上限或缩短 `restart_cooldown_seconds` |
| 状态「在跑」但没产出 | 进度文件有没有更新 | `-p` 输出要等结束才刷，日志不动是正常的；不要开 `stale_minutes` |
| cron 没生效 | `crontab -l` 是否有条目、路径对不对 | 重跑 `install-cron`；注意 cron 的 PATH 要能找到 node 和 codebuddy |
| 拉起后秒退 | `run.log` 尾部 | 查是否 `EADDRINUSE`（缺 `--port 0`）、缺 `-y`、长 prompt 的 `-` 开头行被当选项（命令里要有 `--`） |
| 一直重复拉起 | 任务是否真的能结束 | 用 `first` 模式 + 完成标记；确认提示词有收工条件 |

## 十二、常见问题

**为什么要 `--port 0`**：端口记在 `~/.codebuddy/web-ui-port.json` 复用，常被常驻实例占着；`--port 0` 让内核现分空闲端口，永不冲突。

**能接着已有会话跑吗**：能。`session_id` 填那个会话 ID 即可，此时不会新建，是纯续接。

**会话上下文会撑满吗**：会，撑满触发压缩。所以提示词必须要求每步写回进度文件。

**和 `agentctl.py` 什么关系**：`watchdog.sh` 管历史 `jobs.json`（支持多条提示词轮换）；`agentctl.py` 是新入口（自己指定 session id、多后端、会话文件绝对路径、`send` 追加输入）。两者数据目录不同，互不干扰。新任务优先 `agentctl`，旧配置继续用 `watchdog.sh`。

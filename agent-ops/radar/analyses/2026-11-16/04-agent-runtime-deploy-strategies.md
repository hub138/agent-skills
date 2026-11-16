# openJiuwen agent-runtime：策略化部署与生命周期

- 来源：2026-11-16 11:00 #4 / https://github.com/openJiuwen-ai/agent-runtime
- 分析提交：`<cache>/agent-runtime`（depth 1，2026-11-16）
- 类型：repo
- 相关性：2
- 结论：**skip（形态可借鉴，机制不适用）**

## 1. 核心循环

配置 + 元数据 → `DeploymentManager` 按 `DeployMode` 选策略（subprocess/docker/k8s）
→ 策略负责实例生命周期与持久化 → REST API 暴露 deploy/list/delete/health →
租户中间件注入 `user_id/space_id` 做隔离。

## 2. 机制拆解

### 2.1 策略注册表

- 证据：`management/openjiuwen_runtime/management/manager.py:346 get_strategy(mode)`；
  `:139` 遍历 `self._strategies` 初始化各策略的表；`:292` `strategy.stop()`；
  `:315` `strategy.delete_record()`。
- 形态：**每种部署模式自带表定义与生命周期方法**，管理器只做路由，不写 if/else。

### 2.2 可插拔的边界

- 证据：`manager.py:104` K8s 依赖导入失败时禁用该策略而不是整体启动失败。
- 形态：可选能力在启动时探测，缺失则降级并记录原因。

## 3. 与 agent-ops 的对照

| 维度 | agent-runtime | 本 skill | 差距 |
|---|---|---|---|
| 部署模式 | subprocess/docker/k8s | 只有本机进程 | 不需要多模式 |
| 生命周期 API | REST deploy/list/delete/health | CLI + SQLite 队列 | 形态等价 |
| 多租户 | 中间件注入 tenant | 单人使用 | 不适用 |
| 策略化扩展点 | 策略自带表与生命周期 | 存储层已隔离（换 Postgres 需改一处） | 已具备方向 |

## 4. 可移植性

- 策略注册表：本 skill 只有一种执行形态（CLI 子进程），多一层策略抽象没有第二个实现，
  属于「为扩展而扩展」。
- 启动时探测可选依赖并降级：这是个好习惯，但本 skill 的 CLI 探测已由
  `scripts/platform_util.py resolve_bin` 承担（环境变量 > 候选路径 > PATH），已具备。
- 多租户：明确不适用（单机单人）。

## 5. 判定与理由

`skip`。它不是坏设计，而是**解决的问题不同**：它要把 Agent 从开发态带到多租户生产态，
本 skill 要把单机上的多个 CLI 子 agent 管住。把它的部署抽象搬进来，只会增加
没有第二个实现的抽象层。可借鉴的只有「策略自带表定义」这一条形态纪律，
在将来真的支持第二种存储后端（Postgres）时再用。

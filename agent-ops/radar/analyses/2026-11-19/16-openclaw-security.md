# OpenAI：Securing persistent agents like OpenClaw

来源：20261116-f1ce83f7dbbe9dc6.md（developers.openai.com 博客）

## 机制
- 可信/不可信执行分离：网络、身份、沙箱是可信确定性代码；agent 及其生成的代码
  是不可信面——OpenClaw Gateway 独立容器/集群运行（remote harness execution）。
- 网络管控：强制托管代理、用户级配置不得扩大 allowlist、显式阻断云元数据端点。
- 全量观测：控制平面每个配置变更 + agent 所有 turn 全部留痕（锁定访问权限）。
- 规模：500+ 持久 agent 后台主动工作。

## 对照 agent-ops
可信/不可信分离：manager（可信，模型红线 assert 不可绕过）vs CLI 子进程（不可信面）
——形态已同构。网络 allowlist：agent-ops 未做（CLI 出网不受限）。
全量观测：decisions.jsonl + task_events + audit 已覆盖。

## 判定：skip
威胁模型不匹配：OpenAI 场景是企业内数百个 24/7 持久 agent，攻击来自内部
misaligned action；agent-ops 是单机个人、任务由本人发起、无持久驻留。
网络 allowlist 的真实触发条件：子任务开始访问非预期外部服务时再评估。

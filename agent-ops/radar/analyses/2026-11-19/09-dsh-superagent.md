# DSH Super-agent 双层架构（deepseek-ai/dsh-superagent-prototype）

来源：20261110-b2ecc96fd3ed614d.md（DeepSeek Harness 团队长文）

## 机制
- 双层架构：Router 持续运行做全局协调（收消息/分派/统一对外），不配 Bash 工具，
  职责边界焊死在系统结构里；Worker 隔离会话并行执行，挂完整工具链，不对人类说话。
- Ticket 工作单元：每任务关联自己的执行会话与目录，面板集中显示等待/审查/受阻。
- Trigger 两级过滤：高噪音低触发率下，Fast Path（确定性代码准入）滤掉大部分，
  Slow Path（LLM 按自然语言策略判断）处理候选；已订阅 Thread 走订阅直通直达 Worker。

## 对照 agent-ops（逐机制）
| DSH | agent-ops | 判定 |
|---|---|---|
| Router 不配工具 | manager 只决策不执行（2026-11-12 用户纠正） | 已同构 |
| Ticket 工作单元 | taskctl tasks 表 + outdir | 已同构 |
| Fast/Slow Path | 雷达 triage 确定性词表 + AI 深读 | 已同构 |
| 订阅直通 | 任务组 send → inbox 直达（不经 manager） | 本周刚落地 |
| 会话上限 3-5/人 | daemon 并发池 + 无人值守 | 已超越 |

## 判定：skip
四个核心机制 agent-ops 全部已具备或刚落地（订阅直通=任务组 inbox），
深读确认了现有设计的同构性。无新增可落地项。

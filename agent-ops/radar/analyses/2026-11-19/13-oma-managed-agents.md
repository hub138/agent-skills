# Managed Agents（OMA）云端托管平台

来源：20261112-0327607ca018140c.md（cubesandbox.com 博客，参考 Anthropic Managed Agents）

## 机制
Agent/Environment/Session/Events 四抽象；会话持久化、推理与执行解耦、
凭证托管、文件系统持久化；平台团队集中承担运行职责。

## 对照 agent-ops
| OMA | agent-ops |
|---|---|
| Session 持久化 | taskctl SQLite + 会话 jsonl |
| 推理/执行解耦 | worker 进程两层隔离 |
| Events | task_events + 组事件流 |
| 凭证托管 | 无（CLI 用本机凭证） |

## 判定：skip
平台级能力（多业务、凭证托管、集中运维）与单机个人 skill 不匹配；
四抽象中三个已等效。凭证托管在单机场景反而过度（凭证就在本机）。

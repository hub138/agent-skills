# TencentCloud/CubeSandbox（repo 深读，121.6MB）

来源：radar/state/cache/github.com/TencentCloud/CubeSandbox @ HEAD

## 结构
hypervisor/（微虚拟机管理层）+ agent/ + CubeOps/（配额运维）+ CubeTemplateCenter/
（模板中心）+ guest-init/——完整的 KVM 级沙箱基础设施，含 hypervisor 补丁与配额系统。

## 判定：skip
重量级基础设施，解决「并发跑不可信 Agent 代码」的隔离问题。
agent-ops 是单机个人 skill：子任务由 model_policy 白名单约束（只允许 free-model/free-model、
≤0.15 credits），不执行不可信代码，无多租户配额需求。接入即引入 KVM 运维负担。
触发条件：需要并发跑外部开源项目代码做基准验证时再看。

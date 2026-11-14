# 给企业更多 AI agent 控制权，与 NVIDIA 一起（Giving companies more control over their AI agents, with NVIDIA）

- 原文：[Giving companies more control over their AI agents, with NVIDIA](https://claude.com/resources/articles/giving-companies-more-control-over-their-ai-agents-with-nvidia)
- 来源：Anthropic（claude.com Resources），机构署名
- 发布：2026-09-28
- 译文说明：全文翻译；组件与治理机制部分取自文章引用的 [NVIDIA OpenShell 产品页](https://www.nvidia.com/en-us/ai/openshell/)（含四组件、治理原则、参考架构与 FAQ 机制辨析），文章正文与产品页正文互补、互不重复；术语保留英文原词；站内相对链接转为绝对 URL。

## 机制概览

9 月 28 日，NVIDIA 发布了 [Open Agent Safety Platform](https://nvidianews.nvidia.com/news/open-agent-safety-platform)，一个开放软件平台与参考系统设计，用于强化 AI 安全。Anthropic 与 NVIDIA 合作，为 agent 的整套结构（agent stack）加上额外的安全与控制层。

用 Managed Agents 构建的 agent 已经在安全 sandbox 里干活，NVIDIA OpenShell 在那个执行环境内部再加一层保护，控制 agent 能访问什么、能做什么。

## 安全 agent：架构与沙箱化

### 把 brain 与 hands 分开

agent 的一个风险是：不受信内容可能与 agent 一起进入 sandbox。agent 克隆代码库、读网页、解析工具输出、甚至安装包，其中任何一项都可能带上一段模型可能当作指令照办的文字（prompt injection），或者一段会运行的代码。业界普遍收敛到的架构解法是 [把「brain」与「hands」分开](https://www.anthropic.com/engineering/managed-agents)。

这意味着 harness、session 状态与凭据放在 sandbox 之外的持久基础设施上，sandbox 变成 agent 用来执行的一个工具。对任何构建安全 agent 的团队，这个架构选择是轻松的第一步。Claude Managed Agents 遵循这些原则，核心能力就是为安全 agent 开发而建，而 self-hosted sandboxes 让你把执行放在自己控制的基础设施上。

> 包内互引：brain 与 hands 解耦的完整机制（凭据留在 sandbox 外的 vault、environment 配置、session 持久化）见 managed-agents-evolution.md。

### Claude Managed Agents 的 self-hosted sandboxes

Managed Agents 为在企业环境运行而设计，带 self-hosted sandboxes。用 self-hosted sandbox 时，处理编排、上下文管理与错误恢复的 agent 循环留在 Anthropic 的基础设施上，而每个 session 的工具调用运行在你控制的环境里：你自己的基础设施，或者一个托管的 sandbox 供应商。代码执行、敏感文件、包、服务与数据都留在你的企业边界内，受你自己的安全与运行时控制。

![图：Claude Managed Agents 的 self-hosted sandboxes](https://assets.claude.com/10402619d2fe571f9ab4e44846896d667e7a6734.png)

### NVIDIA OpenShell 限定 agent 能触及什么

NVIDIA [OpenShell](https://www.nvidia.com/en-us/ai/openshell/)，NVIDIA 的开源软件，可以作为那个 sandbox 的 runtime。它治理并监视全部 AI agent 行为，对每个动作强制执行策略。除非有规则允许，OpenShell 拦截一切。它检查 agent 试图使用的每个工具，对 agent 访问的文件、网络连接与数据应用规则。规则在 agent 之外强制执行，OpenShell 记录它放行或拦截的每个决定。

团队可以从窄权限起步，审查日志，然后用 Claude 把规则收紧到任务所需的最小访问。OpenShell 的 policy prover 接着用数学证明确认：在你写的规则下，agent 能触及什么。

![图：Claude Managed Agents + NVIDIA OpenShell](https://assets.claude.com/5fed8f359097a21aa893263a4b26d9a2ae908b41.png)

### 团队在构建什么

公司已经在用 Managed Agents 加 self-hosted sandboxes 强化 agent 安全。[Clay](https://claude.com/blog/claude-managed-agents-updates) 把它的 GTM 工程 agent Sculptor 跑在一个 sandbox 里，agent 能挂载外部文件存储、即时安装包。[Rogo](https://claude.com/blog/claude-managed-agents-updates) 服务强监管行业的客户，所以把 agent 的代码跑在隔离的 microVM 里，代码与数据都留在自己的边界内。

## OpenShell 四组件

产品页给出 OpenShell 的组件构成：

### Agent Sandboxes

每个 agent 跑在自己的隔离 sandbox 里，没有直接网络访问。OpenShell 无特权运行 agent，限制它能触及的文件。它在内核里监视并过滤 agent 的系统调用，拦下不安全的调用，并通过单一安全通道把 agent 的请求代理给 supervisor 审批。

### Policy Prover

policy prover 是 OpenShell 的策略验证引擎。它用形式化验证检查两件事：策略是否保持在允许的访问边界内；提议的网络规则相比 sandbox 当前策略是否增加了有风险的访问。

### Gateway

gateway 是 OpenShell 的控制面。它认证用户、管理 sandbox 生命周期、把策略、设置与凭据下发给每个 sandbox 的 supervisor。它决定谁能做什么，并代理全部对 sandbox 的访问。

### Supervisor

supervisor 跑在 sandbox 之外，在运行时监督 agent，把 sandbox 连到 gateway。它在 binary、目标、方法与路径级别上按策略评估每个网络请求，只在策略允许处提供凭据。策略更新即时生效，每个「allow」与「deny」决定都有日志，形成完整审计记录。

## 治理原则

产品页把机制收拢成几条：

- 安全住在环境里，不在 model 或应用里。默认什么都不允许，权限按策略授予，强制执行发生在 agent 进程之外，那里既哄不走也绕不过。每次 allow 与 deny 都可审计。
- 任何 model、任何 harness、任何 agent，跨云、混合、本地、edge 与物理隔离基础设施，都在同一策略层之下。
- 治理在 AI model 之外：OpenShell 把 agent 怎么干活与它怎么跟环境及外界交互分开。agent 的行为被监视，每个动作被治理。
- 零信任访问：默认拒绝访问，按意图授予权限。OpenShell 在 agent 进程之外强制执行策略，独立于 agent 的推理或配合。
- agent 舰队安全运行：开放或闭源 model 都行，agent 与 harness 自选，跨部署形态用一个统一策略层治理整个 agent 舰队。

## 参考架构

NVIDIA OpenShell Reference Architecture：一个全开放的全套架构，由 NVIDIA OpenShell secure runtime、Vera CPU、Vera Rubin 系统与 BlueField-4 上的 NVIDIA Sentry 驱动，覆盖 AI 工厂、企业基础设施与 edge 的工业规模安全 agent。OpenShell 与 NVIDIA Vera CPU 一起，在工业规模上更高效地治理 AI agent。

## FAQ 机制辨析

产品页 FAQ 里的机制性内容：

- 谁能用：开发者（构建用工具、写文件、调 API、长时间运行的 agent）、平台团队（为开发者铺路）、安全与 IT 团队（需要一条更安全的路来治理 agent 执行，不给每个 agent 宽泛的宿主、网络、凭据或 model 端点访问）。
- 什么 agent 能跑：Claude Code、Codex、GitHub Copilot CLI、Hermes、LangChain Deep Agents、OpenClaw、OpenCode 等路径；model 无关、harness 无关，可带自定义 agent 与自定义 sandbox 镜像。
- 是不是 agent framework：OpenShell 不是又一个 agent framework。它设计为坐在 agent framework 与 harness 下面，包括 Claude Code、Codex、OpenCode、OpenClaw 与自定义 agent 整套结构。
- 是不是只是个 sandbox：sandbox 是为一个有边界的任务把进程与宿主隔开。OpenShell 是治理 agent 整个生命周期的 runtime。那个 runtime 包含沙箱化，还有 gateway 代理的凭据、身份边界、policy-as-code、策略强制的出站、inference routing、审计与状态、多 agent 与 subagent 工作流边界。区别在于：自主 agent 需要的是持续治理，不只是一次性进程隔离。
- 是不是替代身份、可观测、治理或安全工具：OpenShell 与企业生态集成而保持它们的地位。身份供应商、secret store、可观测系统、安全工具与治理平台仍是重要的周边系统。OpenShell 的角色是提供 agent runtime 边界，并在所选 runtime 上一致地强制执行策略。
- 与 Docker 或 Kubernetes pod 的区别：Docker 容器与 Kubernetes pod 是 runtime substrate。OpenShell 用这些 runtime（Docker、Podman、Kubernetes、VM 隔离），但加上 agent 专属控制：gateway 协调、sandbox 监督、策略强制的出站、供应商凭据处理、inference routing、日志。实际区别是 OpenShell 围绕 agent 的动作设计，不只是启动一个容器或 pod。
- 部署位置：开发者跑 agent 的地方，本地开发系统、本地环境、混合环境、云基础设施。支持的路径包括 Docker、Podman、Kubernetes（经 Helm）与实验性 VUM runtime；可跑在 NVIDIA DGX Spark 或 DGX Station 上，把 agent runtime、数据与 model 访问留在受控环境内。
- 云端 model：OpenShell 带 policy-aware inference router，把被允许的请求转发到云端 model 端点。
- Vera CPU 是不是必需：不需要。OpenShell 跑在各类 CPU 系统上；跑在 Vera CPU 上时，全 agent 工作负载（代码执行、工具使用、沙箱化、分析、数据管道与模型之外的编排）性能是 x86 处理器的 2 倍且更省电。

## 可用性

Claude Managed Agents 现已在公开 beta 可用。NVIDIA OpenShell 以 Apache 2.0 许可开源，在 [GitHub](https://github.com/NVIDIA/OpenShell) 与 NVIDIA [开发者资源页](https://docs.nvidia.com/openshell/latest/about/overview) 上可用。

想深入见我们的 [self-hosted sandboxes 文档](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)，并按 [cookbooks](https://github.com/anthropics/claude-quickstarts/tree/main/managed-agents/self-hosted-sandboxes/openshell) 设置你的 sandbox 供应商。

> 包内互引：模型层与环境层的分工、三种隔离模式与封锁教训见 contain-claude.md；Managed Agents 三代接口演进与 vaults 见 managed-agents-evolution.md；无人值守自动化的组件、书签续读与台账见 claude-agent-automations.md。

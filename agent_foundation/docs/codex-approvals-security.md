# Codex 智能体审批与安全

- 原文：https://developers.openai.com/codex/agent-approvals-security
- 来源：OpenAI Codex 官方文档（Agent approvals & security 页）
- 发布：2026 年现行版本
- 译文说明：全文翻译。官方站对脚本抓取有 Cloudflare 拦截，从中文镜像 developers.openai.ac.cn 抓取正文，对照检索摘要校订；镜像改写的链接恢复为官方原始 URL。

Codex 帮你保护代码与数据，降低被滥用的风险。本页讲怎么安全地操作 Codex，覆盖沙箱、审批与网络访问。如果你在找的是扫描关联 GitHub 仓库的产品 Codex Security，请看 [Codex Security](https://developers.openai.com/codex/security)。

默认状态下，智能体运行时网络访问处于关闭。在本地，Codex 用操作系统强制执行的沙箱限制它能接触的内容（通常限于当前工作区），再配合审批策略控制它在行动之前何时必须停下来征求你的同意。

关于 ChatGPT 桌面应用、Codex CLI 与 IDE 扩展中沙箱工作机制的概要说明，看 [Codex 沙箱机制](codex-sandboxing.md)。更广的企业安全视角，看 [Codex 安全白皮书](https://trust.openai.com/?itemUid=382f924d-54f3-43a8-a9df-c39e6c959958&source=click)。

## 从已退役的 `untrusted` 审批策略迁移

Codex 与 ChatGPT Work 不再支持 `approval_policy = "untrusted"`。这项退役设置可能让客户端无法启动。请把它从用户配置、项目配置、profile 文件、启动脚本与托管默认值里移除。交互式只读使用可以这样配置：

```toml
sandbox_mode = "read-only"
approval_policy = "on-request"
```

或者运行 `codex --sandbox read-only --ask-for-approval on-request`。

在 `on-request` 下，沙箱允许的命令无需审批即可运行、读取可访问的文件，并在启用时使用网络访问。

要保留更严格的命令审批规则，请省略显式的 `approval_policy`，在用户级 `~/.codex/config.toml` 里给项目加一个条目：

```toml
[projects."/path/to/project"]
trust_level = "untrusted"
```

随后，除非执行策略规则允许，命令都需要审批。这同时禁用项目本地配置。显式设置 `on-request` 会覆盖从项目派生的策略；托管的 `allowed_approval_policies` 必须包含 `untrusted` 才允许它。

## 沙箱与审批

具备 Work Cloud 本地访问权限的计算机有独立的本地与云端执行策略：

**云端执行**：Work 云容器使用现有的 Work 云策略。

**本地执行**：本地执行要求管理已连接的计算机。MDM 与旧版受管设备要求优先于智能体安全（Agent Security），后者优先于设备的系统要求文件。

对带本地访问的 Work 与 dots，启用托管策略时，受支持的全局策略适用于共享云编排器。Work 云容器与 dots 云计算机各自使用自己的执行配置与要求。本地与云端控制要分别测试。把编排器控制（含审批与 web search）保留在 Global 层。有专用控件时用专用的「允许的审批策略」与「允许的 web search 模式」控件，其余受支持字段用 TOML。把 Codex 示例应用到具备 Work Cloud 本地访问的计算机之前，先查 [配置参考](https://developers.openai.com/codex/config-file/config-reference) 确认字段清单与执行范围。

在桌面、网页与移动端之间切换不会授予对另一台计算机的访问。开启同步或扩大访问之前，先过一遍智能体安全基线，并在每个执行环境里各测一次允许的操作与被阻止的操作。看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration)。

Codex 安全控制来自协同工作的两层：

**沙箱模式**：Codex 执行模型生成的命令时，技术上能做什么（例如能写哪里、能否访问网络）。

**审批策略**：Codex 执行操作之前何时必须征求你的同意（例如离开沙箱、使用网络、运行受信任集合之外的命令）。

Codex 按运行位置使用不同的沙箱模式：

**[Codex Cloud（旧版）](https://developers.openai.com/codex/environments/cloud-environment)**：运行在 OpenAI 管理的隔离容器里，阻止访问你的宿主系统或不相关的数据。用两阶段运行时模型：setup 阶段在 agent 阶段之前运行，可以访问网络安装指定依赖；随后 agent 阶段默认离线运行，除非你为该环境启用互联网访问。为云环境配置的机密只在 setup 期间可用，并在 agent 阶段开始之前被移除。

**当前 Codex Cloud**：设置与任务期间凭据怎么处理，看 [环境变量与网络机密](https://developers.openai.com/codex/environments/cloud-environments#environment-variables-and-secrets)。

**Codex CLI / IDE 扩展**：操作系统级机制强制执行沙箱策略。默认包括无网络访问、写入权限限于活动工作区。你可以按自己的风险承受度配置沙箱、审批策略与网络设置。

在 `Auto` 预设（例如 `--sandbox workspace-write --ask-for-approval on-request`）下，Codex 可以自动读文件、做编辑、在工作目录里运行命令。

Codex 会请求审批的动作是：编辑工作区之外的文件，或运行需要网络访问的命令。只想聊天或做规划而不改任何东西时，用 `/permissions` 命令切到 `read-only` 模式。

Codex 还可以对声明了副作用的应用（connector）工具调用征求审批，即使该操作不是 shell 命令或文件改动。当工具声明了破坏性 annotation 时，破坏性的应用/MCP 工具调用始终需要审批（除非该工具同时声明了 read annotation，read annotation 优先）。

## 安全监控与暂停的任务

GPT-6 Astra 在 Codex 与 ChatGPT Work 里包含安全监控。监控异步运行，检测到潜在不安全的模型行为时可以暂停任务。暂停可能在触发它的活动发生之后才到达；监控不能替代沙箱、权限或对结果的审查。

任务被暂停时，读通知，在发现结果可用时审查它们。确认任务可以安全继续之后才能恢复。通知说任务已结束或不提供恢复选项时，无法从该界面恢复。

安全监控在任务期间评估模型行为。[自动审批审查](https://developers.openai.com/codex/sandboxing/auto-review) 在这些操作运行之前，评估本来就单独需要审批的操作。经自动审批审查批准的操作，仍可能属于监控随后暂停的任务的一部分。

## 网络访问

当前 Codex Cloud 网络设置看 [连接到服务](https://developers.openai.com/codex/environments/cloud-environments#connect-to-services)。Codex Cloud（旧版）看 [智能体互联网访问](https://developers.openai.com/codex/cloud/internet-access) 启用完整互联网访问或域白名单。

对 ChatGPT 桌面应用、Codex CLI 或 IDE 扩展，默认的 `workspace-write` 沙箱模式保持网络访问关闭，除非你在配置里启用：

```toml
[sandbox_workspace_write]
network_access = true
```

### 网络隔离

在受支持的托管 Codex Cloud 执行路径上，智能体安全要求会限制命令网络。Codex Cloud 环境的互联网设置单独生效。智能体安全里允许的域不会覆盖云环境互联网设置里的限制。这些命令网络控制本身不会禁用托管的 web search、应用或 MCP。ChatGPT Work Cloud 有独立的功能权限，不继承这些智能体安全要求。

托管命令白名单适用于使用托管代理的命令。策略允许完全沙箱升级且获得批准时，该执行可以绕过命令代理。窄范围的网络授权与完全沙箱升级是两回事。为预期的边界配置强制执行的审批与沙箱要求，并测试常规命令与升级命令。看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration#configure-network-access-requirements)。

网络访问通过适用于命令衍生的脚本、程序与子进程的目标规则来控制。命令网络访问已启用时，开启 `network_proxy` 功能把流量限制到配置的网络策略。只加域规则本身不会启用代理。

```toml
[features.network_proxy]
enabled = true
domains = { "api.openai.com" = "allow", "example.com" = "deny" }
```

一次性 CLI 会话里，只需要开关时用布尔简写形式，同时设置策略选项时用表格形式：

```bash
codex \
  -c 'features.network_proxy=true' \
  -c 'sandbox_workspace_write.network_access=true'

codex \
  -c 'features.network_proxy.enabled=true' \
  -c 'features.network_proxy.domains={ "api.openai.com" = "allow", "example.com" = "deny" }' \
  -c 'sandbox_workspace_write.network_access=true'
```

该功能改变已启用网络访问的强制执行方式；它本身不授予网络访问权限。结合 `workspace-write` 配置用 `sandbox_workspace_write.network_access` 决定命令是否有网络访问：

- 网络关闭 + `network_proxy` 开启：网络保持关闭，该功能不做任何事。
- 网络开启 + `network_proxy` 关闭：网络保持开启，有不受限制的直接出站访问。
- 网络开启 + `network_proxy` 开启：网络保持开启，出站流量受配置的网络策略限制。

代理功能也适用于 [权限 profile](https://developers.openai.com/codex/permissions#network-permissions)。profile 的 `network.enabled = true` 授予命令网络访问，`features.network_proxy = true` 激活对该 profile 域规则的强制执行：

```toml
default_permissions = "project-edit"

[features]
network_proxy = true

[permissions.project-edit]
extends = ":workspace"

[permissions.project-edit.network]
enabled = true

[permissions.project-edit.network.domains]
"api.openai.com" = "allow"
```

这个示例里如果省略代理功能，命令就有直接的网络访问，`api.openai.com` 允许规则不会限制它的目标地址。

管理员管理的 `experimental_network` 要求与用户功能开关是分开的。它们可以在没有 `features.network_proxy` 的情况下配置并启动沙箱化网络，但活动沙箱保持网络关闭时，它们不会开启网络访问。管理员端 `requirements.toml` 结构看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration#configure-network-access-requirements)。

#### 网络策略

域规则遵循白名单优先：

- 精确的主机名只匹配它自己。
- `*.example.com` 匹配 `api.example.com` 这类子域，不匹配 `example.com`。
- `**.example.com` 同时匹配顶级域与子域。
- 全局 `*` 允许规则匹配任何未被拒绝的公共主机。把 `*` 当成宽泛网络访问看待，可能时优先用带作用域的规则。
- `deny` 总是优先于 `allow`，全局 `*` 只对允许规则有效。

#### 本地与私有目标

默认 `allow_local_binding = false` 会阻止回环、链路本地与私有目标：

- 具体例外：命令需要本地目标时，加精确的本地 IP 字面量或 `localhost` 允许规则。
- 更宽的访问：只在确实需要更宽的本地/私有覆盖时才设 `allow_local_binding = true`。
- 通配符：通配符规则不算显式的本地例外。
- 解析后的地址：解析为本地/私有 IP 的主机名，即使符合白名单也保持被阻止。

#### DNS 重绑定保护

允许主机名之前，Codex 会做尽力而为的 DNS 与 IP 分类检查：

- 失败或超时的查找会被阻止。
- 解析为非公共地址的主机名会被阻止。

该检查降低 DNS 重绑定风险，但没有完全消除。完全防住重绑定需要在传输层固定解析后的 IP。存在恶意 DNS 的可能时，同时在较低层强制执行出口控制。

#### 危险设置

有两个设置会故意扩大信任边界：

- `dangerously_allow_non_loopback_proxy = true` 可能把代理监听器暴露到回环之外。
- `dangerously_allow_all_unix_sockets = true` 绕过 Unix socket 白名单。

只在严格受控的环境里使用它们。启用 Unix socket 代理时，即使请求了非回环绑定，监听器也保持仅限回环，沙箱网络不会变成通往本地守护进程的远程桥。

`network_proxy` 默认关闭。启用它时：

### 命令网络代理之外的流量

网络代理过滤在本地命令沙箱内部运行的脚本、程序与子进程。它不过滤 web search、应用或 connector 工具调用、MCP 服务器连接、浏览器或 Computer Use 活动、Codex 云任务，以及客户端的模型与身份验证请求。这些界面用单独的服务连接、功能设置、工作区策略或环境控制。

浏览器工具在访问源之前单独检查托管网络拒绝与排他白名单。浏览器源策略可以进一步限制网站访问、上传、下载与开发者工具。看 [托管浏览器控制](https://developers.openai.com/codex/enterprise/managed-configuration#control-browser-and-computer-use)。

对托管用户，把命令网络策略与 `allowed_web_search_modes`、已批准的 `mcp_servers`、以及面向应用/插件/浏览器/Computer Use 的功能要求这类控制组合使用。看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration)。

还可以在不给衍生命令完整网络访问的情况下控制 [web search 工具](https://platform.openai.com/docs/guides/tools-web-search)。Codex 默认用 web search 缓存访问结果。该缓存是 OpenAI 维护的网页结果索引，缓存模式返回预先索引的结果，不去获取实时页面。这减少了来自任意实时内容的提示词注入暴露。请把网页结果当作不受信任的内容。用 `--yolo` 或其他[完全访问沙箱设置](#常见的沙箱与审批组合)时，web search 默认用实时结果。用 `--search` 或设 `web_search = "live"` 允许实时浏览，或设为 `"disabled"` 关闭该工具：

```toml
web_search = "cached" # default
# web_search = "disabled"
# web_search = "live" # same as --search
```

外部网页访问应由搜索索引把守时，设 `web_search = "indexed"`。在 Codex 里启用网络访问或 web search 要谨慎。提示词注入可能让智能体获取并跟随不受信任的指令。

## 默认值与建议

启动时，Codex 检测文件夹是否受版本控制并推荐：

- 受版本控制的文件夹：`Auto`（工作区写入 + 按需审批）。
- 不受版本控制的文件夹：`read-only`。

按你的设置，Codex 也可能以 `read-only` 启动，直到你明确信任工作目录（例如通过新手引导提示或 `/permissions`）。

工作区包含当前目录与诸如 `/tmp` 的临时目录。用 `/status` 命令查看哪些目录在工作区里。

接受默认值，运行 `codex`。也可以显式设置：

```bash
codex --sandbox workspace-write --ask-for-approval on-request
```

```bash
codex --sandbox read-only --ask-for-approval on-request
```

### 可写根目录中的受保护路径

默认 `workspace-write` 沙箱策略里，可写根目录仍包含受保护路径：

- `<writable_root>/.git` 无论表现为目录还是文件，都按只读保护。
- `<writable_root>/.git` 是指针文件（`gitdir: ...`）时，解析出的 Git 目录路径也按只读保护。
- `<writable_root>/.agents` 作为目录存在时按只读保护。
- `<writable_root>/.codex` 作为目录存在时按只读保护。
- `<writable_root>/.aws` 作为目录存在时按只读保护。

保护是递归的，这些路径下的全部内容都是只读。

### 在没有审批提示的情况下运行

用 `--ask-for-approval never` 或简写 `-a never` 禁用审批提示。

该选项适用于全部 `--sandbox` 模式，所以你仍然控制着 Codex 的自主级别。Codex 会在你设定的约束范围内尽力工作。

需要 Codex 无审批提示地读文件、做编辑并运行带网络访问的命令时，用 `--sandbox danger-full-access`（或 `--dangerously-bypass-approvals-and-sandbox` 标志）。动手前请谨慎。

折中方案：`approval_policy = { granular = { ... } }` 允许你让特定的审批类别保持交互式，同时自动拒绝其他类别。细粒度策略覆盖沙箱审批、执行策略规则提示、MCP 提示、`request_permissions` 提示与技能脚本审批。

### 自动审批审查

默认状态下，审批请求路由给你：

```toml
approvals_reviewer = "user"
```

审批是交互式的（例如 `approval_policy = "on-request"` 或细粒度审批策略）时，自动审批审查生效。设 `approvals_reviewer = "auto_review"` 让符合条件的审批请求在 Codex 运行之前经过审查者代理：

```toml
approval_policy = "on-request"
approvals_reviewer = "auto_review"
```

完整的审查者生命周期、触发条件、配置优先级与失败行为，看 [自动审查](https://developers.openai.com/codex/sandboxing/auto-review)。

审查者只评估本来就需要审批的操作，例如沙箱升级、被阻止的网络请求、`request_permissions` 提示，或带副作用的应用与 MCP 工具调用。留在沙箱内部的操作无需额外审查步骤即可继续。

审查者策略检查数据渗漏、凭据探测、持续性安全削弱与破坏性操作。策略允许时，低风险与中风险操作可以继续。策略拒绝极高风险操作。高风险操作需要足够的授权且没有匹配的拒绝规则。提示词构建、审查会话与解析失败采取故障关闭策略。超时单独显示，但操作仍然不会运行。

[默认审查者策略](https://github.com/openai/codex/blob/main/codex-rs/core/src/guardian/policy.md)在开源 Codex 仓库里。企业可以用托管要求里的 `guardian_policy_config` 替换租户特定部分。也支持本地 `[auto_review].policy` 文本，但托管要求优先。设置详情看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration#configure-automatic-review-policy)。

在 ChatGPT 桌面应用里，这些审查显示为自动审查项，状态有「正在审查（Reviewing）」「已批准（Approved）」「已拒绝（Denied）」「已中止（Aborted）」「已超时（Timed out）」。还可以包含对所审查请求的风险级别与用户授权评估。

自动审查使用额外的模型调用，可能增加 Codex 的使用量。管理员可以用 `allowed_approvals_reviewers` 约束它。

### 常见的沙箱与审批组合

非交互式运行用 `codex exec --sandbox workspace-write`。

#### `config.toml` 中的配置

更广的配置工作流看 [配置基础](https://developers.openai.com/codex/config-file/config-basic)、[高级配置](https://developers.openai.com/codex/config-file/config-advanced#approval-policies-and-sandbox-modes) 与 [配置参考](https://developers.openai.com/codex/config-file/config-reference)。

```toml
# Interactive approvals with a read-only sandbox
approval_policy = "on-request"
sandbox_mode = "read-only"
allow_login_shell = false # optional hardening: disallow login shells for shell-based tools

# Optional: Allow network in workspace-write mode
[sandbox_workspace_write]
network_access = true

# Optional: granular approval policy
# approval_policy = { granular = {
#   sandbox_approval = true,
#   rules = true,
#   mcp_elicitations = true,
#   request_permissions = false,
#   skill_approval = false
# } }
```

还可以把预设保存为 [配置 profile](https://developers.openai.com/codex/config-file/config-advanced#profiles)，然后用 `codex --profile profile-name` 选择：

```toml
# ~/.codex/full_auto.config.toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```

```toml
# ~/.codex/readonly_quiet.config.toml
approval_policy = "never"
sandbox_mode = "read-only"
```

### 在本地测试沙箱

看命令在 Codex 沙箱下运行的表现，用这些 Codex CLI 命令：

```bash
# macOS
codex sandbox macos [--permissions-profile <name>] [--log-denials] [COMMAND]...
# Linux
codex sandbox linux [--permissions-profile <name>] [COMMAND]...
# Windows
codex sandbox windows [--permissions-profile <name>] [COMMAND]...
```

`sandbox` 命令也可以作为 `codex debug` 使用，平台辅助工具有别名（例如 `codex sandbox seatbelt` 与 `codex sandbox landlock`）。

## 操作系统级沙箱

Codex 按操作系统用不同方式强制执行沙箱：

**macOS** 用 Seatbelt 策略，通过 `sandbox-exec` 以所选 `--sandbox` 模式对应配置文件（`-p`）运行命令。受限读访问启用平台默认设置时，Codex 会附加一个精选的 macOS 平台策略（给常用工具保持兼容性，避免宽泛允许 `/System`）。

**Linux** 默认用 `bwrap` 加 `seccomp`。

**Windows** 支持 [MXC](https://developers.openai.com/codex/windows/windows-sandbox#windows-sandbox)，以 `elevated` 与 `unelevated` 作为旧版回退。在 [WSL2](https://developers.openai.com/codex/windows/wsl)（适用于 Linux 的 Windows 子系统 2）里，Codex 用 Linux 沙箱实现。Codex `0.114` 及更早版本支持 WSL1；从 `0.115` 开始，Linux 沙箱迁移到 `bwrap`，不再支持 WSL1。

在 Windows 上用 Codex IDE 扩展时，它直接支持 WSL2。在 VS Code 设置里做如下设置，确保智能体在可用时始终留在 WSL2 内部：

```json
{
  "chatgpt.runCodexInWindowsSubsystemForLinux": true
}
```

这确保即使宿主操作系统是 Windows，IDE 扩展也继承用于命令、审批与文件系统访问的 Linux 沙箱语义。更多内容看 [WSL 指南](https://developers.openai.com/codex/windows/wsl)。

Windows 上运行时，设备与策略支持的话，在 `config.toml` 里这样设置优先 MXC：

```toml
[features]
prefer_mxc = true
```

在 `windows.sandbox` 里保留一个允许的旧版实现作为回退。配置与兼容限制看 [Windows 设置指南](https://developers.openai.com/codex/windows/windows-sandbox#enable-mxc)。

在 Docker 这类容器化环境里运行 Linux 时，宿主或容器配置阻止了 Codex 需要的命名空间、setuid `bwrap` 或 `seccomp` 操作的话，沙箱可能无法工作。此时配置 Docker 容器提供你需要的隔离，然后在容器内部带 `--sandbox danger-full-access`（或 `--dangerously-bypass-approvals-and-sandbox` 标志）运行 `codex`。

### 在 Dev Containers 中运行 Codex

宿主机无法直接运行 Linux 沙箱，或组织已标准化容器化开发时，用 Dev Containers 运行 Codex，让 Docker 提供外部隔离边界。适用于 Visual Studio Code Dev Containers 及兼容工具。

Dev Containers 提供实质性保护，但挡不住每一次攻击。在容器内部带 `--sandbox danger-full-access` 或 `--dangerously-bypass-approvals-and-sandbox` 运行 Codex 时，恶意项目可能偷走 devcontainer 内可用的任何东西，包括 Codex 凭据。只在受信任的仓库里用这个模式，并像在任何其他提升权限的环境里一样监控 Codex 活动。

容器内部选一种模式：

- Dev Container 配置文件授予 `bwrap` 创建内部沙箱所需权限时，保持 Codex 的 Linux 沙箱启用。
- 容器就是你预期的安全边界时，在容器内部带 `--sandbox danger-full-access` 运行 Codex，让 Codex 不再尝试创建第二层沙箱。

## 版本控制

Codex 与版本控制工作流配合最好：

- 在特性分支上工作，委托之前保持 `git status` 干净。这让 Codex 补丁更容易隔离与还原。
- 优先用基于补丁的工作流（例如 `git diff`/`git apply`），避免直接编辑被跟踪的文件。频繁提交，按小增量回滚。
- 把 Codex 的建议当作任何其他 PR 对待：运行针对性验证、审查差异（diffs）、在提交信息里记录决策以便审计。

## 监控与遥测

Codex 支持通过 OpenTelemetry（OTel）选择性加入的监控，帮助团队审计使用、调查问题并满足合规要求，同时不削弱本地安全默认设置。遥测默认关闭；在配置里显式启用。

### 概述

- Codex 默认关闭 OTel 导出，保持本地运行自包含。
- 启用后，Codex 发出结构化日志事件，覆盖聊天、API 请求、SSE/WebSocket 流活动、用户提示词（默认已脱敏）、工具审批决策与工具结果。
- Codex 用 `service.name`（发起方）、CLI 版本与环境标签标记导出事件，隔离开发/预发/生产流量。

### 启用 OTel（选择加入）

在 Codex 配置（通常是 `~/.codex/config.toml`）里加一个 `[otel]` 块，选导出器以及是否记录提示词文本：

```toml
[otel]
environment = "staging" # dev | staging | prod
exporter = "none" # none | otlp-http | otlp-grpc
log_user_prompt = false # redact prompt text unless policy allows
```

`exporter = "none"` 保持插桩活动，但不向任何地方发送数据。

```toml
[otel]
exporter = { otlp-http = {
  endpoint = "https://otel.example.com/v1/logs",
  protocol = "binary",
  headers = { "x-otlp-api-key" = "${OTLP_TOKEN}" }
}}
```

```toml
[otel]
exporter = { otlp-grpc = {
  endpoint = "https://otel.example.com:4317",
  headers = { "x-otlp-meta" = "abc123" }
}}
```

Codex 批量处理事件并在关闭时刷新。Codex 只导出由其 OTel 模块生成的遥测数据。

### 事件类别

代表性事件类型：

- `codex.conversation_starts`（模型、推理设置、沙箱/审批策略）
- `codex.api_request`（尝试次数、状态/成功、持续时间与错误详情）
- `codex.sse_event`（流事件种类、成功/失败、持续时间，以及 `response.completed` 时的 token 计数）
- `codex.websocket_request` 与 `codex.websocket_event`（请求持续时间与每条消息的种类/成功/错误）
- `codex.user_prompt`（长度；内容已脱敏，除非明确启用）
- `codex.tool_decision`（已批准/已拒绝，来源：配置与用户）
- `codex.tool_result`（持续时间、成功、输出片段）

相关 OTel 指标（计数器加持续时间直方图对）包括 `codex.api_request`、`codex.sse_event`、`codex.websocket.request`、`codex.websocket.event` 与 `codex.tool.call`（带相应的 `.duration_ms` 工具）。

完整事件目录与配置参考，看 [GitHub 上的 Codex 配置文档](https://github.com/openai/codex/blob/main/docs/config.md#otel)。

### 安全与隐私指导

- 除非策略明确允许存储提示词内容，保持 `log_user_prompt = false`。提示词可能包含源代码与敏感数据。
- 只把遥测路由到你控制的收集器；应用符合合规要求的保留限制与访问控制。
- 工具参数与输出当作敏感信息。可能时优先在收集器或 SIEM 处脱敏。
- 不希望 Codex 把会话转录保存在 `CODEX_HOME` 下时，检查本地数据保留设置（例如 `history.persistence` / `history.max_bytes`）。看 [高级配置](https://developers.openai.com/codex/config-file/config-advanced#history-persistence) 与 [配置参考](https://developers.openai.com/codex/config-file/config-reference)。
- 关闭网络访问运行 CLI 时，OTel 导出到不了你的收集器。要导出，在 `workspace-write` 模式下为 OTel 端点允许网络访问，或从 Codex 云导出并批准收集器域。
- 定期审查事件，检查审批/沙箱变更与意外的工具执行。

OTel 是可选的，用来补充上述沙箱与审批保护，不替代它们。

## 托管配置

企业管理员在 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration) 里为工作区配置 Codex 安全设置。设置与策略详情看该页。

# Codex 沙箱机制

- 原文：https://developers.openai.com/codex/sandboxing
- 来源：OpenAI Codex 官方文档（Sandbox 页）
- 发布：2026 年现行版本
- 译文说明：全文翻译。官方站对脚本抓取有 Cloudflare 拦截，从中文镜像 developers.openai.ac.cn 抓取正文，对照检索摘要校订；镜像改写的链接恢复为官方原始 URL。

沙箱是让智能体在不获得对你计算机完全不受限制访问的前提下自主行动的边界。本地聊天在 ChatGPT 桌面应用、Codex CLI 或 IDE 扩展里运行命令时，这些命令默认运行在受限环境里，运行形态不带完全访问权限。

该环境定义智能体可以自行执行的操作，例如能修改哪些文件、命令能否使用网络。任务保持在这些边界之内时，智能体可以继续执行而无需停下来等待确认。需要越过这些边界时，审批流程接管。

沙箱与审批是协同工作的不同控制项。沙箱定义技术边界；审批策略决定智能体在越过边界之前何时必须停下来询问。

## 沙箱管什么

沙箱不只作用于内置文件操作，也作用于衍生的命令。智能体运行 `git`、包管理器或测试运行器这类工具时，这些命令继承同样的沙箱边界。

Codex 在每个操作系统上使用平台原生的强制执行机制。macOS、Linux、WSL2 与原生 Windows 的实现不同，但跨界面的核心理念一致：给智能体一个有边界的工作场所，让常规任务在明确的限制内自主运行。

## 为什么重要

沙箱减少审批疲劳。智能体无需请求你确认每一条低风险命令，而是在你已经批准的边界内读文件、做编辑、运行常规的项目命令。

它还给智能体工作提供更清晰的信任模型。你信任的是智能体在强制执行的限制内运作这件事本身，而不只是它的意图。这让智能体独立工作更容易，同时你仍然清楚它何时会停下来寻求帮助。

## 入门

默认权限模式自动应用沙箱机制。

### 前提条件

**macOS** 上，沙箱用内置 Seatbelt 框架开箱即用。

**Windows** 上，PowerShell 里运行时 Codex 用原生 [Windows 沙箱](https://developers.openai.com/codex/windows/windows-sandbox#windows-sandbox)，WSL2 里运行时用 Linux 沙箱实现。

**Linux 和 WSL2** 先用包管理器安装 bubblewrap：

```bash
sudo apt install bubblewrap
```

```bash
sudo dnf install bubblewrap
```

Codex 用它在 `PATH` 里找到的第一个 `bwrap` 可执行文件。没有可用的 `bwrap` 时，Codex 回退到一个打包的辅助程序，但该辅助程序需要支持创建无特权用户命名空间。安装提供 `bwrap` 的发行版包可以让这套设置可靠。

缺少 `bwrap` 或辅助程序无法创建所需用户命名空间时，Codex 显示启动警告。在限制此 AppArmor 设置的发行版上，优先加载 `bwrap` 的 AppArmor profile，让 `bwrap` 继续工作而无需全局禁用该限制。

**Ubuntu AppArmor 说明**：Ubuntu 25.04 上从 Ubuntu 包仓库安装 `bubblewrap` 应该无需额外 AppArmor 设置即可工作。`bwrap-userns-restrict` profile 随 `apparmor` 包提供，位于 `/etc/apparmor.d/bwrap-userns-restrict`。

Ubuntu 24.04 上，安装 bubblewrap 后 Codex 仍可能警告无法创建所需的用户命名空间。复制并加载额外的 profile：

```bash
sudo apt update
sudo apt install apparmor-profiles apparmor-utils
sudo install -m 0644 \
  /usr/share/apparmor/extra-profiles/bwrap-userns-restrict \
  /etc/apparmor.d/bwrap-userns-restrict
sudo apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict
```

`apparmor_parser -r` 把 profile 载入内核，无需重启。也可以重载全部 AppArmor profile：

```bash
sudo systemctl reload apparmor.service
```

该 profile 不可用或不解决问题时，可以禁用 AppArmor 无特权用户命名空间限制：

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

#### 带 Work Cloud 的本地计算机访问

用 Work Cloud 做本地计算机访问的任务，由 OpenAI 的云端协调对话。沙箱限制取决于每一步的运行位置：

**云端执行**：Work 云容器使用现有的 Work 云策略。桌面浏览器网站规则不会自动应用于云端浏览器。

**本地执行**：受支持的本地执行要求管理已连接计算机上的步骤。

带本地访问与 dots 的 Work，启用托管策略时，受支持的全局策略适用于共享云编排器。Work 云容器与 dots 云计算机各自使用自己的执行配置与要求。本地与云端执行分别测试，确认哪些控制适用于各个环境。一个环境的策略不会授予对另一个环境的访问。

策略内部，从高到低的顺序是：OS 专属环境覆盖 → 全 OS 环境覆盖 → Global。高优先级策略占优，即使低优先级策略更具体。本地执行上，MDM 与旧版受管设备要求优先于智能体安全（Agent Security），后者优先于设备的系统要求文件。

字段专属的合并规则与运行时限制看 [托管配置](https://developers.openai.com/codex/enterprise/managed-configuration)，生效的文件与网络限制看 [Work 本地安全](https://developers.openai.com/codex/enterprise/chatgpt-work-local-security) 与 [Work 云安全](https://developers.openai.com/codex/enterprise/chatgpt-work-cloud-security)。

## 权限的工作方式

用界面的权限控制改变 Codex 处理本地操作的方式。

审批决定 Codex 在操作之前何时暂停，沙箱决定命令可以访问哪些文件与网络资源。审批提供不同范围时（例如单次批准或整个会话批准），选能让任务继续的最小范围。项目边界作为默认值；用独立的项目或工作树（worktree），避免扩大到不相关代码库的访问。

ChatGPT Work 在托管的隔离环境里运行代码与 shell 命令。工作区策略与工具专属的控制决定哪些功能可用。设置可用时，用「设置 > 数据控制 > 工作网络访问」管理代码与 shell 命令的网络访问。开「允许公共互联网访问」让这些命令访问公共互联网。关闭时，命令只能访问托管白名单里的必需主机名。

web search、插件与远程浏览器有单独的控制。更改在当前代码或 shell 运行结束、Work 刷新执行环境之后生效。ChatGPT 网页版不公开本地 Codex 沙箱或审批模式选择器。

ChatGPT 桌面应用里，用输入框下方的权限控制。按你的配置，菜单可能包含「请求批准」、面向符合条件审批请求的「替我批准」、「完全访问」以及命名或自定义的权限 profile。

### 替我批准

「替我批准」保留与「请求批准」相同的 workspace-write 沙箱，但符合条件的审批请求经自动审查路由，不再显示手动审批提示。更多内容看 [自动审查](https://developers.openai.com/codex/sandboxing/auto-review)。沙箱 `workspace-write`、审批策略 `on-request`、审查者 `auto_review`。

CLI 里输入 [`/permissions`](https://developers.openai.com/codex/developer-commands?surface=cli#cli-update-permissions-with-permissions) 打开权限选择器，更改活动权限 profile。

IDE 扩展里，用输入框下方的权限控制。按你的配置，菜单可能包含「请求批准」、面向符合条件审批请求的「替我批准」、「完全访问」以及命名或自定义的权限 profile。

## 配置默认值

要每次以相同行为开始，在 `config.toml` 里设置默认值。[配置基础](https://developers.openai.com/codex/config-file/config-basic) 讲它怎么工作，[配置参考](https://developers.openai.com/codex/config-file/config-reference) 记录 `sandbox_mode`、`approval_policy`、`approvals_reviewer` 与 `sandbox_workspace_write.writable_roots` 的确切键。用这些设置决定智能体默认获得多少自主权、它可以写入哪些目录、何时应暂停等待批准、谁来审查符合条件的审批请求。

常见的沙箱模式：

- `read-only`：智能体可以查看文件，未获批准不能编辑文件或运行命令。
- `workspace-write`：智能体可以读文件、在工作区内编辑、在该边界内运行常规本地命令。这是本地工作的默认低摩擦模式。
- `danger-full-access`：智能体不带沙箱限制运行。这取消文件系统与网络边界，只在你希望智能体以完全访问权限行动时使用。

常见的审批策略：

- `on-request`：智能体默认在沙箱内部工作，需要越过边界时询问。
- `never`：智能体不会因审批提示停下。

Codex 与 ChatGPT Work 不再把 `untrusted` 作为可选审批策略。现有配置用了该值时，看[从已退役的 `untrusted` 审批策略迁移](codex-approvals-security.md#从已退役的-untrusted-审批策略迁移)。

审批具有交互性时，还可以用 `approvals_reviewer` 选择由谁审查：

- `user`：审批提示显示给用户。默认设置。
- `auto_review`：符合条件的审批提示发给审查者智能体（看 [自动审查](https://developers.openai.com/codex/sandboxing/auto-review)）。

完全访问指 `sandbox_mode = "danger-full-access"` 结合 `approval_policy = "never"`。对照之下，低风险本地自动化预设是 `sandbox_mode = "workspace-write"` 结合 `approval_policy = "on-request"`，或对应 CLI 标志 `--sandbox workspace-write --ask-for-approval on-request`。然后保留 `approvals_reviewer = "user"` 做手动审批，或设 `approvals_reviewer = "auto_review"` 做自动审批审查。

需要智能体跨多个目录工作时，可写根（writable roots）允许扩展它能修改的位置，而无需完全移除沙箱。需要更宽或更窄的信任边界时，调整默认沙箱模式与审批策略，避免依赖一次性例外。

工作流需要特定例外时，用[规则（rules）](https://developers.openai.com/codex/agent-configuration/rules)。规则允许你允许、提示或禁止沙箱外部的命令前缀，这通常比宽泛扩大访问更合适。IDE 专属的设置入口看 [Codex IDE 扩展设置](https://developers.openai.com/codex/developer-settings?surface=ide)。

自动审查（可用时）不改变沙箱边界。它是该边界处审批请求的一个可选 `approvals_reviewer`，例如沙箱升级、被阻止的网络访问或仍需批准的带副作用工具调用。沙箱内部已经允许的操作无需额外审查即可运行。审查者生命周期、触发类型、拒绝语义与配置详情看 [自动审查](https://developers.openai.com/codex/sandboxing/auto-review)。

平台详情在平台专属文档里。原生 Windows 的设置、行为与故障排除看 [Windows](https://developers.openai.com/codex/windows/windows-sandbox)。沙箱与审批的管理要求及组织级限制看 [智能体审批与安全](codex-approvals-security.md)。

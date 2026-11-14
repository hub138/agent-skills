# 超越权限确认：让 Claude Code 更安全也更自主（Beyond permission prompts: making Claude Code more secure and autonomous）

- 原文：[Beyond permission prompts: making Claude Code more secure and autonomous](https://www.anthropic.com/research/claude-code-sandboxing)
- 来源：Anthropic Engineering，作者 David Dworken 与 Oliver Weller-Davies
- 发布：2025-10-20
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链。

在 [Claude Code](https://www.claude.com/product/claude-code) 里，Claude 与你一起写代码、测试、调试：遍历你的代码库、编辑多个文件、运行命令验证自己的工作。给 Claude 这么大的代码库与文件访问权会引入风险，prompt injection（提示注入）场景下尤其如此。

为帮助应对，我们在 Claude Code 里推出了两个构建在沙箱之上的新功能，都旨在给开发者一个更安全的工作环境，同时让 Claude 运行得更自主、权限确认更少。内部使用中，我们发现沙箱化让权限确认安全地减少 84%。通过划定 Claude 可以自由工作的边界，两个功能同时提升了安全性与自主度。

## 保障 Claude Code 上的用户安全

Claude Code 基于权限模型运行：默认只读，任何修改或运行命令之前都要先请求许可。也有例外：echo、cat 这类安全命令会自动放行，但多数操作仍需明确批准。

不停点击 "approve" 会拖慢开发循环，还会造成「批准疲劳」：用户不再仔细看自己批准了什么，反而让开发更不安全。

为此，我们为 Claude Code 推出了沙箱化。

## 沙箱化：更安全也更自主的做法

沙箱化预先划出边界，Claude 在边界内可以更自由地工作，无需为每个动作逐一请求许可。开启沙箱化后，权限确认大幅减少，安全性随之提升。

我们的沙箱化构建在操作系统级别的特性之上，实现两道边界：

1. 文件系统隔离，确保 Claude 只能访问或修改特定目录。这对防止被 prompt injection 的 Claude 篡改敏感系统文件尤其重要。
2. 网络隔离，确保 Claude 只能连接获准的服务器。这防止被 prompt injection 的 Claude 泄露敏感信息或下载恶意软件。

值得强调，有效的沙箱化需要文件系统隔离与网络隔离同时在场。没有网络隔离，被攻陷的 agent 可以把 SSH 密钥这类敏感文件传送出去；没有文件系统隔离，被攻陷的 agent 可以轻易逃出沙箱、取得网络访问。两种技术并用，我们才能给 Claude Code 用户更安全也更快的 agentic 体验。

### Claude Code 的两个沙箱化新功能

#### 沙箱化的 bash 工具：无需权限确认的安全 bash 执行

我们推出[一个新沙箱运行时](https://docs.claude.com/en/docs/claude-code/sandboxing)，以 research preview 的 beta 形态提供。它让你精确定义 agent 能访问哪些目录与网络主机，无需承担启动和管理容器的开销。它可以沙箱化任意进程、agent 与 MCP server，也有[开源 research preview](https://github.com/anthropic-experimental/sandbox-runtime) 版本。

在 Claude Code 里，我们用这个运行时沙箱化 bash 工具，让 Claude 在你划定的限制内运行命令。安全沙箱里，Claude 可以更自主地运行、安全执行命令、不弹权限确认。Claude 试图访问沙箱之外的东西时，你会立刻收到通知，自行决定是否放行。

我们把它构建在 [Linux bubblewrap](https://github.com/containers/bubblewrap) 与 MacOS seatbelt 这类操作系统级原语之上，在 OS 层强制执行这些限制。它们覆盖 Claude Code 的直接交互，也覆盖命令派生的任何脚本、程序或子进程。如上所述，这个沙箱同时执行：

1. 文件系统隔离：允许读写当前工作目录，阻止修改目录之外的任何文件。
2. 网络隔离：只允许通过一个 unix domain socket 连接沙箱外运行的代理服务器来访问互联网。代理服务器限制进程能连接的域名，并处理新请求域名的用户确认。想再提高安全性，我们还支持定制这个代理，对出站流量执行任意规则。

两个组件都可配置：你可以轻松选择允许或禁止特定文件路径与域名。

![沙箱化架构示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/0d1c612947c798aef48e6ab4beb7e8544da9d41a-4096x2305.png)

沙箱化保证即便 prompt injection 得手也被完全隔离，无法波及用户的整体安全。这样，被攻陷的 Claude Code 偷不走你的 SSH 密钥，也无法向攻击者的服务器回传数据。

要上手这个功能，在 Claude Code 里运行 /sandbox，并查看我们安全模型的[更多技术细节](https://docs.claude.com/en/docs/claude-code/sandboxing)。

为了让其他团队更容易构建更安全的 agent，我们已把这个功能[开源](https://github.com/anthropic-experimental/sandbox-runtime)。我们相信其他团队也应当考虑为自己的 agent 采用这项技术，增强 agent 的安全姿态。

#### Claude Code on the web：在云端安全运行 Claude Code

今天我们同时发布 [Claude Code on the web](https://docs.claude.com/en/docs/claude-code/claude-code-on-the-web)，让用户在云端的隔离沙箱里运行 Claude Code。Claude Code on the web 把每个 Claude Code 会话放进一个隔离沙箱执行，在其中它可以安全地完整访问自己的服务器。这个沙箱的设计保证敏感凭证（如 git 凭证或签名密钥）永远不与 Claude Code 同处沙箱之内。这样，即使沙箱里运行的代码被攻陷，用户也不会受到进一步伤害。

Claude Code on the web 用一个定制代理服务透明处理全部 git 交互。沙箱内，git client 用一个专门构建的受限凭证向这个服务认证。代理核验这份凭证与 git 交互的内容（比如确认它只向配置的分支推送），再附上正确的 authentication token，把请求发给 GitHub。

![git 代理示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/e8f66bcf73d9d23cae67e67776b2d31373c13050-4096x2305.png)

## 上手

新的沙箱化 bash 工具与 Claude Code on the web，为用 Claude 做工程工作的开发者带来安全与生产力两方面的实质提升。

上手这两个工具：

1. 在 Claude 里运行 `/sandbox`，查看我们关于配置这个沙箱的[文档](https://docs.claude.com/en/docs/claude-code/sandboxing)。
2. 访问 [claude.com/code](http://claude.ai/code) 试用 Claude Code on the web。

如果你在构建自己的 agent，可以看我们的[开源沙箱代码](https://github.com/anthropic-experimental/sandbox-runtime)，考虑把它集成进你的工作。期待看到你构建的成果。

想深入了解 Claude Code on the web，看我们的[发布博客](https://www.anthropic.com/news/claude-code-on-the-web)。

## 作者与致谢

本文由 David Dworken 与 Oliver Weller-Davies 撰写，Meaghan Choi、Catherine Wu、Molly Vorwerck、Alex Isken、Kier Bradwell 与 Kevin Garcia 参与贡献。

# agent-skills

一组面向写作与设计的 AI 技能（Skills），用于 Claude Code、Codex、CodeBuddy 等支持 SKILL.md 规范的命令行智能体。每个技能是一个自包含目录：`SKILL.md` 指令文件 + `references/` 方法手册 + `scripts/` 质量门脚本。

## 技能清单

| 技能 | 用途 |
|---|---|
| [article-illustration](article-illustration/SKILL.md) | 给文章配图：判定哪些段落需要图、先找现成图再自绘、图源核验与配图密度评估 |
| [design-craft](design-craft/SKILL.md) | 界面设计规矩：视觉层级、排版尺度、间距栅格、语义色、交互五态、评审与门禁 |
| [human-voice](human-voice/SKILL.md) | 中文文本的人味增强与 AI 痕迹清理：判据、特征表、任务绑定与浓度分档 |
| [skill-craft](skill-craft/SKILL.md) | 技能本身的工程规范：如何写、如何评审、如何维护一个 SKILL |

## 安装方式

把对应技能目录整个放进你的智能体技能目录即可，例如 Claude Code：

```bash
git clone https://github.com/hub138/agent-skills.git
cp -r agent-skills/article-illustration ~/.claude/skills/
```

## 脚本依赖

技能脚本自包含，按需安装依赖：

```bash
pip install python-frontmatter markdown-it-py
# 量图脚本另需
pip install pillow lxml beautifulsoup4 playwright
```

外部模型调用统一走 `cli_runner.py`，用环境变量 `CLI_REVIEW_COMMAND` 指定命令模板（如 `claude -p --model {model}`），不绑定任何特定厂商。

## 目录约定

```
<skill>/
  SKILL.md        # 入口指令：触发条件、工作流、红线
  references/     # 方法手册：判据、模式表、图源清单
  scripts/        # 质量门与工具脚本（Python 3.10+）
```

## 新增技能

仓库会持续收录新技能，收录流程：

1. 把技能目录（含 `SKILL.md`、`references/`、`scripts/`）拷到仓库根目录；
2. 在上方技能清单表格里加一行：技能名链接到其 `SKILL.md`，一句话写清用途；
3. 检查目录内无内部路径、密钥、临时产物（`__pycache__`、`.work/` 等）；
4. 提交并推送：

```bash
git add <skill-name>/ README.md
git commit -m "Add <skill-name> skill"
git push origin main
```

技能的编写规范见 [skill-craft](skill-craft/SKILL.md)。

## License

[MIT](LICENSE)
